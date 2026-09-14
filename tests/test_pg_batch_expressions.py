from contextlib import nullcontext

import pytest

from tracktolib.pg.query import PGUpdateQuery, SQLExpr, insert_pg


@pytest.mark.parametrize("kind", [pytest.param("insert", id="insert"), pytest.param("update", id="update")])
@pytest.mark.parametrize(
    "first, second, error",
    [
        pytest.param(SQLExpr("10"), SQLExpr("10"), nullcontext(), id="same-expression"),
        pytest.param(10, 20, nullcontext(), id="bound-values"),
        pytest.param(
            SQLExpr("10"), SQLExpr("20"), pytest.raises(ValueError, match="Inconsistent SQLExpr"), id="different"
        ),
        pytest.param(10, SQLExpr("20"), pytest.raises(ValueError, match="Inconsistent SQLExpr"), id="later-expression"),
        pytest.param(SQLExpr("10"), 20, pytest.raises(ValueError, match="Inconsistent SQLExpr"), id="later-value"),
    ],
)
def test_batch_expressions(kind, first, second, error):
    items = [{"id": 1, "value": first}, {"id": 2, "value": second}]
    with error:
        query = insert_pg("example", items) if kind == "insert" else PGUpdateQuery("example", items, where_keys=["id"])
        assert query.query
        assert len(query.values) == 2


def test_returning_insert_preserves_distinct_expressions():
    query = insert_pg("example", [{"value": SQLExpr("10")}, {"value": SQLExpr("20")}], returning=["value"])
    assert "VALUES (10), (20)" in query.query
    assert query._get_flat_values() == []
