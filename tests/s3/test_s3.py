import contextlib

import minio.error
import pytest
from aiobotocore.session import get_session

from tests.s3.conftest import MOTO_ACCESS_KEY, MOTO_SECRET_KEY, MOTO_URL


@contextlib.asynccontextmanager
async def get_s3_client():
    session = get_session()
    async with session.create_client(
        "s3",
        endpoint_url=f"http://{MOTO_URL}",
        aws_secret_access_key=MOTO_SECRET_KEY,
        aws_access_key_id=MOTO_ACCESS_KEY,
    ) as client:
        yield client


@pytest.fixture()
def setup_bucket_aioboto(minio_client, s3_bucket):
    from tracktolib.s3.minio import bucket_rm

    try:
        bucket_rm(minio_client, s3_bucket)
    except minio.error.S3Error:
        pass
    minio_client.make_bucket(s3_bucket)
    yield
    bucket_rm(minio_client, s3_bucket)


@pytest.mark.usefixtures("setup_bucket_aioboto")
async def test_upload_list_file(s3_bucket, static_dir, minio_client):
    from tracktolib.s3.s3 import delete_file, delete_files, list_files, upload_file

    async with get_s3_client() as client:
        await upload_file(client, s3_bucket, static_dir / "test.csv", "foo/test.csv")
        await upload_file(client, s3_bucket, static_dir / "test.csv", "foo/test.tsv", acl="public-read")

        # List
        bucket_data = await list_files(client, s3_bucket, "foo")
        assert sorted([x["Key"] for x in bucket_data]) == ["foo/test.csv", "foo/test.tsv"]
        bucket_data = await list_files(client, s3_bucket, "foo", search_query="Contents[?ends_with(Key, `tsv`)]")
        assert [x["Key"] for x in bucket_data] == ["foo/test.tsv"]

        # Delete
        # Does not raise error
        response_delete_file = await delete_file(client, s3_bucket, "file-that-does-not-exists")
        assert isinstance(response_delete_file, dict)
        await delete_file(client, s3_bucket, "foo/test.tsv")
        bucket_data = await list_files(client, s3_bucket, "foo")
        assert sorted([x["Key"] for x in bucket_data]) == ["foo/test.csv"]

        await upload_file(client, s3_bucket, static_dir / "test.csv", "foo/test.tsv", acl="public-read")
        response_delete_files = await delete_files(client, s3_bucket, ["foo/test.tsv", "foo/test.csv"])
        assert isinstance(response_delete_files, dict)
        bucket_data = await list_files(client, s3_bucket, "foo")
        assert sorted([x["Key"] for x in bucket_data]) == []
