from unittest.mock import AsyncMock

import pytest

from tracktolib.pg.query import PGUpdateQuery, SQLExpr, insert_pg


@pytest.mark.parametrize(
    "query, expected",
    [
        pytest.param(insert_pg("example", [{"a": 1, "b": 2}], returning=["a"]), (1, 2), id="insert"),
        pytest.param(
            insert_pg("example", [{"a": 1, "b": SQLExpr("10")}, {"a": 2, "b": 3}], returning=["a"]),
            (1, 2, 3),
            id="insert-batch-returning",
        ),
        pytest.param(
            PGUpdateQuery("example", [{"id": 1, "value": 2}], where_keys=["id"], returning=["value"]),
            (2, 1),
            id="update-where-key-last",
        ),
    ],
)
@pytest.mark.parametrize(
    "method",
    [
        pytest.param("fetch", id="fetch"),
        pytest.param("fetchrow", id="fetchrow"),
        pytest.param("fetchval", id="fetchval"),
    ],
)
async def test_fetch_binding(query, expected, method):
    conn = AsyncMock()
    await getattr(query, method)(conn, timeout=5)
    options = {"timeout": 5, "column": 0} if method == "fetchval" else {"timeout": 5}
    getattr(conn, method).assert_awaited_once_with(query.query, *expected, **options)


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(insert_pg("example", [{"a": 1}, {"a": 2}]), id="insert-without-returning"),
        pytest.param(PGUpdateQuery("example", [{"a": 1}, {"a": 2}]), id="update-batch"),
        pytest.param(PGUpdateQuery("example", [{"a": 1}], is_many=True), id="update-executemany"),
    ],
)
async def test_unsupported_batch_fetch(query):
    conn = AsyncMock()
    with pytest.raises(ValueError, match="batch"):
        await query.fetch(conn)
    conn.fetch.assert_not_awaited()
