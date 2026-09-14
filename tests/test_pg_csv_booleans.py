from contextlib import nullcontext

import pytest

from tracktolib.pg.utils import _fmt_record_tuple, _get_type


@pytest.mark.parametrize(
    "value, expected, error",
    [
        pytest.param("false", False, nullcontext(), id="false"),
        pytest.param("f", False, nullcontext(), id="f"),
        pytest.param("0", False, nullcontext(), id="zero"),
        pytest.param("NO", False, nullcontext(), id="no"),
        pytest.param("n", False, nullcontext(), id="n"),
        pytest.param("off", False, nullcontext(), id="off"),
        pytest.param("true", True, nullcontext(), id="true"),
        pytest.param("t", True, nullcontext(), id="t"),
        pytest.param("1", True, nullcontext(), id="one"),
        pytest.param("yes", True, nullcontext(), id="yes"),
        pytest.param("y", True, nullcontext(), id="y"),
        pytest.param(" ON ", True, nullcontext(), id="whitespace"),
        pytest.param("", None, nullcontext(), id="empty"),
        pytest.param("-", None, nullcontext(), id="null-marker"),
        pytest.param(None, None, nullcontext(), id="null"),
        pytest.param("maybe", None, pytest.raises(ValueError, match="Invalid boolean"), id="invalid"),
    ],
)
def test_csv_boolean(value, expected, error):
    with error:
        result = _fmt_record_tuple({"enabled": value}, {"enabled": _get_type("boolean", None)}, ["enabled"])
        assert result == (expected,)
