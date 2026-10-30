import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from tracktolib.gh.app import GitHubApp

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()
TOKEN_PATH = "/app/installations/1/access_tokens"


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _token_body(token: str, expires_in: timedelta) -> str:
    return json.dumps({"token": token, "expires_at": (datetime.now(UTC) + expires_in).isoformat()})


@pytest.fixture
async def app(fake_github):
    async with GitHubApp(app_id="123", private_key=PEM, base_url=fake_github.url) as client:
        yield client


def test_jwt_is_rs256_signed_by_the_app():
    app = GitHubApp(app_id="123", private_key=PEM)
    header, payload, signature = app.jwt(now=1_000_000).split(".")

    KEY.public_key().verify(_b64decode(signature), f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    assert json.loads(_b64decode(header)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(_b64decode(payload)) == {"iat": 999_940, "exp": 1_000_540, "iss": "123"}


@pytest.mark.parametrize(
    "expires_in, expected_mints",
    [
        pytest.param(timedelta(hours=1), 1, id="cached-token-reused"),
        pytest.param(timedelta(minutes=2), 2, id="token-near-expiry-renewed"),
    ],
)
async def test_client_acts_as_installation(app, fake_github, expires_in, expected_mints):
    fake_github.routes[TOKEN_PATH] = (201, _token_body("ghs_install", expires_in))

    async with app.client(1, permissions={"issues": "write"}, repositories=["repo"]) as gh:
        await gh.get_pull_request("owner/repo", 1)
        await gh.get_pull_request("owner/repo", 2)

    mints = [r for r in fake_github.requests if r.path == TOKEN_PATH]
    assert len(mints) == expected_mints
    assert mints[0].headers["Authorization"].startswith("Bearer ey")
    assert json.loads(mints[0].body) == {"permissions": {"issues": "write"}, "repositories": ["repo"]}
    calls = [r for r in fake_github.requests if r.path.startswith("/repos/")]
    assert [r.headers["Authorization"] for r in calls] == ["Bearer ghs_install"] * 2


@pytest.mark.parametrize(
    "account, expected_id",
    [
        pytest.param("Getsoren", 7, id="found-case-insensitive"),
        pytest.param("someone-else", None, id="not-installed"),
    ],
)
async def test_get_installation(app, fake_github, account, expected_id):
    fake_github.body = json.dumps([{"id": 7, "account": {"login": "getsoren"}}, {"id": 8, "account": None}])

    installation = await app.get_installation(account)

    assert (installation["id"] if installation else None) == expected_id


async def test_list_installation_repositories_unwraps_the_page(app, fake_github):
    fake_github.routes[TOKEN_PATH] = (201, _token_body("ghs_install", timedelta(hours=1)))
    fake_github.body = json.dumps({"total_count": 1, "repositories": [{"full_name": "owner/repo"}]})

    async with app.client(1) as gh:
        repositories = await gh.list_installation_repositories()

    assert [r["full_name"] for r in repositories] == ["owner/repo"]
