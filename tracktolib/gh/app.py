from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

try:
    import niquests
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from niquests.auth import AsyncAuthBase
except ImportError:
    raise ImportError('Please install tracktolib with "gh-app" to use this module')

from tracktolib.gh.client import GITHUB_HEADERS, GitHubClient, _get_all, _raise_for_status

if TYPE_CHECKING:
    from niquests import PreparedRequest
    from urllib3.util.retry import Retry

    from tracktolib.gh.types import Installation, InstallationToken

# GitHub accepts app JWTs living up to 10 minutes; iat is backdated against clock drift
JWT_LIFETIME = 540
JWT_CLOCK_DRIFT = 60
# Installation tokens live one hour; renewed this long before they expire
TOKEN_RENEW_MARGIN = 300


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _with_bearer(r: PreparedRequest, token: str) -> PreparedRequest:
    if r.headers is None:
        raise ValueError("Auth runs on prepared requests, which always carry headers")
    r.headers["Authorization"] = f"Bearer {token}"
    return r


class _AppJWTAuth(AsyncAuthBase):
    """Bearer auth with a fresh app JWT on every request."""

    def __init__(self, app: GitHubApp) -> None:
        self.app = app

    async def __call__(self, r: PreparedRequest) -> PreparedRequest:
        return _with_bearer(r, self.app.jwt())


class InstallationAuth(AsyncAuthBase):
    """Bearer auth with an installation token, minted on first use and renewed before it expires."""

    def __init__(
        self,
        app: GitHubApp,
        installation_id: int,
        *,
        permissions: Mapping[str, str] | None = None,
        repositories: Sequence[str] | None = None,
    ) -> None:
        self.app = app
        self.installation_id = installation_id
        self.permissions = permissions
        self.repositories = repositories
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        """The cached installation token, minted again when it expires within TOKEN_RENEW_MARGIN seconds."""
        async with self._lock:
            if self._token is None or self._expires_at - time.time() < TOKEN_RENEW_MARGIN:
                data = await self.app.create_installation_token(
                    self.installation_id, permissions=self.permissions, repositories=self.repositories
                )
                self._token = data["token"]
                self._expires_at = datetime.fromisoformat(data["expires_at"]).timestamp()
            return self._token

    async def __call__(self, r: PreparedRequest) -> PreparedRequest:
        return _with_bearer(r, await self.token())


@dataclass
class GitHubApp:
    """
    Async client authenticated as a GitHub App, for its installations and their tokens.

    `private_key` is the PEM key downloaded from the App settings.
    """

    app_id: str
    private_key: str = field(repr=False)
    base_url: str = "https://api.github.com"
    retries: int | Retry = 0
    session: niquests.AsyncSession = field(init=False, repr=False)
    _key: rsa.RSAPrivateKey = field(init=False, repr=False)

    def __post_init__(self) -> None:
        key = serialization.load_pem_private_key(self.private_key.encode(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("A GitHub App private key must be an RSA key")
        self._key = key
        self.session = niquests.AsyncSession(
            base_url=self.base_url, retries=self.retries, auth=_AppJWTAuth(self), headers=dict(GITHUB_HEADERS)
        )

    async def __aenter__(self) -> GitHubApp:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying session."""
        await self.session.close()

    def jwt(self, *, now: float | None = None) -> str:
        """Sign an RS256 JWT authenticating as the App itself, valid JWT_LIFETIME seconds from `now`."""
        issued = int(time.time() if now is None else now)
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = {"iat": issued - JWT_CLOCK_DRIFT, "exp": issued + JWT_LIFETIME, "iss": self.app_id}
        payload = _b64url(json.dumps(claims).encode())
        signature = self._key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{payload}.{_b64url(signature)}"

    async def list_installations(self) -> list[Installation]:
        """List the accounts the App is installed on."""
        return await _get_all(self.session, "/app/installations")

    async def get_installation(self, account: str) -> Installation | None:
        """Get the installation on a user or organization login (case insensitive), None when not installed there."""
        for installation in await self.list_installations():
            if ((installation["account"] or {}).get("login") or "").lower() == account.lower():
                return installation
        return None

    async def create_installation_token(
        self,
        installation_id: int,
        *,
        permissions: Mapping[str, str] | None = None,
        repositories: Sequence[str] | None = None,
    ) -> InstallationToken:
        """Mint a one-hour installation token, optionally narrowed to some permissions or repository names."""
        payload: dict[str, Any] = {}
        if permissions is not None:
            payload["permissions"] = dict(permissions)
        if repositories is not None:
            payload["repositories"] = list(repositories)
        response = await self.session.post(f"/app/installations/{installation_id}/access_tokens", json=payload or None)
        _raise_for_status(response)
        return cast("InstallationToken", response.json())

    def installation_auth(
        self,
        installation_id: int,
        *,
        permissions: Mapping[str, str] | None = None,
        repositories: Sequence[str] | None = None,
    ) -> InstallationAuth:
        """Auth acting as an installation, for GitHubClient(auth=...) or any niquests session."""
        return InstallationAuth(self, installation_id, permissions=permissions, repositories=repositories)

    def client(
        self,
        installation_id: int,
        *,
        permissions: Mapping[str, str] | None = None,
        repositories: Sequence[str] | None = None,
        retries: int | Retry = 0,
        hooks: Any = None,
    ) -> GitHubClient:
        """A GitHubClient acting as an installation, its token renewed for as long as the client lives."""
        auth = self.installation_auth(installation_id, permissions=permissions, repositories=repositories)
        return GitHubClient(token=None, base_url=self.base_url, retries=retries, hooks=hooks, auth=auth)
