from contextlib import nullcontext
from unittest.mock import AsyncMock, Mock

import pytest

from tracktolib.notion.fetch import create_page, fetch_database, fetch_search, query_database


def session_with_response(payload):
    response = Mock()
    response.json.return_value = payload
    session = Mock()
    session.headers = {"Notion-Version": "2022-06-28"}
    session.get = AsyncMock(return_value=response)
    session.post = AsyncMock(return_value=response)
    return session


@pytest.mark.parametrize(
    "parent,version,sources,expected,error",
    [
        pytest.param(
            {"database_id": "db"},
            "2025-09-03",
            [{"id": "source"}],
            {"data_source_id": "source"},
            None,
            id="resolve-database",
        ),
        pytest.param(
            {"data_source_id": "source"}, "2025-09-03", [], {"data_source_id": "source"}, None, id="explicit-source"
        ),
        pytest.param({"database_id": "db"}, "2022-06-28", [], {"database_id": "db"}, None, id="legacy-database"),
        pytest.param({"page_id": "page"}, "2025-09-03", [], {"page_id": "page"}, None, id="page-parent"),
        pytest.param(
            {"data_source_id": "source"}, "2022-06-28", [], None, "requires Notion API", id="legacy-source-rejected"
        ),
        pytest.param({"database_id": "db"}, "2025-09-03", [], None, "exactly one data source", id="no-sources"),
        pytest.param(
            {"database_id": "db"},
            "2025-09-03",
            [{"id": "one"}, {"id": "two"}],
            None,
            "exactly one data source",
            id="ambiguous-sources",
        ),
        pytest.param(
            {"database_id": "db", "data_source_id": "source"},
            "2025-09-03",
            [],
            None,
            "exactly one of",
            id="conflicting-parent-identifiers",
        ),
    ],
)
async def test_create_page_resolves_parent_identifiers(parent, version, sources, expected, error):
    session = session_with_response({"data_sources": sources})
    original = parent.copy()
    with pytest.raises(ValueError, match=error) if error else nullcontext():
        await create_page(session, parent=parent, properties={}, api_version=version)
    assert parent == original
    assert session.headers == {"Notion-Version": "2022-06-28"}
    if error:
        session.post.assert_not_awaited()
    else:
        assert session.post.call_args.kwargs == {
            "json": {"parent": expected, "properties": {}},
            "headers": {"Notion-Version": version},
        }
    if parent == {"database_id": "db"} and version == "2025-09-03":
        session.get.assert_awaited_once_with(
            "https://api.notion.com/v1/databases/db",
            headers={"Notion-Version": version},
        )
    else:
        session.get.assert_not_awaited()


@pytest.mark.parametrize(
    "version,endpoint,identifier",
    [
        pytest.param("2022-06-28", "databases", "db", id="legacy"),
        pytest.param("2025-09-03", "data_sources", "source", id="modern"),
    ],
)
@pytest.mark.parametrize(
    "fetch",
    [
        pytest.param(fetch_database, id="fetch"),
        pytest.param(query_database, id="query"),
    ],
)
async def test_database_calls_preserve_identifier_and_override_header(fetch, version, endpoint, identifier):
    session = session_with_response({})
    session.headers["Notion-Version"] = "2022-06-28" if version == "2025-09-03" else "2025-09-03"
    await fetch(session, identifier, api_version=version)
    call = session.get.call_args if fetch is fetch_database else session.post.call_args
    suffix = "" if fetch is fetch_database else "/query"
    assert call.args == (f"https://api.notion.com/v1/{endpoint}/{identifier}{suffix}",)
    assert call.kwargs["headers"] == {"Notion-Version": version}


async def test_search_filter_and_header_use_same_version():
    session = session_with_response({})
    await fetch_search(session, filter={"value": "database", "property": "object"}, api_version="2025-09-03")
    assert session.post.call_args.kwargs == {
        "json": {"filter": {"value": "data_source", "property": "object"}},
        "headers": {"Notion-Version": "2025-09-03"},
    }


async def test_parent_lookup_failure_prevents_page_creation():
    session = session_with_response({})
    session.get.return_value.raise_for_status.side_effect = RuntimeError("lookup failed")
    with pytest.raises(RuntimeError, match="lookup failed"):
        await create_page(session, parent={"database_id": "db"}, properties={}, api_version="2025-09-03")
    session.post.assert_not_awaited()
