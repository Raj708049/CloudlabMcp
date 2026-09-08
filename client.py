"""HTTP client + auth helper for the CloudLab API.

Wraps httpx with the base URL and credentials from config, holds an auth
token once we log in, and exposes small helpers (get/post/etc.) that every
tool can reuse.
"""

from typing import Any, Optional

import httpx

from config import config


class CloudLabClient:
    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._logged_in: bool = False
        # A single reusable async client. It persists session cookies (the
        # SESS... cookie the login sets) automatically across requests.
        # timeout is generous for provisioning.
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=60.0,
        )

    # ---- auth -----------------------------------------------------------
    async def login(self) -> Any:
        """Authenticate against POST /v1/users/login.

        Sends form-encoded username/password. The response returns a token
        (used as X-CSRF-Token for later calls) and sets a session cookie that
        the shared client stores automatically. No pre-existing token needed —
        it is generated fresh on every login.
        """
        config.require("base_url", "username", "password")
        self._http.base_url = config.base_url
        resp = await self._http.post(
            "/v1/users/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"username": config.username, "password": config.password},
        )
        resp.raise_for_status()

        data: Any
        try:
            data = resp.json()
        except Exception:
            data = resp.text

        # Best-effort extraction of a session/auth token from the body.
        if isinstance(data, dict):
            nested = data.get("data") if isinstance(data.get("data"), dict) else {}
            self._token = (
                data.get("token")
                or data.get("sessionToken")
                or nested.get("token")
            )
        self._logged_in = True
        return data

    async def ensure_login(self) -> None:
        if not self._logged_in:
            await self.login()

    def _base_headers(self) -> dict[str, str]:
        """Headers sent on every authenticated (non-login) request.

        Authenticated endpoints expect the CSRF token from login in the
        'X-CSRF-Token' header; the session cookie is attached automatically.
        """
        headers: dict[str, str] = {}
        if self._token:
            headers["X-CSRF-Token"] = self._token
        return headers

    @property
    def csrf_token(self) -> Optional[str]:
        return self._token

    # ---- generic request helpers ---------------------------------------
    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: Any = None,
        params: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        """Make an HTTP request and return parsed JSON (or text)."""
        self._http.base_url = config.base_url
        if auth:
            await self.ensure_login()
        headers = self._base_headers() if auth else {}
        resp = await self._http.request(
            method, path, json=json, data=data, params=params, headers=headers
        )
        resp.raise_for_status()
        # Some endpoints return empty bodies.
        if not resp.content:
            return {"status": resp.status_code}
        try:
            return resp.json()
        except Exception:
            return resp.text

    async def get(self, path: str, **kw: Any) -> Any:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, **kw: Any) -> Any:
        return await self.request("POST", path, **kw)

    async def put(self, path: str, **kw: Any) -> Any:
        return await self.request("PUT", path, **kw)

    async def delete(self, path: str, **kw: Any) -> Any:
        return await self.request("DELETE", path, **kw)


# Shared singleton used by all tools.
client = CloudLabClient()
