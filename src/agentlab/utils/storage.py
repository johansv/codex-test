"""Utilities for writing Garmin data payloads to disk."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timezone, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping

_PII_TOKENS = (
    "token",
    "secret",
    "password",
    "client_id",
    "client_secret",
)

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

    def store(
        self,
        day: date,
        outcome: FetchOutcome,
        *,
        _correlation_id: str | None = None,
        day_overrides: Mapping[str, date] | None = None,
        default_override: date | None = None,
    ) -> None:
        """Write results and errors for *day* to disk.

        When *day_overrides* is provided, endpoints listed in the mapping are stored
        under the mapped day instead of *day*. When *default_override* is provided,
        endpoints not listed in *day_overrides* default to that override day.
        """

        overrides = dict(day_overrides or {})

        for result in outcome.results:
            target_day = overrides.get(result.endpoint, default_override) or day
            self.write_result(target_day, result)

        for error in outcome.errors:
            target_day = overrides.get(error.endpoint, default_override) or day
            self.write_error(target_day, error)

    def write_result(
        self,
        day: date,
        result: EndpointResult,
        *,
        correlation_id: str | None = None,
        _correlation_id: str | None = None,
    ) -> None:
        # Accept both the legacy _correlation_id keyword and the public correlation_id name.
        _ = correlation_id or _correlation_id
        day_dir = self._ensure_day_dir(day)
        filename = self._result_filename(result)
        payload_bytes = self._serialise_payload(result)
        target_path = day_dir / filename
        self._write_atomic(target_path, payload_bytes)

        checksum = hashlib.md5(payload_bytes).hexdigest()
        media_type = self._media_type_for_extension(target_path.suffix or ".json")
        request_block = self._build_request_block(result.endpoint, result.scope, result.metadata)
        self._write_metadata(
            day=day,
            endpoint=result.endpoint,
            payload_path=target_path,
            status="success",
            payload_exists=True,
            size_bytes=len(payload_bytes),
            md5=checksum,
            media_type=media_type,
            items=self._count_items(result.payload),
            request=request_block,
            day_context="local",
            error=None,
        )
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

        error_payload_path = path
        media_type = self._media_type_for_extension(error_payload_path.suffix or ".json")
        request_block = self._build_request_block(error.endpoint, error.scope, None)

        self._write_metadata(
            day=day,
            endpoint=error.endpoint,
            payload_path=error_payload_path,
            status="error",
            payload_exists=False,
            size_bytes=0,
            md5="",
            media_type=media_type,
            items=0,
            request=request_block,
            day_context="local",
            error={"code": "GARMIN_ERROR", "message": error.message},
        )

    def _ensure_day_dir(self, day: date) -> Path:
        day_dir = self.root / "l0" / "garmin" / day.isoformat()
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
        device_id = scope.get("deviceId")
        if device_id is not None:
            return f"{endpoint}_{device_id}"
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

    def _write_metadata(
        self,
        *,
        day: date,
        endpoint: str,
        payload_path: Path,
        status: str,
        payload_exists: bool,
        size_bytes: int,
        md5: str,
        media_type: str,
        items: int,
        request: dict[str, Any],
        day_context: str,
        error: dict[str, str] | None,
    ) -> None:
        date_from, date_to = self._day_window_iso(day)
        payload_info = {
            "file": self._relative_payload_path(payload_path),
            "extension": self._normalise_extension(payload_path.suffix),
            "size_bytes": size_bytes if payload_exists else 0,
            "md5": md5 if payload_exists else "",
            "type": media_type,
            "exists": payload_exists,
        }
        metadata = {
            "schema_version": "meta/1.0",
            "vendor": "garmin",
            "endpoint": endpoint,
            "day": day.isoformat(),
            "scope": {
                "date_from": date_from,
                "date_to": date_to,
                "data_scope": "day",
                "day_context": day_context or "local",
            },
            "status": status,
            "payload": payload_info,
            "items": items,
            "request": request,
            "error": error,
            "run": {"id": self.run_id or ""},
        }
        meta_path = self._metadata_path(payload_path)
        self._write_atomic(meta_path, json.dumps(metadata, indent=2).encode("utf-8"))

    def _relative_payload_path(self, payload_path: Path) -> str:
        try:
            return payload_path.relative_to(self.root).as_posix()
        except ValueError:
            return payload_path.as_posix()

    @staticmethod
    def _normalise_extension(extension: str) -> str:
        if not extension:
            return ".json"
        return extension if extension.startswith(".") else f".{extension}"

    @staticmethod
    def _media_type_for_extension(extension: str) -> str:
        ext = (extension or "").lower()
        if not ext.startswith("."):
            ext = f".{ext}" if ext else ".json"
        if ext == ".json":
            return "application/json"
        return "application/octet-stream"

    @staticmethod
    def _day_window_iso(day: date) -> tuple[str, str]:
        start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1) - timedelta(seconds=1)
        return start.isoformat(), end.isoformat()

    @staticmethod
    def _count_items(payload: Any) -> int:
        if payload is None:
            return 0
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            if "items" in payload:
                items = payload.get("items")
                if isinstance(items, list):
                    return len(items)
                if isinstance(items, dict):
                    return len(items)
                if items is None:
                    return 0
                return 1
            return 1 if payload else 0
        if isinstance(payload, (bytes, str)):
            return 1 if payload else 0
        return 1

    def _sanitize_params(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[Any, Any] = {}
            for key, val in value.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in _PII_TOKENS):
                    sanitized[key] = "***REDACTED***"
                else:
                    sanitized[key] = self._sanitize_params(val)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_params(item) for item in value]
        if isinstance(value, tuple):
            return [self._sanitize_params(item) for item in value]
        if isinstance(value, str):
            lowered = value.lower()
            if "@" in value:
                return "[redacted]"
            if any(token in lowered for token in _PII_TOKENS):
                return "***REDACTED***"
            return value
        return value

    def _build_request_block(
        self,
        endpoint: str,
        scope: dict[str, Any],
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        method = "LOCAL"
        endpoint_path = endpoint
        params: dict[str, Any] = {}
        if scope:
            params["scope"] = self._sanitize_params(scope)
        if metadata:
            calls = metadata.get("api_calls")
            if isinstance(calls, list) and calls:
                first_call = calls[0]
                call_name = str(first_call.get("name") or "").strip()
                if call_name:
                    endpoint_path = f"garmin.{call_name}"
                    method = self._infer_http_method(call_name)
                kwargs = first_call.get("kwargs")
                if isinstance(kwargs, dict) and kwargs:
                    params["kwargs"] = self._sanitize_params(kwargs)
                args = first_call.get("args")
                if isinstance(args, (list, tuple)) and args:
                    params["args"] = self._sanitize_params(list(args))
        if "scope" not in params:
            params["scope"] = {}
        return {
            "method": method,
            "endpoint_path": endpoint_path,
            "params": params,
        }

    @staticmethod
    def _infer_http_method(call_name: str) -> str:
        lowered = call_name.lower()
        if lowered.startswith("get"):
            return "GET"
        if lowered.startswith("post") or lowered.startswith("create") or lowered.startswith("set"):
            return "POST"
        return "LOCAL"

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

