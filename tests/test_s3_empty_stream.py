from unittest.mock import AsyncMock, Mock

import pytest

from tracktolib.s3.niquests import s3_file_upload


@pytest.mark.parametrize(
    "chunks",
    [pytest.param([], id="empty-iterator"), pytest.param([b"", b""], id="empty-chunks")],
)
async def test_unknown_length_empty_stream_creates_zero_byte_object(chunks: list[bytes]):
    s3 = Mock()
    s3.meta.service_model.api_version = "2006-03-01"
    s3.generate_presigned_url.side_effect = lambda **kwargs: kwargs["ClientMethod"]
    response = Mock(
        content=(
            b'<InitiateMultipartUploadResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            b"<UploadId>upload-id</UploadId></InitiateMultipartUploadResult>"
        )
    )
    response.raise_for_status.return_value = response
    client = Mock(
        post=AsyncMock(return_value=response),
        put=AsyncMock(return_value=response),
        delete=AsyncMock(return_value=response),
    )

    async def stream():
        for chunk in chunks:
            yield chunk

    await s3_file_upload(s3, client, "bucket", "empty", stream(), content_type="text/plain")

    client.post.assert_awaited_once()
    client.delete.assert_awaited_once_with("abort_multipart_upload")
    client.put.assert_awaited_once_with("put_object", data=b"", headers={"Content-Type": "text/plain"}, hooks=None)
