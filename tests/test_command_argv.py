import sys

import pytest

from tracktolib.utils import aexec_cmd, exec_cmd


@pytest.mark.parametrize(
    "is_async",
    [pytest.param(False, id="sync"), pytest.param(True, id="async")],
)
@pytest.mark.parametrize(
    "cmd, expected",
    [
        pytest.param(
            [sys.executable, "-c", "import sys; print(sys.argv[1], end='')", "a b; $(printf injected)"],
            "a b; $(printf injected)",
            id="literal-argv",
        ),
        pytest.param("printf '%s' 'hello world'", "hello world", id="shell-string"),
    ],
)
async def test_command_arguments(is_async, cmd, expected):
    output = await aexec_cmd(cmd) if is_async else exec_cmd(cmd)
    assert output == expected
