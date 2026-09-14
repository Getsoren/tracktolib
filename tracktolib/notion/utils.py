"""Notion utility functions for exporting and importing content."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast

import niquests

from .markdown import (
    blocks_to_markdown_with_comments,
    comments_to_markdown,
    markdown_to_blocks,
    strip_comments_from_markdown,
)

if TYPE_CHECKING:
    from .cache import NotionCache
    from .models import Block, Comment, PartialBlock

from ..utils import get_chunks, run_coros
from .blocks import (
    ExportResult,
    find_divergence_index,
)
from .fetch import (
    create_comment,
    create_page,
    delete_block,
    fetch_append_block_children,
    fetch_block_children,
    fetch_comments,
    fetch_user,
)

__all__ = [
    "DEFAULT_CONCURRENCY",
    "ClearResult",
    "PageComment",
    "ProgressCallback",
    "UpdateResult",
    "clear_page_blocks",
    "download_page_to_markdown",
    "export_markdown_to_page",
    "fetch_all_page_blocks",
    "fetch_all_page_comments",
    "update_page_content",
]


class ProgressCallback(Protocol):
    """Protocol for progress callback functions."""

    def __call__(self, current: int, total: int | None) -> None:
        """Called after each operation to report progress.

        Args:
            current: Number of items processed so far
            total: Total number of items to process, or None if unknown (e.g., during fetch)
        """
        ...


class ClearResult(TypedDict):
    """Result of clearing page blocks."""

    deleted: int
    """Number of blocks deleted."""


class PageComment(TypedDict):
    """Comment with block context."""

    id: str
    """Comment ID."""
    discussion_id: str
    """Discussion thread ID."""
    block_id: str
    """ID of the block this comment is attached to."""
    block_type: str
    """Type of the block (e.g., 'paragraph', 'code')."""
    author_name: str
    """Name of the comment author."""
    created_time: str
    """ISO 8601 timestamp when the comment was created."""
    text: str
    """Plain text content of the comment."""


class UpdateResult(TypedDict):
    """Result of updating page content."""

    preserved: int
    """Number of blocks preserved (unchanged from prefix)."""
    deleted: int
    """Number of blocks deleted."""
    created: int
    """Number of new blocks created."""


NOTION_BLOCK_LIMIT = 100
"""Maximum number of blocks per Notion API request."""

DEFAULT_CONCURRENCY = 50
"""Default concurrency limit for parallel API requests."""


async def export_markdown_to_page(
    session: niquests.AsyncSession,
    *,
    database_id: str,
    content: str,
    title: str,
    properties: dict[str, Any] | None = None,
    comments: list[str] | None = None,
) -> ExportResult:
    """Export markdown content to a Notion database as a new page.

    Handles large documents by chunking blocks (Notion API limit: 100 blocks per request).

    Args:
        session: Authenticated niquests session with Notion headers
        database_id: ID of the Notion database to create the page in
        content: Markdown content to convert to Notion blocks
        title: Page title (Name property)
        properties: Additional page properties (optional)
        comments: List of comment strings to add to the page (optional)

    Returns:
        ExportResult with count of blocks created and page URL
    """
    if not content.strip():
        return {"count": 0, "url": None}

    all_blocks = markdown_to_blocks(content)

    # Build properties with title
    page_properties: dict[str, Any] = {
        "Name": {"title": [{"text": {"content": title}}]},
    }
    if properties:
        page_properties.update(properties)

    # Create page with first chunk of blocks (max 100)
    first_chunk = all_blocks[:NOTION_BLOCK_LIMIT]
    page = await create_page(
        session,
        parent={"database_id": database_id},
        properties=page_properties,
        children=first_chunk,
    )

    url = page.get("url") if page else None
    page_id = page.get("id") if page else None

    # Append remaining blocks in chunks
    if page_id and len(all_blocks) > NOTION_BLOCK_LIMIT:
        remaining_blocks = all_blocks[NOTION_BLOCK_LIMIT:]
        for i in range(0, len(remaining_blocks), NOTION_BLOCK_LIMIT):
            chunk = remaining_blocks[i : i + NOTION_BLOCK_LIMIT]
            await fetch_append_block_children(session, page_id, chunk)

    # Add comments if provided
    if comments and page_id:
        for comment_text in comments:
            await create_comment(
                session,
                parent={"page_id": page_id},
                rich_text=[{"type": "text", "text": {"content": comment_text}}],
            )

    return {"count": len(all_blocks), "url": url}


async def download_page_to_markdown(
    session: niquests.AsyncSession,
    page_id: str,
    output_path: str | Path,
    *,
    include_comments: bool = False,
    semaphore: asyncio.Semaphore | None = None,
    on_progress: ProgressCallback | None = None,
) -> int:
    """Download a Notion page to a local markdown file.

    Uses TaskGroup with Semaphore for parallel fetching of comments.

    Args:
        session: Authenticated niquests session with Notion headers
        page_id: ID of the Notion page to download
        output_path: Path to save the markdown file
        include_comments: Whether to include comments (both page-level and inline block comments)
        semaphore: Optional semaphore for rate limiting (default: Semaphore(50))
        on_progress: Optional callback called after each batch of blocks is fetched.
            Receives (current, total) where total is None (unknown during fetch).

    Returns:
        Number of blocks converted
    """
    # Fetch all blocks from the page
    all_blocks: list[Block | PartialBlock] = []
    cursor: str | None = None

    while True:
        response = await fetch_block_children(session, page_id, start_cursor=cursor)
        all_blocks.extend(response.get("results", []))

        has_more = response.get("has_more", False)
        if on_progress:
            on_progress(len(all_blocks), None)

        if not has_more:
            break
        cursor = response.get("next_cursor")

    # Fetch comments if requested
    block_comments: dict[str, list[Comment]] = {}
    page_comments: list[Comment] = []

    if include_comments:
        # Collect all block IDs to fetch comments for (including page itself)
        block_ids = [page_id] + [b.get("id") for b in all_blocks if b.get("id")]

        # Fetch comments in parallel
        sem = semaphore or asyncio.Semaphore(DEFAULT_CONCURRENCY)
        block_id_to_comments: dict[str, list[Comment]] = {}
        user_ids: set[str] = set()

        async def fetch_block_comments(bid: str) -> tuple[str, list[Comment]]:
            comments_list = await _fetch_all_comments(session, bid)
            if comments_list:
                # Use actual parent block_id from comment to avoid race condition
                actual_block_id = comments_list[0].get("parent", {}).get("block_id", bid)
                return actual_block_id, comments_list
            return bid, []

        async for actual_block_id, comments_list in run_coros((fetch_block_comments(bid) for bid in block_ids), sem):
            if comments_list:
                block_id_to_comments[actual_block_id] = comments_list
                for comment in comments_list:
                    user_id = comment.get("created_by", {}).get("id")
                    if user_id:
                        user_ids.add(user_id)

        # Fetch all user names in parallel
        user_cache: dict[str, str] = {}

        async for uid, name in run_coros((_fetch_user_with_id(session, uid) for uid in user_ids), sem):
            user_cache[uid] = name

        # Apply user names to comments
        for comments_list in block_id_to_comments.values():
            for comment in comments_list:
                created_by = cast(dict[str, Any], comment.get("created_by", {}))
                uid = created_by.get("id")
                if uid and uid in user_cache:
                    created_by["name"] = user_cache[uid]

        # Separate page comments from block comments
        page_comments = block_id_to_comments.pop(page_id, [])
        block_comments = block_id_to_comments

    # Convert blocks to markdown with inline comments
    markdown_content = blocks_to_markdown_with_comments(all_blocks, block_comments)

    # Append page-level comments at the end
    if page_comments:
        comments_md = comments_to_markdown(page_comments)
        markdown_content = f"{markdown_content}\n\n{comments_md}"

    # Write to file with trailing newline
    output = Path(output_path)
    output.write_text(f"{markdown_content}\n", encoding="utf-8")

    return len(all_blocks)


async def clear_page_blocks(
    session: niquests.AsyncSession,
    page_id: str,
    *,
    cache: NotionCache | None = None,
    semaphore: asyncio.Semaphore | None = None,
    on_progress: ProgressCallback | None = None,
) -> ClearResult:
    """Delete all blocks from a Notion page.

    Uses TaskGroup for parallel deletion with Semaphore for rate limiting.
    Default concurrency is 50 if no semaphore is provided.

    Args:
        session: Authenticated niquests session with Notion headers
        page_id: ID of the Notion page to clear
        cache: Optional cache to invalidate after clearing
        semaphore: Optional semaphore for rate limiting (default: Semaphore(50))
        on_progress: Optional callback called after each block is deleted.
            Receives (deleted_count, total_count).

    Returns:
        ClearResult with count of blocks deleted
    """
    # First, fetch all blocks to get the total count
    all_block_ids: list[str] = []
    cursor: str | None = None

    while True:
        response = await fetch_block_children(session, page_id, start_cursor=cursor)
        blocks = response.get("results", [])
        for block in blocks:
            block_id = block.get("id")
            if block_id:
                all_block_ids.append(block_id)

        if not response.get("has_more", False):
            break
        cursor = response.get("next_cursor")

    if not all_block_ids:
        if cache:
            cache.delete_page_blocks(page_id)
        return {"deleted": 0}

    total = len(all_block_ids)
    deleted_count = 0
    sem = semaphore or asyncio.Semaphore(DEFAULT_CONCURRENCY)

    async def delete_one(block_id: str) -> None:
        nonlocal deleted_count
        async with sem:
            await delete_block(session, block_id)
        deleted_count += 1
        if on_progress:
            on_progress(deleted_count, total)

    async with asyncio.TaskGroup() as tg:
        for block_id in all_block_ids:
            tg.create_task(delete_one(block_id))

    if cache:
        cache.delete_page_blocks(page_id)

    return {"deleted": deleted_count}


async def fetch_all_page_blocks(
    session: niquests.AsyncSession,
    page_id: str,
    *,
    cache: NotionCache | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[Block | PartialBlock]:
    """Fetch all blocks from a Notion page.

    Args:
        session: Authenticated niquests session with Notion headers
        page_id: ID of the Notion page
        cache: Optional cache to read from and write to
        on_progress: Optional callback called after each batch of blocks is fetched.
            Receives (fetched_count, None) since total is unknown during fetch.

    Returns:
        List of all blocks in the page
    """
    # Try cache first
    if cache:
        cached = cache.get_page_blocks(page_id)
        if cached is not None:
            return cached  # type: ignore[return-value]

    # Fetch from API
    all_blocks: list[Block | PartialBlock] = []
    cursor: str | None = None

    while True:
        response = await fetch_block_children(session, page_id, start_cursor=cursor)
        all_blocks.extend(response.get("results", []))

        if on_progress:
            on_progress(len(all_blocks), None)

        if not response.get("has_more", False):
            break
        cursor = response.get("next_cursor")

    # Update cache
    if cache:
        cache.set_page_blocks(page_id, all_blocks)  # type: ignore[arg-type]

    return all_blocks


async def _fetch_all_comments(session: niquests.AsyncSession, block_id: str) -> list[Comment]:
    """Fetch every comments page for a page or block."""
    comments: list[Comment] = []
    cursor: str | None = None
    while True:
        response = await fetch_comments(session, block_id, start_cursor=cursor)
        comments.extend(response.get("results", []))
        if not response.get("has_more", False):
            return comments
        cursor = response.get("next_cursor")
        if not cursor:
            raise ValueError("Notion comments response has_more without next_cursor")


async def _fetch_block_comments(
    session: niquests.AsyncSession, block: Block | PartialBlock
) -> list[tuple[str, str, Comment]]:
    block_id = block.get("id", "")
    block_type = block.get("type", "unknown")
    comments = await _fetch_all_comments(session, block_id)
    return [(block_id, block_type, c) for c in comments]


async def _fetch_user_with_id(session: niquests.AsyncSession, uid: str) -> tuple[str, str]:
    user = await fetch_user(session, uid)
    return uid, user.get("name") or uid


async def fetch_all_page_comments(
    session: niquests.AsyncSession,
    page_id: str,
    *,
    cache: NotionCache | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[PageComment]:
    """Fetch all comments from a page and its blocks.

    Args:
        session: Authenticated niquests session with Notion headers
        page_id: The page to fetch comments from
        cache: Optional cache to read from and write to
        concurrency: Max concurrent requests (default 50)

    Returns:
        List of comments with block context, ordered by block position
    """
    # Try cache first
    if cache:
        cached = cache.get_page_comments(page_id)
        if cached is not None:
            return cached

    blocks = await fetch_all_page_blocks(session, page_id, cache=cache)
    sem = asyncio.Semaphore(concurrency)

    # Fetch comments for all blocks
    raw_comments: list[tuple[str, str, Comment]] = [
        (page_id, "page", c) for c in await _fetch_all_comments(session, page_id)
    ]
    user_ids: set[str] = {uid for _, _, c in raw_comments if (uid := c.get("created_by", {}).get("id"))}

    async for result in run_coros((_fetch_block_comments(session, b) for b in blocks), sem):
        for block_id, block_type, c in result:
            raw_comments.append((block_id, block_type, c))
            user_id = c.get("created_by", {}).get("id")
            if user_id:
                user_ids.add(user_id)

    # Fetch user names in parallel
    user_ids_list = list(user_ids)
    user_cache: dict[str, str] = {}

    async for uid, name in run_coros((_fetch_user_with_id(session, uid) for uid in user_ids_list), sem):
        user_cache[uid] = name

    # Build final comments with resolved user names
    comments: list[PageComment] = []
    for block_id, block_type, c in raw_comments:
        user_id = c.get("created_by", {}).get("id", "")
        author_name = user_cache.get(user_id, "Unknown")
        comments.append(
            {
                "id": c["id"],
                "discussion_id": c["discussion_id"],
                "block_id": block_id,
                "block_type": block_type,
                "author_name": author_name,
                "created_time": c["created_time"],
                "text": "".join(rt.get("plain_text", "") for rt in c.get("rich_text", [])),
            }
        )

    # Update cache
    if cache:
        cache.set_page_comments(page_id, comments)

    return comments


async def update_page_content(
    session: niquests.AsyncSession,
    page_id: str,
    content: str,
    *,
    cache: NotionCache | None = None,
    semaphore: asyncio.Semaphore | None = None,
    on_progress: ProgressCallback | None = None,
) -> UpdateResult:
    """Update a Notion page using smart prefix-preserving diff.

    Only deletes and recreates blocks that have changed, preserving:
    - Block IDs for unchanged blocks
    - Inline comments attached to unchanged blocks
    - Reduces API calls for edits at the end of documents

    Uses TaskGroup for parallel deletion with Semaphore for rate limiting.
    Default concurrency is 50 if no semaphore is provided.

    Comment blockquotes (> 💬) are automatically stripped from the content
    to preserve existing comments on the page.

    Args:
        session: Authenticated niquests session with Notion headers
        page_id: ID of the Notion page to update
        content: Markdown content to replace the page content with
        cache: Optional cache for existing blocks (avoids fetch if cached)
        semaphore: Optional semaphore for rate limiting (default: Semaphore(50))
        on_progress: Optional callback called after each block is deleted.
            Receives (deleted_count, total_to_delete).

    Returns:
        UpdateResult with counts of preserved, deleted, and created blocks
    """
    content = strip_comments_from_markdown(content)

    # Handle empty content
    if not content.strip():
        result = await clear_page_blocks(session, page_id, cache=cache, semaphore=semaphore, on_progress=on_progress)
        return {"preserved": 0, "deleted": result["deleted"], "created": 0}

    new_blocks = markdown_to_blocks(content)

    # Fetch existing blocks (from cache or API)
    existing_blocks = await fetch_all_page_blocks(session, page_id, cache=cache)

    # Find where content diverges
    divergence_idx = find_divergence_index(existing_blocks, new_blocks)

    # Count preserved blocks
    preserved = divergence_idx

    # Delete blocks from divergence point onward
    blocks_to_delete = existing_blocks[divergence_idx:]
    block_ids_to_delete = [b.get("id") for b in blocks_to_delete if b.get("id")]
    total_to_delete = len(block_ids_to_delete)
    deleted_count = 0

    if block_ids_to_delete:
        sem = semaphore or asyncio.Semaphore(DEFAULT_CONCURRENCY)

        async def delete_one(block_id: str) -> None:
            nonlocal deleted_count
            async with sem:
                await delete_block(session, block_id)
            deleted_count += 1
            if on_progress:
                on_progress(deleted_count, total_to_delete)

        async with asyncio.TaskGroup() as tg:
            for block_id in block_ids_to_delete:
                tg.create_task(delete_one(block_id))

    # Append new blocks from divergence point onward
    blocks_to_create = new_blocks[divergence_idx:]
    created = 0
    if blocks_to_create:
        # Notion's append API adds to the end, which is what we want
        # since we deleted everything after the preserved blocks
        for chunk in get_chunks(blocks_to_create, NOTION_BLOCK_LIMIT):
            await fetch_append_block_children(session, page_id, chunk)
            created += len(chunk)

    # Update cache with the new state
    if cache:
        # Build the new block list: preserved blocks + newly created
        # Note: newly created blocks don't have IDs yet, so we need to refetch
        # or we can just invalidate the cache
        cache.delete_page_blocks(page_id)

    return {"preserved": preserved, "deleted": deleted_count, "created": created}
