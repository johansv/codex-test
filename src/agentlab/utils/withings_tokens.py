from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_REQUIRED_KEYS = {
    "access_token",
    "refresh_token",
    "expires_at",
    "client_id",
    "client_secret",
}


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


@dataclass
class WithingsTokenBundle:
    access_token: str
    refresh_token: str
    expires_at: datetime
    client_id: str
    client_secret: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "WithingsTokenBundle":
        missing = _REQUIRED_KEYS - data.keys()
        if missing:
            raise ValueError(f"Missing Withings token keys: {', '.join(sorted(missing))}")
        expires_at = data["expires_at"]
        if isinstance(expires_at, str):
            expires = datetime.fromisoformat(expires_at)
        elif isinstance(expires_at, (int, float)):
            expires = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        elif isinstance(expires_at, datetime):
            expires = expires_at
        else:
            raise ValueError("Unsupported expires_at type in Withings token bundle")
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return cls(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            expires_at=expires.astimezone(timezone.utc),
            client_id=str(data["client_id"]),
            client_secret=str(data["client_secret"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }


class WithingsTokenStore:
    """Persist and retrieve Withings OAuth token bundles."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> WithingsTokenBundle:
        if not self._path.exists():
            raise FileNotFoundError(self._path)
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Withings token file must contain a JSON object")
        return WithingsTokenBundle.from_mapping(raw)

    def save(self, bundle: WithingsTokenBundle) -> None:
        serialized = json.dumps(bundle.to_dict(), indent=2, sort_keys=True)
        _write_atomic(self._path, serialized)
