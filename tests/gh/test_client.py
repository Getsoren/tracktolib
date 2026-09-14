import json
from contextlib import nullcontext
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import cast

import niquests
import pytest

from tracktolib.gh import GitHubClient, GitHubError


@dataclass
class FakeRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: str


@dataclass
class FakeGitHub:
    """Replies with a canned response and records what the client sent."""

    url: str = ""
    status: int = 200
    body: str = "{}"
    content_type: str = "application/json"
    requests: list[FakeRequest] = field(default_factory=list)


class FakeGitHubServer(HTTPServer):
    fake: FakeGitHub


class FakeGitHubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Overridden to prevent logging
        pass

    def _serve(self):
        fake = cast("FakeGitHubServer", self.server).fake
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        fake.requests.append(FakeRequest(self.command, self.path, dict(self.headers), body))

        payload = fake.body.encode()
        self.send_response(fake.status)
        self.send_header("Content-Type", fake.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _serve
    do_POST = _serve


@pytest.fixture
def fake_github():
    server = FakeGitHubServer(("localhost", 0), FakeGitHubHandler)
    server.fake = FakeGitHub(url="http://{}:{}".format(*server.server_address))

    thread = Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    yield server.fake

    server.shutdown()
    server.server_close()


@pytest.fixture
async def gh(fake_github):
    async with GitHubClient(token="test-token", base_url=fake_github.url) as client:
        yield client


@pytest.mark.parametrize(
    "call, expected_accept",
    [
        pytest.param(
            lambda gh: gh.get_pull_request_diff("owner/repo", 42),
            "application/vnd.github.v3.diff",
            id="diff-overrides-accept",
        ),
        pytest.param(
            lambda gh: gh.get_pull_request("owner/repo", 42),
            "application/vnd.github+json",
            id="default-accept-untouched",
        ),
    ],
)
async def test_accept_header(gh, fake_github, call, expected_accept):
    await call(gh)
    assert fake_github.requests[-1].headers["Accept"] == expected_accept


async def test_get_pull_request_diff_returns_text(gh, fake_github):
    fake_github.body = "diff --git a/foo.py b/foo.py\n+1\n"
    fake_github.content_type = "text/plain"

    assert await gh.get_pull_request_diff("owner/repo", 42) == fake_github.body


@pytest.mark.parametrize(
    "body, expected",
    [
        pytest.param({"permission": "admin"}, "admin", id="admin"),
        pytest.param({"permission": "none"}, "none", id="none"),
        pytest.param({"user": {"login": "octocat"}}, None, id="missing-permission-raises"),
        pytest.param([], None, id="unexpected-shape-raises"),
    ],
)
async def test_get_collaborator_permission(gh, fake_github, body, expected):
    fake_github.body = json.dumps(body)

    with nullcontext() if expected else pytest.raises(GitHubError):
        assert await gh.get_collaborator_permission("owner/repo", "octocat") == expected

    assert fake_github.requests[-1].path == "/repos/owner/repo/collaborators/octocat/permission"


@pytest.mark.parametrize(
    "call, expected_path, expected_payload",
    [
        pytest.param(
            lambda gh: gh.create_pull_request_review(
                "owner/repo",
                42,
                body="Looks good",
                event="APPROVE",
                comments=[{"path": "foo.py", "line": 12, "start_line": 10, "side": "RIGHT", "body": "nit"}],
                commit_id="abc123",
            ),
            "/repos/owner/repo/pulls/42/reviews",
            {
                "event": "APPROVE",
                "body": "Looks good",
                "commit_id": "abc123",
                "comments": [{"path": "foo.py", "line": 12, "start_line": 10, "side": "RIGHT", "body": "nit"}],
            },
            id="review-with-comments",
        ),
        pytest.param(
            lambda gh: gh.create_pull_request_review("owner/repo", 42, body="No comment"),
            "/repos/owner/repo/pulls/42/reviews",
            {"event": "COMMENT", "body": "No comment"},
            id="review-without-comments",
        ),
        pytest.param(
            lambda gh: gh.create_reaction("owner/repo", 7, "eyes"),
            "/repos/owner/repo/issues/comments/7/reactions",
            {"content": "eyes"},
            id="reaction",
        ),
    ],
)
async def test_post_payload(gh, fake_github, call, expected_path, expected_payload):
    await call(gh)

    request = fake_github.requests[-1]
    assert request.method == "POST"
    assert request.path == expected_path
    assert json.loads(request.body) == expected_payload


@pytest.mark.parametrize(
    "status, body, expected_message",
    [
        pytest.param(404, '{"message": "Not Found"}', "Not Found", id="github-message"),
        pytest.param(403, '{"message": "Resource not accessible by integration"}', None, id="forbidden"),
        pytest.param(502, "<html>oops</html>", "Bad Gateway", id="non-json-body-falls-back-to-reason"),
    ],
)
async def test_raise_github_error(gh, fake_github, status, body, expected_message):
    fake_github.status = status
    fake_github.body = body

    with pytest.raises(GitHubError) as exc_info:
        await gh.get_pull_request("owner/repo", 42)

    error = exc_info.value
    assert error.status == status
    assert error.message == (expected_message or json.loads(body)["message"])
    assert error.response is not None
    # Still an HTTPError so callers of the previous behaviour keep working
    assert isinstance(error, niquests.HTTPError)
