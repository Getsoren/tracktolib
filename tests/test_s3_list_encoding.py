from unittest.mock import AsyncMock, Mock

import pytest

from tracktolib.s3.niquests import s3_list_files


@pytest.mark.parametrize(
    ("encoding", "expected"),
    [
        pytest.param("", "a%2Fb+c%2520", id="literal-key"),
        pytest.param("<EncodingType>url</EncodingType>", "a/b+c%20", id="url-encoded-key"),
    ],
)
async def test_listing_preserves_key_identity(encoding: str, expected: str):
    s3 = Mock()
    s3.meta.service_model.api_version = "2006-03-01"
    response = Mock()
    response.content = (
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"{encoding}<Contents><Key>a%2Fb+c%2520</Key><Size>1</Size></Contents></ListBucketResult>"
    ).encode()
    response.raise_for_status.return_value = response
    client = Mock(get=AsyncMock(return_value=response))

    objects = [obj async for obj in s3_list_files(s3, client, "bucket", "")]

    assert objects[0]["Key"] == expected
