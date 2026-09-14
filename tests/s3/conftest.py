import contextlib
import os
from dataclasses import dataclass

import botocore.session
import pytest
from botocore.config import Config
from minio import Minio

# Moto config (accepts any credentials)
MOTO_URL = os.environ.get("MOTO_URL", "localhost:9000")
MOTO_ACCESS_KEY = os.environ.get("MOTO_ACCESS_KEY", "foo")
MOTO_SECRET_KEY = os.environ.get("MOTO_SECRET_KEY", "foobarbaz")

S3_BUCKET = "test"

S3_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "path"})


@dataclass
class S3BackendConfig:
    """Configuration for an S3-compatible backend."""

    name: str
    endpoint_url: str
    access_key: str
    secret_key: str
    region: str


MOTO_BACKEND = S3BackendConfig(
    name="moto",
    endpoint_url=f"http://{MOTO_URL}",
    access_key=MOTO_ACCESS_KEY,
    secret_key=MOTO_SECRET_KEY,
    region="us-east-1",
)


@contextlib.contextmanager
def get_botocore_client(backend: S3BackendConfig):
    session = botocore.session.Session()
    client = session.create_client(
        "s3",
        endpoint_url=backend.endpoint_url,
        aws_secret_access_key=backend.secret_key,
        aws_access_key_id=backend.access_key,
        region_name=backend.region,
        config=S3_CONFIG,
    )
    yield client
    client.close()


@pytest.fixture()
def minio_client():
    client = Minio(MOTO_URL, access_key=MOTO_ACCESS_KEY, secret_key=MOTO_SECRET_KEY, secure=False)
    yield client


@pytest.fixture(scope="function")
def s3_bucket():
    return S3_BUCKET


@pytest.fixture(scope="function")
def s3_backend() -> S3BackendConfig:
    return MOTO_BACKEND


@pytest.fixture(scope="function")
async def s3_client(s3_backend: S3BackendConfig):
    from tracktolib.s3.niquests import S3Session

    client = S3Session(
        endpoint_url=s3_backend.endpoint_url,
        access_key=s3_backend.access_key,
        secret_key=s3_backend.secret_key,
        region=s3_backend.region,
        s3_config=S3_CONFIG,
    )
    async with client:
        yield client


@pytest.fixture()
async def setup_bucket(s3_bucket, s3_client, s3_backend: S3BackendConfig):
    """Setup and teardown bucket for tests."""
    try:
        await s3_client.empty_bucket(s3_bucket)
    except Exception:
        pass
    with get_botocore_client(s3_backend) as client:
        try:
            client.delete_bucket(Bucket=s3_bucket)
        except Exception:
            pass
        client.create_bucket(Bucket=s3_bucket)

    yield

    try:
        await s3_client.empty_bucket(s3_bucket)
    except Exception:
        pass
    with get_botocore_client(s3_backend) as client:
        try:
            client.delete_bucket(Bucket=s3_bucket)
        except Exception:
            pass
