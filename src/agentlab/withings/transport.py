from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, MutableMapping

try:  # optional dependency
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional
    requests = None  # type: ignore[assignment]

from agentlab.utils.withings_tokens import WithingsTokenBundle, WithingsTokenStore

from .fetcher import NetworkError, RetryAfter

logger = logging.getLogger(__name__)


class WithingsTransport:
    """HTTP transport for Withings APIs with OAuth2 refresh support."""

    _TOKEN_GRACE_SECONDS = 60

    def __init__(
        self,
        *,
        token_store: WithingsTokenStore,
        http_session: Any | None = None,
        base_url: str = "https://wbsapi.withings.net",
        timeout: float = 30.0,
        request_delay: float = 1.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._store = token_store
        if http_session is not None:
            self._session = http_session
        else:
            if requests is None:
                raise RuntimeError(
                    "requests is required for WithingsTransport; install requests or supply a custom session."
                )
            self._session = requests.Session()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._request_delay = max(0.0, float(request_delay))
        self._sleep = sleep or time.sleep
        self._last_request_at: float | None = None

        self._token_bundle = self._store.load()

    def get_measures(self, from_dt: datetime, to_dt: datetime) -> list[dict[str, Any]]:
        self._ensure_token()
        all_groups: list[dict[str, Any]] = []
        offset: int | None = None

        while True:
            payload: dict[str, Any] = {
                "action": "getmeas",
                "category": 1,
                "startdate": int(from_dt.timestamp()),
                "enddate": int(to_dt.timestamp()),
            }
            if offset is not None:
                payload["offset"] = offset

            response = self._request("POST", "/v2/measure", data=payload)
            body = response.get("body", {})
            groups = body.get("measuregrps")
            if isinstance(groups, list):
                all_groups.extend(groups)

            more = body.get("more")
            next_offset = body.get("offset")
            if more and isinstance(next_offset, (int, float)):
                offset = int(next_offset)
                continue
            break

        return all_groups

    # Internal helpers ---------------------------------------------------------

    def _ensure_token(self) -> None:
        now = datetime.now(timezone.utc)
        if self._token_bundle.expires_at - timedelta(seconds=self._TOKEN_GRACE_SECONDS) <= now:
            self._refresh_tokens()

    def _refresh_tokens(self) -> None:
        payload = {
            "action": "requesttoken",
            "grant_type": "refresh_token",
            "client_id": self._token_bundle.client_id,
            "client_secret": self._token_bundle.client_secret,
            "refresh_token": self._token_bundle.refresh_token,
        }
        data = self._request("POST", "/v2/oauth2", data=payload, allow_refresh=False)
        body = data.get("body", {})
        expires_in = body.get("expires_in")
        expires_at = body.get("expires_at")
        if isinstance(expires_in, (int, float)):
            expiry = datetime.now(timezone.utc) + timedelta(seconds=float(expires_in))
        elif isinstance(expires_at, (int, float)):
            expiry = datetime.fromtimestamp(float(expires_at), tz=timezone.utc)
        elif isinstance(expires_at, str):
            expiry = datetime.fromisoformat(expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        else:
            expiry = datetime.now(timezone.utc) + timedelta(hours=1)

        self._token_bundle = WithingsTokenBundle(
            access_token=str(body.get("access_token") or self._token_bundle.access_token),
            refresh_token=str(body.get("refresh_token") or self._token_bundle.refresh_token),
            expires_at=expiry.astimezone(timezone.utc),
            client_id=self._token_bundle.client_id,
            client_secret=self._token_bundle.client_secret,
        )
        self._store.save(self._token_bundle)

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Mapping[str, Any] | None = None,
        allow_refresh: bool = True,
    ) -> MutableMapping[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._token_bundle.access_token}",
            "Accept": "application/json",
        }
        self._throttle()
        response = self._session.request(
            method,
            url,
            data=data,
            timeout=self._timeout,
            headers=headers,
        )
        self._last_request_at = time.monotonic()

        if response.status_code == 401 and allow_refresh:
            self._refresh_tokens()
            return self._request(method, path, data=data, allow_refresh=False)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after)
            except (TypeError, ValueError):
                wait_seconds = 60.0
            raise RetryAfter(wait_seconds)

        if response.status_code >= 400:
            raise NetworkError(self._redact_error(response))

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise NetworkError("Withings API returned invalid JSON") from exc

        status = payload.get("status")
        if status not in (0, "0", None):
            error_message = payload.get("error") or payload.get("message") or "Withings API error"
            raise NetworkError(self._redact_text(str(error_message)))

        return payload

    @staticmethod
    def _redact_text(text: str) -> str:
        if not text:
            return text
        return text.replace("\n", " ").replace("\r", " ")

    def _redact_error(self, response: Any) -> str:
        parts = [f"HTTP {response.status_code}"]
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            message = payload.get("error") or payload.get("message")
            if message:
                parts.append(self._redact_text(str(message)))
        return " - ".join(parts)

    def _throttle(self) -> None:
        if self._request_delay <= 0:
            return
        now = time.monotonic()
        if self._last_request_at is None:
            self._last_request_at = now
            return
        elapsed = now - self._last_request_at
        if elapsed < self._request_delay:
            self._sleep(self._request_delay - elapsed)
