from asyncio import CancelledError
from contextlib import nullcontext
from unittest.mock import AsyncMock, Mock

import pytest
from botocore.exceptions import ClientError
from niquests.exceptions import HTTPError

from tracktolib.s3.niquests import s3_multipart_upload


@pytest.mark.parametrize(
    ("body", "abort_fails", "error"),
    [
        pytest.param(b"<CompleteMultipartUploadResult/>", False, None, id="success"),
        pytest.param(b"<Error><Code>InternalError</Code></Error>", False, ClientError, id="embedded-error"),
        pytest.param(
            b'<Error xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Code>InternalError</Code></Error>',
            False,
            ClientError,
            id="namespaced-error",
        ),
        pytest.param(b"<Error><Code>InternalError</Code></Error>", True, ClientError, id="abort-also-fails"),
        pytest.param(b"", False, HTTPError, id="http-completion-failure"),
        pytest.param(b"", False, CancelledError, id="cancelled-upload"),
    ],
)
async def test_completion_error_is_raised_and_upload_aborted(
    body: bytes, abort_fails: bool, error: type[BaseException] | None
):
    s3 = Mock()
    s3.meta.service_model.api_version = "2006-03-01"
    s3.generate_presigned_url.side_effect = lambda **kwargs: kwargs["ClientMethod"]
    create = Mock(
        content=(
            b'<InitiateMultipartUploadResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            b"<UploadId>upload-id</UploadId></InitiateMultipartUploadResult>"
        )
    )
    complete = Mock(content=body)
    part = Mock(headers={"ETag": "etag"})
    for response in (create, complete, part):
        response.raise_for_status.return_value = response
    if error is HTTPError:
        complete.raise_for_status.side_effect = HTTPError("completion failed")
    client = Mock(
        post=AsyncMock(side_effect=[create, complete]),
        put=AsyncMock(return_value=part),
        delete=AsyncMock(return_value=Mock()),
    )
    if abort_fails:
        client.delete.side_effect = RuntimeError("abort failed")

    with pytest.raises(error) if error else nullcontext():
        async with s3_multipart_upload(s3, client, "bucket", "key") as upload:
            await upload.fetch_create()
            await upload.upload_part(b"contents")
            if error is CancelledError:
                raise CancelledError()

    assert client.delete.await_count == int(error is not None)
    if error:
        client.delete.assert_awaited_once_with("abort_multipart_upload")
    assert client.post.await_count == (1 if error is CancelledError else 2)
