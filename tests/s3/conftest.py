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

# Garage config
GARAGE_URL = os.environ.get("GARAGE_URL", "localhost:9002")
GARAGE_ACCESS_KEY = os.environ.get("GARAGE_ACCESS_KEY", "GK0123456789abcdef01234567")
GARAGE_SECRET_KEY = os.environ.get(
    "GARAGE_SECRET_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)

S3_BUCKET = "test"

GARAGE_AVAILABLE = True

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

GARAGE_BACKEND = S3BackendConfig(
    name="garage",
    endpoint_url=f"http://{GARAGE_URL}",
    access_key=GARAGE_ACCESS_KEY,
    secret_key=GARAGE_SECRET_KEY,
    region="us-east-1",
)


def get_s3_backends():
    """Return list of available S3 backends as pytest params."""
    backends = [pytest.param(MOTO_BACKEND, id="moto")]
    if GARAGE_AVAILABLE:
        backends.append(pytest.param(GARAGE_BACKEND, id="garage"))
    return backends


# Skip markers
requires_garage = pytest.mark.skipif(
    not GARAGE_AVAILABLE, reason="Requires Garage (set GARAGE_ACCESS_KEY and GARAGE_SECRET_KEY)"
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


@pytest.fixture(scope="function", params=get_s3_backends())
def s3_backend(request) -> S3BackendConfig:
    """Parametrized fixture providing each available S3 backend."""
    return request.param


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
    """Setup and teardown bucket for tests, works with any backend."""
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


# Garage-only fixtures for website tests
@pytest.fixture(scope="function")
async def garage_client():
    if not GARAGE_AVAILABLE:
        pytest.skip("Garage not configured")
    from tracktolib.s3.niquests import S3Session

    client = S3Session(
        endpoint_url=GARAGE_BACKEND.endpoint_url,
        access_key=GARAGE_BACKEND.access_key,
        secret_key=GARAGE_BACKEND.secret_key,
        region=GARAGE_BACKEND.region,
        s3_config=S3_CONFIG,
    )
    async with client:
        yield client


@pytest.fixture()
async def setup_garage_bucket(s3_bucket, garage_client):
    """Setup bucket in Garage for website tests."""
    if not GARAGE_AVAILABLE:
        pytest.skip("Garage not configured")

    try:
        await garage_client.empty_bucket(s3_bucket)
    except Exception:
        pass
    with get_botocore_client(GARAGE_BACKEND) as client:
        try:
            client.delete_bucket(Bucket=s3_bucket)
        except Exception:
            pass
        client.create_bucket(Bucket=s3_bucket)

    yield

    try:
        await garage_client.empty_bucket(s3_bucket)
    except Exception:
        pass
    with get_botocore_client(GARAGE_BACKEND) as client:
        try:
            client.delete_bucket(Bucket=s3_bucket)
        except Exception:
            pass
