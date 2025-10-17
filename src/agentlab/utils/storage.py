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

        day_dir = self.root / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)

        for result in outcome.results:
            filename = self._result_filename(result)
            payload = self._serialise_payload(result)
            self._write_atomic(day_dir / filename, payload)

        for error in outcome.errors:
            self._write_error(day_dir, error)

    def _write_error(self, day_dir: Path, error: EndpointError) -> None:
        path = day_dir / f"{error.endpoint}.error.json"
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
        return f"{result.endpoint}.{extension}"

    def _determine_extension(self, result: EndpointResult) -> str:
        payload = result.payload
        if isinstance(payload, bytes):
            fmt = result.scope.get("format")
            if isinstance(fmt, str):
                return fmt.lower()
            return "bin"
        if isinstance(payload, (dict, list)):
            return "json"
        if isinstance(payload, str):
            return "txt"
        return "json"

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
