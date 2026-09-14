from __future__ import annotations

import datetime as dt
import hashlib
import http
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Literal, NamedTuple, Required, Self, TypedDict, Unpack
from urllib.parse import unquote
from xml.sax.saxutils import escape as xml_escape

try:
    import botocore.client
    import botocore.session
    import jmespath
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.config import Config
    from botocore.exceptions import ClientError
except ImportError as e:
    raise ImportError("botocore is required for S3 operations. Install with tracktolib[s3-niquests]") from e

try:
    import niquests
except ImportError as e:
    raise ImportError("niquests is required for S3 operations. Install with tracktolib[s3-niquests]") from e

import json

from ..utils import get_stream_chunk

__all__ = (
    "OnUpload",
    "S3MultipartUpload",
    "S3Object",
    "S3ObjectParams",
    "S3Session",
    "SyncResult",
    "UploadPart",
    "build_s3_headers",
    "build_s3_presigned_params",
    "s3_create_multipart_upload",
    "s3_delete_bucket_policy",
    "s3_delete_bucket_website",
    "s3_delete_object",
    "s3_delete_objects",
    "s3_download_file",
    "s3_empty_bucket",
    "s3_file_upload",
    "s3_get_bucket_policy",
    "s3_get_object",
    "s3_list_files",
    "s3_multipart_upload",
    "s3_put_bucket_policy",
    "s3_put_bucket_website",
    "s3_put_object",
    "s3_sync_directory",
    "s3_upload_file",
)

ACL = Literal[
    "private",
    "public-read",
    "public-read-write",
    "authenticated-read",
    "aws-exec-read",
    "bucket-owner-read",
    "bucket-owner-full-control",
]

StorageClass = Literal[
    "STANDARD",
    "REDUCED_REDUNDANCY",
    "STANDARD_IA",
    "ONEZONE_IA",
    "INTELLIGENT_TIERING",
    "GLACIER",
    "DEEP_ARCHIVE",
    "OUTPOSTS",
    "GLACIER_IR",
    "EXPRESS_ONEZONE",
]

ServerSideEncryption = Literal["AES256", "aws:kms", "aws:kms:dsse"]


class S3ObjectParams(TypedDict, total=False):
    """
    Parameters for S3 object uploads (PutObject, CreateMultipartUpload).

    See:
    - https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html
    - https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateMultipartUpload.html
    """

    acl: ACL | None
    content_type: str | None
    content_disposition: str | None
    content_encoding: str | None
    content_language: str | None
    cache_control: str | None
    storage_class: StorageClass | None
    server_side_encryption: ServerSideEncryption | None
    sse_kms_key_id: str | None
    tagging: str | None  # URL-encoded key=value pairs
    metadata: dict[str, str] | None  # User-defined metadata (x-amz-meta-*)


def build_s3_headers(params: S3ObjectParams) -> dict[str, str]:
    """
    Build S3 request headers from S3ObjectParams.

    Returns a dict of HTTP headers to include in the request.
    """
    headers: dict[str, str] = {}

    if (acl := params.get("acl")) is not None:
        headers["x-amz-acl"] = acl
    if (content_type := params.get("content_type")) is not None:
        headers["Content-Type"] = content_type
    if (content_disposition := params.get("content_disposition")) is not None:
        headers["Content-Disposition"] = content_disposition
    if (content_encoding := params.get("content_encoding")) is not None:
        headers["Content-Encoding"] = content_encoding
    if (content_language := params.get("content_language")) is not None:
        headers["Content-Language"] = content_language
    if (cache_control := params.get("cache_control")) is not None:
        headers["Cache-Control"] = cache_control
    if (storage_class := params.get("storage_class")) is not None:
        headers["x-amz-storage-class"] = storage_class
    if (sse := params.get("server_side_encryption")) is not None:
        headers["x-amz-server-side-encryption"] = sse
    if (sse_kms_key_id := params.get("sse_kms_key_id")) is not None:
        headers["x-amz-server-side-encryption-aws-kms-key-id"] = sse_kms_key_id
    if (tagging := params.get("tagging")) is not None:
        headers["x-amz-tagging"] = tagging
    if (metadata := params.get("metadata")) is not None:
        for key, value in metadata.items():
            headers[f"x-amz-meta-{key}"] = value

    return headers


def build_s3_presigned_params(bucket: str, key: str, params: S3ObjectParams) -> dict:
    """
    Build parameters dict for botocore generate_presigned_url.

    Maps S3ObjectParams to the Params dict expected by botocore.
    """
    presigned_params: dict = {"Bucket": bucket, "Key": key}

    if (acl := params.get("acl")) is not None:
        presigned_params["ACL"] = acl
    if (content_type := params.get("content_type")) is not None:
        presigned_params["ContentType"] = content_type
    if (content_disposition := params.get("content_disposition")) is not None:
        presigned_params["ContentDisposition"] = content_disposition
    if (content_encoding := params.get("content_encoding")) is not None:
        presigned_params["ContentEncoding"] = content_encoding
    if (content_language := params.get("content_language")) is not None:
        presigned_params["ContentLanguage"] = content_language
    if (cache_control := params.get("cache_control")) is not None:
        presigned_params["CacheControl"] = cache_control
    if (storage_class := params.get("storage_class")) is not None:
        presigned_params["StorageClass"] = storage_class
    if (sse := params.get("server_side_encryption")) is not None:
        presigned_params["ServerSideEncryption"] = sse
    if (sse_kms_key_id := params.get("sse_kms_key_id")) is not None:
        presigned_params["SSEKMSKeyId"] = sse_kms_key_id
    if (tagging := params.get("tagging")) is not None:
        presigned_params["Tagging"] = tagging
    if (metadata := params.get("metadata")) is not None:
        presigned_params["Metadata"] = metadata

    return presigned_params


@dataclass
class S3Session:
    """
    Utility class that wraps botocore S3 client and niquests async session.

    Usage:
        async with S3Session(
            endpoint_url='http://localhost:9000',
            access_key='foo',
            secret_key='bar',
        ) as s3:
            await s3.put_object('my-bucket', 'path/to/file.txt', b'content')
            content = await s3.get_object('my-bucket', 'path/to/file.txt')

        # With custom clients:
        async with S3Session(
            endpoint_url='...',
            access_key='...',
            secret_key='...',
            s3_client=my_s3_client,
            http_client=my_http_session,
        ) as s3:
            ...
    """

    endpoint_url: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    region: str | None = None
    s3_config: Config | None = None
    s3_client: botocore.client.BaseClient | None = None
    http_client: niquests.AsyncSession = field(default_factory=niquests.AsyncSession)
    _botocore_session: botocore.session.Session | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if self.s3_client is None:
            self._botocore_session = botocore.session.Session()
            if self.access_key is not None and self.secret_key is not None:
                self._botocore_session.set_credentials(self.access_key, self.secret_key)
            config = self.s3_config
            if config is None:
                config = Config(signature_version="s3v4")
            self.s3_client = self._botocore_session.create_client(
                "s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                config=config,
            )

    @property
    def _s3(self) -> botocore.client.BaseClient:
        if self.s3_client is None:
            raise ValueError("s3_client not initialized")
        return self.s3_client

    async def __aenter__(self) -> Self:
        await self.http_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.__aexit__(exc_type, exc_val, exc_tb)
        self._s3.close()

    async def delete_object(self, bucket: str, key: str) -> niquests.AsyncResponse:
        """Delete an object from S3."""
        return await s3_delete_object(self._s3, self.http_client, bucket, key)  # pyright: ignore[reportReturnType]

    async def delete_objects(self, bucket: str, keys: list[str]) -> list[niquests.AsyncResponse]:
        """Delete multiple objects from S3."""
        return await s3_delete_objects(self._s3, self.http_client, bucket, keys)  # pyright: ignore[reportReturnType]

    def list_files(
        self,
        bucket: str,
        prefix: str,
        *,
        search_query: str | None = None,
        max_items: int | None = None,
        page_size: int | None = None,
        starting_token: str | None = None,
    ) -> AsyncIterator[S3Object]:
        """List files in an S3 bucket with a given prefix."""
        return s3_list_files(
            self._s3,
            self.http_client,
            bucket,
            prefix,
            search_query=search_query,
            max_items=max_items,
            page_size=page_size,
            starting_token=starting_token,
        )

    async def put_object(
        self, bucket: str, key: str, data: bytes, **kwargs: Unpack[S3ObjectParams]
    ) -> niquests.AsyncResponse:
        """Upload an object to S3."""
        return await s3_put_object(self._s3, self.http_client, bucket, key, data, **kwargs)  # pyright: ignore[reportReturnType]

    async def upload_file(
        self, bucket: str, file: Path, path: str, **kwargs: Unpack[S3ObjectParams]
    ) -> niquests.AsyncResponse:
        """Upload a file to S3."""
        return await s3_upload_file(self._s3, self.http_client, bucket, file, path, **kwargs)  # pyright: ignore[reportReturnType]

    async def get_object(self, bucket: str, key: str) -> bytes | None:
        """Download an object from S3."""
        return await s3_get_object(self._s3, self.http_client, bucket, key)

    async def download_file(
        self,
        bucket: str,
        key: str,
        on_chunk: Callable[[bytes], None] | None = None,
        chunk_size: int = 1024 * 1024,
        on_start: OnDownloadStartFn | None = None,
    ) -> AsyncIterator[bytes]:
        """Download a file from S3 with streaming support."""
        async for chunk in s3_download_file(
            self._s3, self.http_client, bucket, key, chunk_size=chunk_size, on_start=on_start
        ):
            if on_chunk:
                on_chunk(chunk)
            yield chunk

    def multipart_upload(self, bucket: str, key: str, *, expires_in: int = 3600, **kwargs: Unpack[S3ObjectParams]):
        """Create a multipart upload context manager."""
        return s3_multipart_upload(self._s3, self.http_client, bucket, key, expires_in=expires_in, **kwargs)

    async def file_upload(
        self,
        bucket: str,
        key: str,
        data: AsyncIterator[bytes],
        *,
        min_part_size: int = 5 * 1024 * 1024,
        on_upload: OnUpload | None = None,
        content_length: int | None = None,
        **kwargs: Unpack[S3ObjectParams],
    ) -> None:
        """Upload a file to S3 using streaming (multipart for large files)."""
        return await s3_file_upload(
            self._s3,
            self.http_client,
            bucket,
            key,
            data,
            min_part_size=min_part_size,
            on_upload=on_upload,
            content_length=content_length,
            **kwargs,
        )

    async def put_bucket_policy(self, bucket: str, policy: str | dict) -> niquests.AsyncResponse:
        """Set a bucket policy."""
        return await s3_put_bucket_policy(self._s3, self.http_client, bucket, policy, self._botocore_session)  # pyright: ignore[reportReturnType]

    async def get_bucket_policy(self, bucket: str) -> dict | None:
        """Get a bucket policy. Returns None if no policy exists."""
        return await s3_get_bucket_policy(self._s3, self.http_client, bucket)

    async def delete_bucket_policy(self, bucket: str) -> niquests.AsyncResponse:
        """Delete a bucket policy."""
        return await s3_delete_bucket_policy(self._s3, self.http_client, bucket)  # pyright: ignore[reportReturnType]

    async def put_bucket_website(
        self, bucket: str, index_document: str = "index.html", error_document: str | None = None
    ) -> niquests.AsyncResponse:
        """Configure a bucket as a static website."""
        return await s3_put_bucket_website(
            self._s3, self.http_client, bucket, index_document, error_document, self._botocore_session
        )  # pyright: ignore[reportReturnType]

    async def delete_bucket_website(self, bucket: str) -> niquests.AsyncResponse:
        """Remove website configuration from a bucket."""
        return await s3_delete_bucket_website(self._s3, self.http_client, bucket)  # pyright: ignore[reportReturnType]

    async def empty_bucket(self, bucket: str, *, on_progress: Callable[[str], None] | None = None) -> int:
        """Delete all objects from a bucket. Returns count of deleted objects."""
        return await s3_empty_bucket(self._s3, self.http_client, bucket, on_progress=on_progress)

    async def sync_directory(
        self,
        bucket: str,
        local_dir: Path,
        remote_prefix: str = "",
        *,
        delete: bool = False,
        on_upload: Callable[[Path, str], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_skip: Callable[[Path, str], None] | None = None,
        **kwargs: Unpack[S3ObjectParams],
    ) -> SyncResult:
        """
        Sync a local directory to an S3 bucket prefix.

        Similar to `aws s3 sync`. Uploads new/changed files (based on size and mtime)
        and optionally deletes remote files not present locally when `delete=True`.
        """
        return await s3_sync_directory(
            self._s3,
            self.http_client,
            bucket,
            local_dir,
            remote_prefix,
            delete=delete,
            on_upload=on_upload,
            on_delete=on_delete,
            on_skip=on_skip,
            **kwargs,
        )


class UploadPart(TypedDict):
    PartNumber: int
    ETag: str | None


class S3MultipartUpload(NamedTuple):
    fetch_create: Callable[[], Awaitable[str]]
    fetch_complete: Callable[[], Awaitable[niquests.Response]]
    upload_part: Callable[[bytes | bytearray], Awaitable[UploadPart]]
    generate_presigned_url: Callable[..., str]
    fetch_abort: Callable[[], Awaitable[niquests.Response]]


class S3Object(TypedDict, total=False):
    Key: Required[str]
    LastModified: str
    ETag: str
    Size: int
    StorageClass: str


class SyncResult(TypedDict):
    uploaded: list[str]
    deleted: list[str]
    skipped: list[str]


async def s3_delete_object(
    s3: botocore.client.BaseClient, client: niquests.AsyncSession, bucket: str, key: str
) -> niquests.Response:
    """Delete an object from S3 using presigned URL."""
    url = s3.generate_presigned_url(
        ClientMethod="delete_object",
        Params={
            "Bucket": bucket,
            "Key": key,
        },
    )
    return (await client.delete(url)).raise_for_status()


async def s3_delete_objects(
    s3: botocore.client.BaseClient, client: niquests.AsyncSession, bucket: str, keys: list[str]
) -> list[niquests.Response]:
    """Delete multiple objects from S3 using presigned URLs."""
    responses = []
    for key in keys:
        resp = await s3_delete_object(s3, client, bucket, key)
        responses.append(resp)
    return responses


async def s3_list_files(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    prefix: str,
    *,
    search_query: str | None = None,
    max_items: int | None = None,
    page_size: int | None = None,
    starting_token: str | None = None,
) -> AsyncIterator[S3Object]:
    """
    List files in an S3 bucket with a given prefix.

    Yields dicts with 'Key', 'LastModified', 'Size', etc. Use `search_query` for
    JMESPath filtering (e.g. "Contents[?Size > `100`][]"), `max_items` to limit
    total results, `page_size` to control items per request, and `starting_token`
    to resume from a previous continuation token.
    """
    api_version = s3.meta.service_model.api_version
    ns = {"s3": f"http://s3.amazonaws.com/doc/{api_version}/"}

    continuation_token = starting_token
    items_yielded = 0

    while True:
        params: dict = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            params["ContinuationToken"] = continuation_token
        if page_size is not None:
            params["MaxKeys"] = page_size

        url = s3.generate_presigned_url(
            ClientMethod="list_objects_v2",
            Params=params,
        )

        resp = (await client.get(url)).raise_for_status()
        if resp.content is None:
            return
        root = ET.fromstring(resp.content)

        page_items: list[S3Object] = []
        for contents in root.findall("s3:Contents", ns):
            item: S3Object = {}  # pyright: ignore[reportAssignmentType]
            for child in contents:
                tag = child.tag.replace(f"{{{ns['s3']}}}", "")
                item[tag] = child.text
            if "Size" in item:
                item["Size"] = int(item["Size"])
            if root.findtext("s3:EncodingType", namespaces=ns) == "url" and item.get("Key"):
                item["Key"] = unquote(item["Key"])
            page_items.append(item)

        if search_query:
            page_items = jmespath.search(search_query, {"Contents": page_items}) or []

        for item in page_items:
            if max_items is not None and items_yielded >= max_items:
                return
            yield item
            items_yielded += 1

        is_truncated = root.find("s3:IsTruncated", ns)
        if is_truncated is not None and is_truncated.text == "true":
            next_token = root.find("s3:NextContinuationToken", ns)
            continuation_token = next_token.text if next_token is not None else None
        else:
            break


type OnUpload = Callable[[niquests.PreparedRequest], None]


def _upload_hooks(on_upload: OnUpload | None) -> dict | None:
    return {"on_upload": [on_upload]} if on_upload else None


async def s3_put_object(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    key: str,
    data: bytes | bytearray,
    *,
    on_upload: OnUpload | None = None,
    **kwargs: Unpack[S3ObjectParams],
) -> niquests.Response:
    """
    Upload an object to S3 using presigned URL.

    See: https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html
    """

    obj_params: S3ObjectParams = kwargs
    presigned_params = build_s3_presigned_params(bucket, key, obj_params)
    headers = build_s3_headers(obj_params)
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params=presigned_params,
    )
    resp = (
        await client.put(url, data=data, headers=headers if headers else None, hooks=_upload_hooks(on_upload))
    ).raise_for_status()
    return resp


async def s3_upload_file(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    file: Path,
    path: str,
    **kwargs: Unpack[S3ObjectParams],
) -> niquests.Response:
    """
    Upload a file to S3 using presigned URL.
    This is a convenience wrapper around s3_put_object that reads the file content.
    """
    return await s3_put_object(s3, client, bucket, path, file.read_bytes(), **kwargs)


async def s3_get_object(
    s3: botocore.client.BaseClient, client: niquests.AsyncSession, bucket: str, key: str
) -> bytes | None:
    """Download an object from S3 using presigned URL."""
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
        },
    )
    resp = await client.get(url)
    if resp.status_code == http.HTTPStatus.NOT_FOUND:
        return None
    resp.raise_for_status()
    return resp.content


type OnDownloadStartFn = Callable[[niquests.AsyncResponse], None]


async def s3_download_file(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    key: str,
    *,
    chunk_size: int = 1024 * 1024,
    on_start: OnDownloadStartFn | None = None,
) -> AsyncIterator[bytes]:
    """Download an object from S3 with streaming support."""
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
    )
    resp = await client.get(url, stream=True)
    resp.raise_for_status()
    if on_start:
        on_start(resp)
    async for chunk in await resp.iter_content(chunk_size):
        yield chunk


async def s3_create_multipart_upload(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    key: str,
    *,
    expires_in: int = 3600,
    generate_presigned_url: Callable[..., str] | None = None,
    **kwargs: Unpack[S3ObjectParams],
) -> str:
    """
    Initiate a multipart upload and return the UploadId.

    See: https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateMultipartUpload.html
    """
    obj_params: S3ObjectParams = kwargs
    headers = build_s3_headers(obj_params)

    if generate_presigned_url is not None:
        url = generate_presigned_url("create_multipart_upload")
    else:
        presigned_params = build_s3_presigned_params(bucket, key, obj_params)
        url = s3.generate_presigned_url(
            ClientMethod="create_multipart_upload",
            Params=presigned_params,
            ExpiresIn=expires_in,
        )
    resp = (await client.post(url, headers=headers if headers else None)).raise_for_status()
    if resp.content is None:
        raise ValueError("Empty response from create_multipart_upload")
    api_version = s3.meta.service_model.api_version
    ns = {"s3": f"http://s3.amazonaws.com/doc/{api_version}/"}
    root = ET.fromstring(resp.content)
    upload_id_elem = root.find("s3:UploadId", ns)
    if upload_id_elem is None or upload_id_elem.text is None:
        raise ValueError("UploadId not found in response")
    return upload_id_elem.text


@asynccontextmanager
async def s3_multipart_upload(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    key: str,
    *,
    expires_in: int = 3600,
    on_upload: OnUpload | None = None,
    **kwargs: Unpack[S3ObjectParams],
) -> AsyncIterator[S3MultipartUpload]:
    """Async context manager for S3 multipart upload with automatic cleanup."""
    obj_params: S3ObjectParams = kwargs
    upload_id: str | None = None
    _part_number: int = 1
    _parts: list[UploadPart] = []
    _has_been_aborted = False

    async def fetch_complete():
        if upload_id is None:
            raise ValueError("Upload ID is not set")
        complete_url = _generate_presigned_url("complete_multipart_upload", UploadId=upload_id)
        # Create XML payload for completing multipart upload
        parts_xml = "".join(
            f"<Part><PartNumber>{part['PartNumber']}</PartNumber><ETag>{part['ETag']}</ETag></Part>" for part in _parts
        )
        xml_payload = f"<CompleteMultipartUpload>{parts_xml}</CompleteMultipartUpload>"

        response = (
            await client.post(complete_url, data=xml_payload, headers={"Content-Type": "application/xml"})
        ).raise_for_status()
        root = ET.fromstring(response.content or b"")
        if root.tag.rsplit("}", 1)[-1] == "Error":
            raise ClientError(
                {"Error": {child.tag.rsplit("}", 1)[-1]: child.text for child in root}},
                "CompleteMultipartUpload",
            )
        return response

    async def fetch_abort():
        nonlocal _has_been_aborted
        if upload_id is None:
            raise ValueError("Upload ID is not set")
        abort_url = _generate_presigned_url("abort_multipart_upload", UploadId=upload_id)
        abort_resp = (await client.delete(abort_url)).raise_for_status()
        _has_been_aborted = True
        return abort_resp

    async def upload_part(data: bytes | bytearray) -> UploadPart:
        nonlocal _part_number, _parts
        if upload_id is None:
            raise ValueError("Upload ID is not set")
        presigned_url = _generate_presigned_url("upload_part", UploadId=upload_id, PartNumber=_part_number)
        upload_resp = (await client.put(presigned_url, data=data, hooks=_upload_hooks(on_upload))).raise_for_status()
        _etag = upload_resp.headers.get("ETag")
        etag: str | None = _etag.decode() if isinstance(_etag, bytes) else _etag
        _part: UploadPart = {"PartNumber": _part_number, "ETag": etag}
        _parts.append(_part)
        _part_number += 1
        return _part

    def _generate_presigned_url(method: str, **params):
        if method == "create_multipart_upload":
            _params = {**build_s3_presigned_params(bucket, key, obj_params), **params}
        else:
            _params = {"Bucket": bucket, "Key": key, **params}
        return s3.generate_presigned_url(ClientMethod=method, Params=_params, ExpiresIn=expires_in)

    async def fetch_create() -> str:
        nonlocal upload_id
        upload_id = await s3_create_multipart_upload(
            s3, client, bucket, key, expires_in=expires_in, generate_presigned_url=_generate_presigned_url, **kwargs
        )
        return upload_id

    try:
        yield S3MultipartUpload(
            fetch_create=fetch_create,
            fetch_complete=fetch_complete,
            upload_part=upload_part,
            fetch_abort=fetch_abort,
            generate_presigned_url=_generate_presigned_url,
        )
        if not _has_been_aborted and upload_id is not None:
            await fetch_complete()
    except BaseException:
        if not _has_been_aborted and upload_id is not None:
            with suppress(Exception):
                await fetch_abort()
        raise


async def s3_file_upload(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    key: str,
    data: AsyncIterator[bytes],
    *,
    # 5MB minimum for S3 parts
    min_part_size: int = 5 * 1024 * 1024,
    on_upload: OnUpload | None = None,
    content_length: int | None = None,
    **kwargs: Unpack[S3ObjectParams],
) -> None:
    """
    Upload a file to S3 from an async byte stream.

    Uses multipart upload for large files. If `content_length` is provided and smaller
    than `min_part_size`, uses a single PUT instead. The optional `on_upload` callback
    receives a `niquests.PreparedRequest` with an `upload_progress` attribute for
    fine-grained byte-level progress tracking.
    """
    if content_length is not None and content_length < min_part_size:
        # Small file - use single PUT operation
        _data = bytearray()
        async for chunk in data:
            _data.extend(chunk)
        await s3_put_object(s3, client, bucket=bucket, key=key, data=bytes(_data), on_upload=on_upload, **kwargs)
        return

    async with s3_multipart_upload(s3, client, bucket=bucket, key=key, on_upload=on_upload, **kwargs) as mpart:
        await mpart.fetch_create()
        has_uploaded_parts = False
        async for chunk in get_stream_chunk(data, min_size=min_part_size):
            if len(chunk) < min_part_size:
                if not has_uploaded_parts:
                    # No parts uploaded yet, abort multipart and use single PUT
                    await mpart.fetch_abort()
                    await s3_put_object(s3, client, bucket=bucket, key=key, data=chunk, on_upload=on_upload, **kwargs)
                else:
                    # Parts already uploaded, upload final chunk as last part (S3 allows last part to be smaller)
                    await mpart.upload_part(chunk)
                return
            await mpart.upload_part(chunk)
            has_uploaded_parts = True


def _get_credentials(s3: botocore.client.BaseClient, session: botocore.session.Session | None = None):
    """Get credentials from session (public API) or fall back to client internals."""
    if session is not None:
        return session.get_credentials()
    # Fall back to private API for backward compatibility with standalone function usage
    return s3._request_signer._credentials  # pyright: ignore[reportAttributeAccessIssue]


def _sign_s3_request(
    s3: botocore.client.BaseClient,
    method: str,
    url: str,
    data: bytes,
    content_type: str,
    botocore_session: botocore.session.Session | None = None,
) -> dict[str, str]:
    """Create and sign an S3 request, returning the headers to use."""
    request = AWSRequest(method=method, url=url, data=data, headers={"Content-Type": content_type})
    request.headers["x-amz-content-sha256"] = hashlib.sha256(data).hexdigest()

    credentials = _get_credentials(s3, botocore_session)
    region = s3.meta.region_name
    signer = SigV4Auth(credentials, "s3", region)
    signer.add_auth(request)

    return dict(request.headers)


async def s3_put_bucket_policy(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    policy: str | dict,
    botocore_session: botocore.session.Session | None = None,
) -> niquests.Response:
    """
    Set a bucket policy using a signed request.

    The policy can be provided as a JSON string or a dict (which will be serialized).
    If botocore_session is provided, credentials are retrieved via the public API;
    otherwise falls back to the client's internal credentials.
    """
    policy_str = policy if isinstance(policy, str) else json.dumps(policy)
    policy_bytes = policy_str.encode("utf-8")
    url = f"{s3.meta.endpoint_url}/{bucket}?policy"
    headers = _sign_s3_request(s3, "PUT", url, policy_bytes, "application/json", botocore_session)
    return (await client.put(url, data=policy_bytes, headers=headers)).raise_for_status()


async def s3_get_bucket_policy(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
) -> dict | None:
    """
    Get a bucket policy using presigned URL.

    Returns the policy as a dict, or None if no policy exists.
    """
    url = s3.generate_presigned_url(
        ClientMethod="get_bucket_policy",
        Params={"Bucket": bucket},
    )
    resp = await client.get(url)
    if resp.status_code == http.HTTPStatus.NOT_FOUND:
        return None
    # NoSuchBucketPolicy returns 404 on AWS, but some providers may return other codes
    if resp.status_code == http.HTTPStatus.NO_CONTENT:
        return None
    resp.raise_for_status()
    if resp.content is None:
        return None
    return json.loads(resp.content)


async def s3_delete_bucket_policy(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
) -> niquests.Response:
    """Delete a bucket policy using presigned URL."""
    url = s3.generate_presigned_url(
        ClientMethod="delete_bucket_policy",
        Params={"Bucket": bucket},
    )
    return (await client.delete(url)).raise_for_status()


def _build_website_xml(index_document: str, error_document: str | None, api_version: str) -> str:
    """Build XML payload for S3 website configuration."""
    index_xml = f"<IndexDocument><Suffix>{xml_escape(index_document)}</Suffix></IndexDocument>"
    error_xml = f"<ErrorDocument><Key>{xml_escape(error_document)}</Key></ErrorDocument>" if error_document else ""
    return f'<WebsiteConfiguration xmlns="http://s3.amazonaws.com/doc/{api_version}/">{index_xml}{error_xml}</WebsiteConfiguration>'


async def s3_put_bucket_website(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    index_document: str = "index.html",
    error_document: str | None = None,
    botocore_session: botocore.session.Session | None = None,
) -> niquests.AsyncResponse:
    """
    Configure a bucket as a static website using a signed request.

    Note: This operation is not supported by MinIO.
    If botocore_session is provided, credentials are retrieved via the public API;
    otherwise falls back to the client's internal credentials.
    """
    api_version = s3.meta.service_model.api_version
    xml_payload = _build_website_xml(index_document, error_document, api_version)
    xml_bytes = xml_payload.encode("utf-8")
    url = f"{s3.meta.endpoint_url}/{bucket}?website"
    headers = _sign_s3_request(s3, "PUT", url, xml_bytes, "application/xml", botocore_session)
    return (await client.put(url, data=xml_bytes, headers=headers)).raise_for_status()  # pyright: ignore[reportReturnType]


async def s3_delete_bucket_website(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
) -> niquests.Response:
    """Remove website configuration from a bucket using presigned URL."""
    url = s3.generate_presigned_url(
        ClientMethod="delete_bucket_website",
        Params={"Bucket": bucket},
    )
    return (await client.delete(url)).raise_for_status()


async def s3_empty_bucket(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> int:
    """
    Delete all objects from a bucket.

    The optional on_progress callback is called with each deleted key.
    Returns the count of deleted objects.
    """
    deleted_count = 0
    async for obj in s3_list_files(s3, client, bucket, ""):
        key = obj.get("Key")
        if key:
            await s3_delete_object(s3, client, bucket, key)
            deleted_count += 1
            if on_progress:
                on_progress(key)
    return deleted_count


def _parse_s3_datetime(s3_datetime: str) -> dt.datetime:
    """Parse S3 LastModified datetime string to timezone-aware datetime."""
    # S3 returns ISO format like "2024-01-15T10:30:00.000Z"
    # Handle both with and without milliseconds
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return dt.datetime.strptime(s3_datetime, fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse S3 datetime: {s3_datetime}")


def _needs_upload(local_file: Path, remote_obj: S3Object | None) -> bool:
    """
    Determine if a local file needs to be uploaded based on size and mtime.

    Uses size + mtime strategy: upload if size differs OR local mtime is newer.
    """
    if remote_obj is None:
        return True

    local_stat = local_file.stat()
    local_size = local_stat.st_size
    remote_size = remote_obj.get("Size", 0)

    if local_size != remote_size:
        return True

    remote_modified_str = remote_obj.get("LastModified")
    if remote_modified_str is None:
        return True

    local_mtime = dt.datetime.fromtimestamp(local_stat.st_mtime, tz=dt.timezone.utc)
    remote_mtime = _parse_s3_datetime(remote_modified_str)

    return local_mtime > remote_mtime


async def s3_sync_directory(
    s3: botocore.client.BaseClient,
    client: niquests.AsyncSession,
    bucket: str,
    local_dir: Path,
    remote_prefix: str = "",
    *,
    delete: bool = False,
    on_upload: Callable[[Path, str], None] | None = None,
    on_delete: Callable[[str], None] | None = None,
    on_skip: Callable[[Path, str], None] | None = None,
    **kwargs: Unpack[S3ObjectParams],
) -> SyncResult:
    """
    Sync a local directory to an S3 bucket prefix.

    Similar to `aws s3 sync`. Compares files using size and modification time:
    uploads if size differs OR local file is newer than remote. When `delete=True`,
    removes remote files that don't exist locally.

    The remote_prefix should not have a leading slash. Files are uploaded with keys
    like "{remote_prefix}/{relative_path}" (or just "{relative_path}" if prefix is empty).
    """
    result: SyncResult = {"uploaded": [], "deleted": [], "skipped": []}

    # Validate local directory
    local_dir = local_dir.resolve()
    if not local_dir.exists():
        raise ValueError(f"Local directory does not exist: {local_dir}")
    if not local_dir.is_dir():
        raise ValueError(f"Path is not a directory: {local_dir}")

    # Normalize prefix (remove trailing slash for consistent key building)
    prefix = remote_prefix.rstrip("/")

    # Build map of remote files: relative_key -> S3Object
    remote_files: dict[str, S3Object] = {}
    list_prefix = f"{prefix}/" if prefix else ""
    async for obj in s3_list_files(s3, client, bucket, list_prefix):
        key = obj.get("Key")
        if key:
            # Extract relative path from full key
            relative_key = key[len(list_prefix) :] if list_prefix else key
            remote_files[relative_key] = obj

    # Collect local files and their relative paths
    local_files: dict[str, Path] = {}
    for local_file in local_dir.rglob("*"):
        if local_file.is_file():
            relative_path = local_file.relative_to(local_dir).as_posix()
            local_files[relative_path] = local_file

    # Upload new or changed files
    for relative_path, local_file in local_files.items():
        remote_key = f"{prefix}/{relative_path}" if prefix else relative_path
        remote_obj = remote_files.get(relative_path)

        if _needs_upload(local_file, remote_obj):
            await s3_upload_file(s3, client, bucket, local_file, remote_key, **kwargs)
            result["uploaded"].append(remote_key)
            if on_upload:
                on_upload(local_file, remote_key)
        else:
            result["skipped"].append(remote_key)
            if on_skip:
                on_skip(local_file, remote_key)

    # Delete remote files not present locally
    if delete:
        for relative_path, remote_obj in remote_files.items():
            if relative_path not in local_files:
                remote_key = remote_obj["Key"]
                await s3_delete_object(s3, client, bucket, remote_key)
                result["deleted"].append(remote_key)
                if on_delete:
                    on_delete(remote_key)

    return result
