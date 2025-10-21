"""Utilities for writing Garmin data payloads to disk."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from agentlab.core.garmin import EndpointError, EndpointResult, FetchOutcome


class GarminStorageWriter:
    """Persist Garmin endpoint payloads with atomic writes."""

    def __init__(
        self,
        root: Path,
        *,
        run_id: str | None = None,
        garmin_version: str | None = None,
    ) -> None:
        self.root = root
        self.run_id = run_id
        if garmin_version is None:
            try:
                garmin_version = version("garminconnect")
            except PackageNotFoundError:  # pragma: no cover - defensive
                garmin_version = "unknown"
        self.garmin_version = garmin_version

    def store(self, day: date, outcome: FetchOutcome, *, correlation_id: str | None = None) -> None:
        """Write results and errors for *day* to disk."""

        for result in outcome.results:
            self.write_result(day, result, correlation_id=correlation_id)

        for error in outcome.errors:
            self.write_error(day, error)

    def write_result(self, day: date, result: EndpointResult, *, correlation_id: str | None = None) -> None:
        day_dir = self._ensure_day_dir(day)
        filename = self._result_filename(result)
        payload_bytes = self._serialise_payload(result)
        target_path = day_dir / filename
        self._write_atomic(target_path, payload_bytes)

        run_correlation = correlation_id or (f"{self.run_id}:{day.isoformat()}" if self.run_id else None)
        metadata = self._build_metadata(day, result, target_path, payload_bytes, run_correlation)
        meta_path = self._metadata_path(target_path)
        self._write_atomic(meta_path, json.dumps(metadata, indent=2).encode("utf-8"))

        error_path = self._matching_error_file(day_dir, result.endpoint, result.scope)
        if error_path is not None and error_path.exists():
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
                    return "zip"
                return lowered
            if result.endpoint == "workout-download":
                return "fit"
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
        gear_uuid = scope.get("gearUuid")
        if gear_uuid is not None:
            return f"{endpoint}_{gear_uuid}"
        workout_id = scope.get("workoutId")
        if workout_id is not None:
            return f"{endpoint}_{workout_id}"
        return endpoint

    def _error_filename(self, endpoint: str, scope: dict[str, str | int]) -> str:
        basename = self._compose_basename(endpoint, scope)
        return f"{basename}.error.json"

    def _matching_error_file(
        self,
        day_dir: Path,
        endpoint: str,
        scope: dict[str, str | int],
    ) -> Path | None:
        explicit = day_dir / self._error_filename(endpoint, scope)
        if explicit.exists():
            return explicit

        gear_uuid = scope.get("gearUuid")
        if isinstance(gear_uuid, str):
            legacy = day_dir / f"{endpoint}.error.json"
            if legacy.exists():
                return legacy

        return None

    def _metadata_path(self, payload_path: Path) -> Path:
        return payload_path.with_name(f"{payload_path.name}.meta.json")

    def _build_metadata(
        self,
        day: date,
        result: EndpointResult,
        payload_path: Path,
        payload_bytes: bytes,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        raw_calls: list[Any] = []
        if result.metadata:
            calls = result.metadata.get("garmin_methods")
            if isinstance(calls, list):
                raw_calls = json.loads(json.dumps(calls))

        run_info: dict[str, str] = {}
        if self.run_id is not None:
            run_info["id"] = self.run_id
        if correlation_id is not None:
            run_info["correlation"] = correlation_id

        checksum = hashlib.md5(payload_bytes).hexdigest()

        metadata: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "day": day.isoformat(),
            "endpoint": result.endpoint,
            "scope": result.scope,
            "payload": {
                "file": payload_path.name,
                "extension": payload_path.suffix.lstrip("."),
                "size_bytes": len(payload_bytes),
                "type": self._payload_kind(result.payload),
                "md5": checksum,
            },
            "garminconnect_version": self.garmin_version,
            "garmin_methods": raw_calls,
            "garmin_method_count": len(raw_calls),
        }
        if run_info:
            metadata["run"] = run_info
        return metadata

    @staticmethod
    def _payload_kind(payload: object) -> str:
        if isinstance(payload, bytes):
            return "bytes"
        if isinstance(payload, str):
            return "text"
        if isinstance(payload, (dict, list)):
            return "json"
        if payload is None:
            return "none"
        return payload.__class__.__name__

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
