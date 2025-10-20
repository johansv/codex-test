"""Utilities for writing Garmin data payloads to disk."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from agentlab.core.garmin import EndpointError, EndpointResult, FetchOutcome


class GarminStorageWriter:
    """Persist Garmin endpoint payloads with atomic writes."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def store(self, day: date, outcome: FetchOutcome) -> None:
        """Write results and errors for *day* to disk."""

        for result in outcome.results:
            self.write_result(day, result)

        for error in outcome.errors:
            self.write_error(day, error)

    def write_result(self, day: date, result: EndpointResult) -> None:
        day_dir = self._ensure_day_dir(day)
        filename = self._result_filename(result)
        payload = self._serialise_payload(result)
        target_path = day_dir / filename
        self._write_atomic(target_path, payload)
        error_path = day_dir / self._error_filename(result.endpoint, result.scope)
        if error_path.exists():
            error_path.unlink()

    def write_error(self, day: date, error: EndpointError) -> None:
        day_dir = self._ensure_day_dir(day)
        path = day_dir / self._error_filename(error.endpoint, error.scope)
        content = json.dumps(
            {
                "endpoint": error.endpoint,
                "scope": error.scope,
                "message": error.message,
                "traceback": error.traceback,
            },
            indent=2,
        )
        self._write_atomic(path, content.encode("utf-8"))

    def _ensure_day_dir(self, day: date) -> Path:
        day_dir = self.root / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _serialise_payload(self, result: EndpointResult) -> bytes:
        payload = result.payload
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            return payload.encode("utf-8")
        if isinstance(payload, (dict, list)):
            return json.dumps(payload, indent=2).encode("utf-8")
        return json.dumps(payload, default=str, indent=2).encode("utf-8")

    def _result_filename(self, result: EndpointResult) -> str:
        extension = self._determine_extension(result)
        basename = self._compose_basename(result.endpoint, result.scope)
        return f"{basename}.{extension}"

    def _determine_extension(self, result: EndpointResult) -> str:
        payload = result.payload
        if isinstance(payload, bytes):
            fmt = result.scope.get("format")
            if isinstance(fmt, str):
                lowered = fmt.lower()
                if lowered == "original":
                    return "fit"
                return lowered
            return "bin"
        if isinstance(payload, (dict, list)):
            return "json"
        if isinstance(payload, str):
            return "txt"
        return "json"

    def _compose_basename(self, endpoint: str, scope: dict[str, str | int]) -> str:
        activity_id = scope.get("activityId")
        if activity_id is not None:
            return f"{endpoint}_{activity_id}"
        return endpoint

    def _error_filename(self, endpoint: str, scope: dict[str, str | int]) -> str:
        basename = self._compose_basename(endpoint, scope)
        return f"{basename}.error.json"

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=path.stem,
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(tmp_fd, "wb") as handle:
                handle.write(data)
            tmp_path.replace(path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
