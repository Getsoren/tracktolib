import json
import subprocess
import sys
from contextlib import nullcontext

import pytest

from tracktolib.utils import rm_keys


@pytest.mark.parametrize(
    "data, expected, error",
    [
        pytest.param({"secret": None, "public": 1}, {"public": 1}, None, id="null-value"),
        pytest.param([{"secret": 1}, {"secret": None}], [{}, {}], None, id="multiple-records"),
        pytest.param({"public": 1}, None, KeyError, id="missing-key"),
    ],
)
def test_remove_keys(data, expected, error):
    with pytest.raises(error) if error else nullcontext():
        assert rm_keys(data, ["secret"]) == expected


def test_remove_keys_under_optimized_python():
    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "import json; from tracktolib.utils import rm_keys; "
            "print(json.dumps(rm_keys({'secret': 'value', 'public': 1}, ['secret'])))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {"public": 1}
