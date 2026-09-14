from unittest.mock import AsyncMock

import pytest

from tracktolib.pg.query import update_returning


@pytest.mark.parametrize(
    "where, keys, expected, values",
    [
        pytest.param(None, None, "RETURNING id, value", (1, 2), id="unfiltered"),
        pytest.param("WHERE active", None, "RETURNING id, value", (1, 2), id="custom-where"),
        pytest.param(None, ["id"], "RETURNING value", (2, 1), id="where-key"),
    ],
)
async def test_update_return_keys(where, keys, expected, values):
    conn = AsyncMock()
    result = await update_returning(conn, "example", {"id": 1, "value": 2}, return_keys=True, where=where, keys=keys)
    assert result is conn.fetchrow.return_value
    conn.fetchrow.assert_awaited_once()
    query, *args = conn.fetchrow.call_args.args
    assert query.endswith(expected)
    assert tuple(args) == values
    if where:
        assert where in query
