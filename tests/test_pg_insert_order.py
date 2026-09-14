from contextlib import nullcontext

import pytest

from tracktolib.pg_sync import get_insert_data


@pytest.mark.parametrize(
    "row, expected, error",
    [
        pytest.param({"b": 3, "a": 4}, [(1, 2), (4, 3)], nullcontext(), id="reordered"),
        pytest.param({"a": 4}, None, pytest.raises(ValueError, match="Inconsistent columns"), id="missing"),
        pytest.param({"a": 4, "c": 3}, None, pytest.raises(ValueError, match="Inconsistent columns"), id="different"),
        pytest.param(
            {"a": 4, "b": 3, "c": 5}, None, pytest.raises(ValueError, match="Inconsistent columns"), id="extra"
        ),
    ],
)
def test_insert_column_order(row, expected, error):
    with error:
        query, values = get_insert_data("example", [{"a": 1, "b": 2}, row])
        assert query == "INSERT INTO example as t (a,b) VALUES (%s,%s)"
        assert values == expected
