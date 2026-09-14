from dataclasses import dataclass
from typing import Any

import pytest

from tracktolib.api import JSONSerialResponse


@dataclass
class Value:
    number: int


def serialize_value(value: Any) -> str:
    if isinstance(value, Value):
        return str(value.number)
    raise TypeError(f"Unsupported value: {type(value)}")


class CustomResponse(JSONSerialResponse):
    json_serial = serialize_value


@pytest.mark.parametrize(
    "response_type, expected",
    [
        pytest.param(JSONSerialResponse, b'{"value":{"number":1}}', id="default-serializer"),
        pytest.param(CustomResponse, b'{"value":"1"}', id="custom-serializer"),
    ],
)
def test_json_response_serializer(response_type, expected):
    assert response_type({"value": Value(1)}).body == expected
