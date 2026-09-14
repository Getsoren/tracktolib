from unittest.mock import AsyncMock, Mock, patch

import pytest

from tracktolib.notion.utils import _fetch_all_comments, download_page_to_markdown, fetch_all_page_comments


def comment(identifier, block_id):
    return {
        "id": identifier,
        "discussion_id": "discussion",
        "parent": {"block_id": block_id},
        "created_by": {"id": "user"},
        "created_time": "2026-09-14T00:00:00Z",
        "rich_text": [{"type": "text", "plain_text": identifier, "text": {"content": identifier}}],
    }


@pytest.mark.parametrize(
    "blocks",
    [
        pytest.param([], id="empty-page"),
        pytest.param(
            [{"id": "block", "type": "paragraph"}],
            id="page-with-block",
        ),
    ],
)
async def test_page_comments_include_page_and_paginated_block_comments(blocks):
    async def fetch(session, block_id, *, start_cursor=None):
        return {
            "results": [comment(f"{block_id}-{start_cursor or 'first'}", block_id)],
            "has_more": start_cursor is None,
            "next_cursor": "second" if start_cursor is None else None,
        }

    cache = Mock()
    cache.get_page_comments.return_value = None
    with (
        patch("tracktolib.notion.utils.fetch_all_page_blocks", AsyncMock(return_value=blocks)),
        patch("tracktolib.notion.utils.fetch_comments", side_effect=fetch) as fetch_mock,
        patch("tracktolib.notion.utils.fetch_user", AsyncMock(return_value={"name": "Author"})),
    ):
        result = await fetch_all_page_comments(Mock(), "page", cache=cache)
    assert [item["id"] for item in result] == ["page-first", "page-second"] + (
        ["block-first", "block-second"] if blocks else []
    )
    assert all(item["author_name"] == "Author" for item in result)
    assert result[0]["block_type"] == "page"
    assert fetch_mock.await_count == 2 * (1 + len(blocks))
    cache.set_page_comments.assert_called_once_with("page", result)


async def test_markdown_export_includes_later_comment_pages(tmp_path):
    responses = [
        {"results": [comment("first", "page")], "has_more": True, "next_cursor": "next"},
        {"results": [comment("second", "page")], "has_more": False, "next_cursor": None},
    ]
    output = tmp_path / "page.md"
    with (
        patch("tracktolib.notion.utils.fetch_block_children", AsyncMock(return_value={"results": []})),
        patch("tracktolib.notion.utils.fetch_comments", AsyncMock(side_effect=responses)) as fetch_mock,
        patch("tracktolib.notion.utils.fetch_user", AsyncMock(return_value={"name": "Author"})),
    ):
        await download_page_to_markdown(Mock(), "page", output, include_comments=True)
    assert "first" in output.read_text()
    assert "second" in output.read_text()
    assert fetch_mock.call_args.kwargs == {"start_cursor": "next"}


async def test_comments_reject_missing_continuation_cursor():
    with patch("tracktolib.notion.utils.fetch_comments", AsyncMock(return_value={"results": [], "has_more": True})):
        with pytest.raises(ValueError, match="next_cursor"):
            await _fetch_all_comments(Mock(), "page")
