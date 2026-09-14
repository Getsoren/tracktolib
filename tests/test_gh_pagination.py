import json
from unittest.mock import AsyncMock, patch

import niquests
import pytest

from tracktolib.gh.client import GitHubClient


def response(items, next_url=None):
    result = niquests.Response()
    result.status_code = 200
    result._content = json.dumps(items).encode()
    if next_url:
        result.headers["Link"] = f'<{next_url}>; rel="next"'
    return result


@pytest.mark.parametrize(
    "method,args,kwargs,params",
    [
        pytest.param("get_issue_comments", ("org/repo", 1), {}, {}, id="comments"),
        pytest.param("get_issue_labels", ("org/repo", 1), {}, {}, id="labels"),
        pytest.param(
            "list_pull_requests",
            ("org/repo",),
            {"head": "org:branch"},
            {"state": "open", "head": "org:branch"},
            id="pulls",
        ),
        pytest.param(
            "get_deployments",
            ("org/repo",),
            {"environment": "preview"},
            {"environment": "preview"},
            id="deployments",
        ),
        pytest.param("get_deployment_statuses", ("org/repo", 1), {}, {}, id="statuses"),
    ],
)
async def test_list_methods_follow_next_links(method, args, kwargs, params):
    next_url = "https://api.github.com/next?page=2&environment=preview"
    session = AsyncMock()
    session.get.side_effect = [response([{"id": 1}], next_url), response([{"id": 2}])]
    with patch("tracktolib.gh.client.niquests.AsyncSession", return_value=session):
        client = GitHubClient(token="test")
        assert await getattr(client, method)(*args, **kwargs) == [{"id": 1}, {"id": 2}]
    assert session.get.call_args_list[0].kwargs == {"params": {"per_page": "100", **params}}
    session.get.assert_awaited_with(next_url, params=None)


async def test_marker_on_later_page_prevents_duplicate_comment():
    session = AsyncMock()
    session.get.side_effect = [
        response([{"id": 1, "body": "other"}], "https://api.github.com/comments?page=2"),
        response([{"id": 2, "body": "<!-- marker -->"}]),
    ]
    with patch("tracktolib.gh.client.niquests.AsyncSession", return_value=session):
        client = GitHubClient(token="test")
        assert await client.create_idempotent_comment("org/repo", 1, "new", "<!-- marker -->") is None
    session.post.assert_not_awaited()


async def test_deployment_cleanup_includes_later_pages():
    session = AsyncMock()
    session.get.side_effect = [
        response([{"id": 1}], "https://api.github.com/deployments?page=2&environment=preview"),
        response([{"id": 2}]),
    ]
    session.post.return_value = response({"state": "inactive"})
    with patch("tracktolib.gh.client.niquests.AsyncSession", return_value=session):
        client = GitHubClient(token="test")
        assert await client.mark_deployment_inactive("org/repo", "preview") == 2
    assert [call.args[0] for call in session.post.call_args_list] == [
        "/repos/org/repo/deployments/1/statuses",
        "/repos/org/repo/deployments/2/statuses",
    ]
