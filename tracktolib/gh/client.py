from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal, NotRequired, TypedDict, cast
from urllib.parse import quote

try:
    import niquests
except ImportError:
    raise ImportError('Please install niquests or tracktolib with "gh" to use this module')

if TYPE_CHECKING:
    from urllib3.util.retry import Retry

    from tracktolib.gh.types import (
        Deployment,
        DeploymentStatus,
        IssueComment,
        Label,
        PullRequest,
        PullRequestReview,
        PullRequestSimple,
        Reaction,
    )


ProgressCallback = Callable[[int, int], None]
ReactionContent = Literal["+1", "-1", "laugh", "confused", "heart", "hooray", "rocket", "eyes"]
ReviewEvent = Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"]

DIFF_ACCEPT = "application/vnd.github.v3.diff"


class ReviewComment(TypedDict):
    """A line anchored review comment, line and start_line being 1-based line numbers of the file side."""

    path: str
    body: str
    line: NotRequired[int]
    start_line: NotRequired[int]
    side: NotRequired[Literal["LEFT", "RIGHT"]]
    start_side: NotRequired[Literal["LEFT", "RIGHT"]]


class GitHubError(niquests.HTTPError):
    """
    Error raised when a GitHub API call fails, keeping the status and the message returned by GitHub.

    Subclasses niquests.HTTPError so existing callers catching it keep working.
    """

    def __init__(self, status: int, message: str, *, response: niquests.Response | None = None) -> None:
        self.status = status
        self.message = message
        super().__init__(f"{status}: {message}", response=response)


def _raise_for_status(response: niquests.Response) -> None:
    """Raise GitHubError on an error response, using the "message" field GitHub returns in the body."""
    status = response.status_code
    if status is None or status < 400:
        return
    try:
        payload = response.json()
    except ValueError:
        payload = None
    message = payload.get("message") if isinstance(payload, dict) else None
    raise GitHubError(status, message or response.reason or "unknown error", response=response)


@dataclass
class GitHubClient:
    """
    Async GitHub API client for issues, labels, pull requests, reviews and deployments.
    """

    token: str | None = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN"))
    base_url: str = "https://api.github.com"
    retries: int | Retry = 0
    hooks: Any = None
    session: niquests.AsyncSession = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.token:
            raise ValueError("GITHUB_TOKEN environment variable is required")

        self.session = niquests.AsyncSession(
            base_url=self.base_url,
            retries=self.retries,
            hooks=self.hooks,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying session."""
        await self.session.close()

    async def _get_all(self, url: str, *, params: dict[str, str] | None = None) -> list[Any]:
        """Collect list responses by following GitHub's next-page links."""
        results: list[Any] = []
        # GitHub defaults to 30 items per page; 100 is the maximum
        params = {"per_page": "100", **(params or {})}
        # Pages are fetched serially: GitHub asks for serial requests per token to avoid secondary rate limits
        while True:
            response = await self.session.get(url, params=params)
            _raise_for_status(response)
            results.extend(response.json())
            if not (next_url := response.links.get("next", {}).get("url")):
                return results
            url = next_url
            params = None

    # Issue Comments

    async def get_issue_comments(self, repository: str, issue_number: int) -> list[IssueComment]:
        """Get all comments on an issue or PR."""
        return await self._get_all(f"/repos/{repository}/issues/{issue_number}/comments")

    async def create_issue_comment(self, repository: str, issue_number: int, body: str) -> IssueComment:
        """Create a comment on an issue or PR."""
        response = await self.session.post(f"/repos/{repository}/issues/{issue_number}/comments", json={"body": body})
        _raise_for_status(response)
        return cast("IssueComment", response.json())

    async def update_issue_comment(self, repository: str, comment_id: int, body: str) -> IssueComment:
        """Update a comment by ID."""
        response = await self.session.patch(f"/repos/{repository}/issues/comments/{comment_id}", json={"body": body})
        _raise_for_status(response)
        return cast("IssueComment", response.json())

    async def delete_issue_comment(self, repository: str, comment_id: int) -> None:
        """Delete a comment by ID."""
        response = await self.session.delete(f"/repos/{repository}/issues/comments/{comment_id}")
        _raise_for_status(response)

    async def find_comments_with_marker(self, repository: str, issue_number: int, marker: str) -> list[int]:
        """Find comment IDs containing a specific marker string."""
        comments = await self.get_issue_comments(repository, issue_number)
        return [c["id"] for c in comments if marker in c.get("body", "")]

    async def delete_comments_with_marker(
        self,
        repository: str,
        issue_number: int,
        marker: str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> int:
        """Delete all comments containing a specific marker. Returns count deleted."""
        comment_ids = await self.find_comments_with_marker(repository, issue_number, marker)
        total = len(comment_ids)
        for i, comment_id in enumerate(comment_ids):
            await self.delete_issue_comment(repository, comment_id)
            if on_progress:
                on_progress(i + 1, total)
        return total

    async def create_idempotent_comment(
        self, repository: str, issue_number: int, body: str, marker: str
    ) -> IssueComment | None:
        """
        Create a comment only if one with the marker doesn't already exist.

        The marker should be included in the body (e.g., an HTML comment like
        '<!-- my-marker -->'). Returns the created comment, or None if skipped.
        """
        if await self.find_comments_with_marker(repository, issue_number, marker):
            return None
        return await self.create_issue_comment(repository, issue_number, body)

    async def create_reaction(self, repository: str, comment_id: int, content: ReactionContent) -> Reaction:
        """Create a reaction on an issue or PR comment, e.g. "eyes" to acknowledge a command."""
        response = await self.session.post(
            f"/repos/{repository}/issues/comments/{comment_id}/reactions", json={"content": content}
        )
        _raise_for_status(response)
        return cast("Reaction", response.json())

    # Labels

    async def get_issue_labels(self, repository: str, issue_number: int) -> list[Label]:
        """Get all labels on an issue or PR."""
        return await self._get_all(f"/repos/{repository}/issues/{issue_number}/labels")

    async def add_labels(self, repository: str, issue_number: int, labels: list[str]) -> list[Label]:
        """Add labels to an issue or PR."""
        response = await self.session.post(f"/repos/{repository}/issues/{issue_number}/labels", json={"labels": labels})
        _raise_for_status(response)
        return cast("list[Label]", response.json())

    async def remove_label(self, repository: str, issue_number: int, label: str) -> bool:
        """Remove a label from an issue/PR. Returns True if removed, False if not found."""
        response = await self.session.delete(
            f"/repos/{repository}/issues/{issue_number}/labels/{quote(label, safe='')}"
        )
        if response.status_code == 404:
            return False
        _raise_for_status(response)
        return True

    # Pull Requests

    async def list_pull_requests(
        self,
        repository: str,
        *,
        state: Literal["open", "closed", "all"] = "open",
        head: str | None = None,
        base: str | None = None,
    ) -> list[PullRequestSimple]:
        """List pull requests for a repository, optionally filtered by state, head or base branch."""
        params: dict[str, str] = {"state": state}
        if head is not None:
            params["head"] = head
        if base is not None:
            params["base"] = base
        return await self._get_all(f"/repos/{repository}/pulls", params=params)

    async def get_pull_request(self, repository: str, number: int) -> PullRequest:
        """Get a single pull request, with the fields list_pull_requests does not return (changed_files, ...)."""
        response = await self.session.get(f"/repos/{repository}/pulls/{number}")
        _raise_for_status(response)
        return cast("PullRequest", response.json())

    async def get_pull_request_diff(self, repository: str, number: int) -> str:
        """Get the unified diff of a pull request."""
        # Per request headers take precedence over the session ones
        response = await self.session.get(f"/repos/{repository}/pulls/{number}", headers={"Accept": DIFF_ACCEPT})
        _raise_for_status(response)
        return response.text or ""

    async def create_pull_request_review(
        self,
        repository: str,
        number: int,
        *,
        body: str | None = None,
        event: ReviewEvent = "COMMENT",
        comments: Sequence[ReviewComment] | None = None,
        commit_id: str | None = None,
    ) -> PullRequestReview:
        """
        Create a review on a pull request, optionally with line anchored comments.

        The comments are anchored on the diff of commit_id, defaulting to the latest commit of the PR.
        """
        payload: dict[str, Any] = {"event": event}
        if body is not None:
            payload["body"] = body
        if commit_id is not None:
            payload["commit_id"] = commit_id
        if comments:
            payload["comments"] = list(comments)
        response = await self.session.post(f"/repos/{repository}/pulls/{number}/reviews", json=payload)
        _raise_for_status(response)
        return cast("PullRequestReview", response.json())

    # Collaborators

    async def get_collaborator_permission(self, repository: str, username: str) -> str:
        """
        Get the permission of a user on a repository: admin, write, read or none.

        Raises GitHubError if the response has no permission rather than assuming one.
        """
        response = await self.session.get(f"/repos/{repository}/collaborators/{quote(username, safe='')}/permission")
        _raise_for_status(response)
        payload = response.json()
        permission = payload.get("permission") if isinstance(payload, dict) else None
        if not isinstance(permission, str):
            raise GitHubError(
                response.status_code or 0,
                f"No permission returned for {username} on {repository}",
                response=response,
            )
        return permission

    # Deployments

    async def get_deployments(self, repository: str, *, environment: str | None = None) -> list[Deployment]:
        """Get deployments, optionally filtered by environment."""
        params = {"environment": environment} if environment else {}
        return await self._get_all(f"/repos/{repository}/deployments", params=params)

    async def create_deployment_status(
        self,
        repository: str,
        deployment_id: int,
        state: str,
        *,
        description: str | None = None,
        environment_url: str | None = None,
    ) -> DeploymentStatus:
        """
        Create a deployment status.

        State can be: error, failure, inactive, in_progress, queued, pending, success.
        """
        payload: dict = {"state": state}
        if description:
            payload["description"] = description
        if environment_url:
            payload["environment_url"] = environment_url
        response = await self.session.post(f"/repos/{repository}/deployments/{deployment_id}/statuses", json=payload)
        _raise_for_status(response)
        return cast("DeploymentStatus", response.json())

    async def get_deployment_statuses(
        self,
        repository: str,
        deployment_id: int,
    ) -> list[DeploymentStatus]:
        """Get all statuses for a deployment, most recent first."""
        return await self._get_all(f"/repos/{repository}/deployments/{deployment_id}/statuses")

    async def get_latest_deployment_status(
        self,
        repository: str,
        environment: str,
    ) -> DeploymentStatus | None:
        """Get the latest deployment status for an environment."""
        deployments = await self.get_deployments(repository, environment=environment)
        if not deployments:
            return None
        statuses = await self.get_deployment_statuses(repository, deployments[0]["id"])
        return statuses[0] if statuses else None

    async def mark_deployment_inactive(
        self,
        repository: str,
        environment: str,
        *,
        description: str = "Environment removed",
        on_progress: ProgressCallback | None = None,
    ) -> int:
        """Mark all deployments for an environment as inactive. Returns count updated."""
        deployments = await self.get_deployments(repository, environment=environment)
        total = len(deployments)
        for i, deployment in enumerate(deployments):
            await self.create_deployment_status(repository, deployment["id"], "inactive", description=description)
            if on_progress:
                on_progress(i + 1, total)
        return total
