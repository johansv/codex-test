from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agentlab.metadata import DayStats, RunError, RunMetaReader, RunMetaWriter, RunParams
from agentlab.utils.storage import GarminStorageWriter

_PII_TOKENS = (
    "token",
    "secret",
    "password",
    "client_id",
    "client_secret",
)

__all__ = ["WithingsFetcher", "RetryAfter", "NetworkError"]


class RetryAfter(RuntimeError):
    """Signal that the upstream API asked us to retry later."""

    def __init__(self, retry_after_s: float, message: str | None = None) -> None:
        super().__init__(message or "Retry after")
        self.retry_after_s = float(retry_after_s)


class NetworkError(RuntimeError):
    """Raised when the transport fails to fetch data."""


@dataclass(slots=True)
class _RequestWindow:
    start: datetime
    end: datetime

    @property
    def start_iso(self) -> str:
        return self.start.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()


@dataclass(slots=True, frozen=True)
class _ResumeState:
    manifest_path: Path | None
    first_incomplete: date | None
    manifest: dict[str, Any] | None


class ManifestReader:
    """Locate existing run manifests and surface resume hints."""

    def __init__(self, out_root: Path) -> None:
        self._runs_dir = Path(out_root) / "runs"

    def resume_from_first_incomplete(self, run_id: str | None = None) -> _ResumeState:
        manifest_path = self._latest_manifest(run_id)
        if manifest_path is None:
            return _ResumeState(None, None, None)

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        progress = data.get("progress", {}) or {}

        first_incomplete: date | None = None
        for day_key in sorted(progress):
            entry = progress.get(day_key) or {}
            if entry.get("status") not in {"done", "skipped"}:
                first_incomplete = date.fromisoformat(day_key)
                break

        return _ResumeState(manifest_path, first_incomplete, data)

    def _latest_manifest(self, run_id: str | None) -> Path | None:
        if not self._runs_dir.exists():
            return None
        pattern = f"run_*_{run_id}.meta.json" if run_id else "run_*.meta.json"
        matches = sorted(self._runs_dir.glob(pattern))
        if not matches:
            return None
        return matches[-1]


class WithingsFetcher:
    """Collect Withings L0 measures data into the local out_root."""

    _MAX_ATTEMPTS = 3
    _BACKOFF_CAP_SECONDS = 15 * 60
    _SLEEP_CAP_SECONDS = 0.05  # keep retries fast during tests

    def __init__(
        self,
        transport: Any,
        *,
        timezone: str = "Europe/Stockholm",
        day_cutover: str = "00:00",
        run_id_provider: Callable[[], str] | None = None,
    ) -> None:
        self._transport = transport
        self._timezone_name = timezone
        self._timezone = self._resolve_timezone(timezone)
        self._cutover = self._parse_cutover(day_cutover)
        self._run_id_provider = run_id_provider or self._default_run_id
        self._random = random.Random(0)
        self._sleep = time.sleep
        self._last_manifest_path: Path | None = None
        self._last_manifest: dict[str, Any] | None = None
        self._last_run_id: str | None = None

    @property
    def last_manifest_path(self) -> Path | None:
        return self._last_manifest_path

    @property
    def last_manifest(self) -> dict[str, Any] | None:
        return self._last_manifest

    @property
    def last_run_id(self) -> str | None:
        return self._last_run_id

    def fetch_date_range(
        self,
        *,
        out_root: Path,
        start_date: date,
        end_date: date,
        skip_existing: bool = False,
        dry_run: bool = False,  # unused for now; parity with Garmin signature
        resume: bool = False,
        debug: bool = False,
    ) -> None:
        if end_date < start_date:
            raise ValueError("end_date cannot be earlier than start_date")

        out_root = Path(out_root)
        out_root.mkdir(parents=True, exist_ok=True)

        total_days = max(1, (end_date - start_date).days + 1)
        run_id = self._resolve_run_id()
        self._last_run_id = run_id
        resume_state = (
            ManifestReader(out_root).resume_from_first_incomplete(run_id)
            if resume
            else _ResumeState(None, None, None)
        )
        if resume_state.manifest_path is not None:
            self._last_manifest_path = resume_state.manifest_path
            self._last_manifest = resume_state.manifest

        effective_start = start_date
        if resume_state.first_incomplete and resume_state.first_incomplete > effective_start:
            effective_start = resume_state.first_incomplete

        writer = RunMetaWriter(
            out_root=out_root,
            timezone=self._timezone_name,
            run_id=run_id,
            vendor_label="withings",
        )
        writer.start_run(
            RunParams(
                start_date=effective_start,
                end_date=end_date,
                preset="withings-l0",
                skip_existing=skip_existing,
                resume=resume,
            ),
            vendor="withings",
            days_scheduled=total_days,
            dry_run=dry_run,
            out_root=out_root,
        )

        progress = resume_state.manifest.get("progress", {}) if resume_state.manifest else {}
        days = list(self._iter_days(effective_start, end_date))
        if progress:
            days = [
                day
                for day in days
                if progress.get(day.isoformat(), {}).get("status") not in {"done", "skipped"}
            ]
        if not days:
            self._record_manifest_snapshot(out_root, run_id)
            return

        for day in days:
            writer.start_day(day)
            request = self._request_window(day)
            day_started = time.perf_counter()
            if debug:
                print(
                    f"[withings] {day.isoformat()} -> window {request.start_iso} to {request.end_iso}",
                    file=sys.stderr,
                )

            try:
                records = self._fetch_with_retry(request)
            except (NetworkError, RetryAfter) as exc:
                self._handle_day_error(
                    out_root=out_root,
                    day=day,
                    run_id=run_id,
                    writer=writer,
                    stats=self._day_stats(
                        ok=0,
                        fail=1,
                        skipped=0,
                        bytes_payload=0,
                        started=day_started,
                    ),
                    request=request,
                    error_code="HTTP_429" if isinstance(exc, RetryAfter) else "WITHINGS_ERROR",
                    error_msg=str(exc),
                    retry_after=getattr(exc, "retry_after_s", None),
                    debug=debug,
                )
                self._record_manifest_snapshot(out_root, run_id)
                raise
            except Exception as exc:  # pragma: no cover - defensive
                self._handle_day_error(
                    out_root=out_root,
                    day=day,
                    run_id=run_id,
                    writer=writer,
                    stats=self._day_stats(
                        ok=0,
                        fail=1,
                        skipped=0,
                        bytes_payload=0,
                        started=day_started,
                    ),
                    request=request,
                    error_code="WITHINGS_ERROR",
                    error_msg=str(exc),
                    debug=debug,
                )
                self._record_manifest_snapshot(out_root, run_id)
                raise

            success_count, bytes_written, skipped_count = self._persist_records(
                out_root=out_root,
                run_id=run_id,
                records=records,
                request=request,
                day=day,
                skip_existing=skip_existing,
                debug=debug,
            )

            stats = self._day_stats(
                ok=success_count,
                fail=0,
                skipped=skipped_count,
                bytes_payload=bytes_written,
                started=day_started,
            )
            writer.end_day(day, status="done", stats=stats)

        writer.finish()
        self._record_manifest_snapshot(out_root, run_id)

    # Internals -----------------------------------------------------------------

    def _fetch_with_retry(self, request: _RequestWindow) -> list[dict[str, Any]]:
        attempts = 0
        while attempts < self._MAX_ATTEMPTS:
            attempts += 1
            try:
                raw = self._transport.get_measures(request.start, request.end)
            except RetryAfter as exc:
                if attempts >= self._MAX_ATTEMPTS:
                    raise
                delay = self._compute_backoff(attempts, exc.retry_after_s)
                self._sleep(min(delay, self._SLEEP_CAP_SECONDS))
                continue
            return self._normalise_records(raw)
        raise RuntimeError("exhausted retry attempts")  # pragma: no cover

    def _persist_records(
        self,
        *,
        out_root: Path,
        run_id: str,
        records: list[dict[str, Any]],
        request: _RequestWindow,
        day: date,
        skip_existing: bool,
        debug: bool,
    ) -> tuple[int, int, int]:
        grouped = self._bucket_by_day(records)
        if not grouped:
            grouped = {day: []}
        success_for_day = 0
        skipped_for_day = 0
        bytes_for_day = 0

        for target_day, payload in sorted(grouped.items()):
            day_dir = self._ensure_day_dir(out_root, target_day)
            slug = self._payload_slug(
                request=request,
                target_day=target_day,
                payload=payload,
            )
            payload_path = day_dir / f"measures-{slug}.json"
            meta_path = payload_path.with_name(f"{payload_path.name}.meta.json")

            if skip_existing and payload_path.exists() and meta_path.exists():
                meta = self._build_meta(
                    run_id=run_id,
                    target_day=target_day,
                    request=request,
                    status="skipped",
                    payload_path=payload_path,
                    payload_size=0,
                    payload_md5="",
                    items=0,
                    exists=False,
                    out_root=out_root,
                )
                self._write_meta(meta_path, meta)
                if target_day == day:
                    skipped_for_day += 1
                if debug:
                    print(
                        f"[withings] {target_day.isoformat()} skip {payload_path.name}",
                        file=sys.stderr,
                    )
                continue

            bytes_written, payload_md5 = self._write_json(payload_path, payload)
            meta = self._build_meta(
                run_id=run_id,
                target_day=target_day,
                request=request,
                status="success",
                payload_path=payload_path,
                payload_size=bytes_written,
                payload_md5=payload_md5,
                items=len(payload),
                exists=True,
                out_root=out_root,
            )
            self._write_meta(meta_path, meta)

            if target_day == day:
                success_for_day += 1
                bytes_for_day += bytes_written
                if debug:
                    print(
                        f"[withings] {target_day.isoformat()} wrote {payload_path.name} items={len(payload)} bytes={bytes_written}",
                        file=sys.stderr,
                    )
            elif debug:
                print(
                    f"[withings] {target_day.isoformat()} wrote {payload_path.name} (routed)",
                    file=sys.stderr,
                )

        return success_for_day, bytes_for_day, skipped_for_day

    def _handle_day_error(
        self,
        *,
        out_root: Path,
        day: date,
        run_id: str,
        writer: RunMetaWriter,
        stats: DayStats,
        request: _RequestWindow,
        error_code: str,
        error_msg: str,
        retry_after: float | None = None,
        debug: bool = False,
    ) -> None:
        day_dir = self._ensure_day_dir(out_root, day)
        error_payload = {
            "run_id": run_id,
            "date": day.isoformat(),
            "request": {"from": request.start_iso, "to": request.end_iso},
            "error": {"code": error_code, "message": error_msg},
        }
        if retry_after is not None:
            error_payload["error"]["retry_after_s"] = retry_after
        error_json_path = day_dir / "measures.error.json"
        error_meta_path = error_json_path.with_name(f"{error_json_path.name}.meta.json")
        self._write_json(error_json_path, error_payload)
        meta = self._build_meta(
            run_id=run_id,
            target_day=day,
            request=request,
            status="error",
            payload_path=error_json_path,
            payload_size=0,
            payload_md5="",
            items=0,
            exists=False,
            out_root=out_root,
            error_info={
                "code": error_code,
                "msg": error_msg,
                "retry_after_s": retry_after,
            },
        )
        self._write_meta(error_meta_path, meta)
        writer.end_day(day, status="partial", stats=stats, last_endpoint="measures")
        writer.abort(
            RunError(code=error_code, msg=error_msg, last_endpoint="measures")
        )
        if debug:
            print(
                f"[withings] {day.isoformat()} abort {error_code}: {error_msg}",
                file=sys.stderr,
            )

    def _day_stats(
        self,
        *,
        ok: int,
        fail: int,
        skipped: int,
        bytes_payload: int,
        started: float,
    ) -> DayStats:
        duration = max(0, int(round(time.perf_counter() - started)))
        return DayStats(
            endpoints_ok=ok,
            endpoints_fail=fail,
            endpoints_skipped=skipped,
            bytes_payload=bytes_payload,
            duration_s=duration,
        )

    def _bucket_by_day(self, records: Iterable[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
        buckets: dict[date, list[dict[str, Any]]] = {}
        for record in records:
            local_dt = self._record_timestamp(record)
            if local_dt is None:
                continue
            target_day = local_dt.date()
            if local_dt.time() < self._cutover:
                target_day = target_day - timedelta(days=1)
            buckets.setdefault(target_day, []).append(record)
        return buckets

    def _record_timestamp(self, record: dict[str, Any]) -> datetime | None:
        timestamp: datetime | None = None
        timestamp_raw = record.get("timestamp")
        if isinstance(timestamp_raw, str):
            try:
                timestamp = datetime.fromisoformat(timestamp_raw)
            except ValueError:
                timestamp = None
        if timestamp is None:
            for field in ("date", "created"):
                value = record.get(field)
                if isinstance(value, (int, float)):
                    timestamp = datetime.fromtimestamp(float(value), tz=dt_timezone.utc)
                    break
        if timestamp is None:
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=self._timezone)
        return timestamp.astimezone(self._timezone)

    def _write_json(self, path: Path, payload: Any) -> tuple[int, str]:
        data = json.dumps(payload, indent=2, ensure_ascii=False)
        encoded = data.encode("utf-8")
        GarminStorageWriter._write_atomic(path, encoded)
        return len(encoded), hashlib.md5(encoded).hexdigest()

    def _write_meta(self, path: Path, meta: dict[str, Any]) -> None:
        data = json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8")
        GarminStorageWriter._write_atomic(path, data)

    def _build_meta(
        self,
        *,
        run_id: str,
        target_day: date,
        request: _RequestWindow,
        status: str,
        payload_path: Path,
        payload_size: int,
        payload_md5: str,
        items: int,
        exists: bool,
        out_root: Path,
        error_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload_exists = status == "success" and exists
        payload_info = {
            "file": self._relative_payload_path(out_root, payload_path),
            "extension": self._normalise_extension(payload_path.suffix),
            "size_bytes": payload_size if payload_exists else 0,
            "md5": payload_md5 if payload_exists else "",
            "type": "application/json",
            "exists": payload_exists,
        }
        start_unix = int(request.start.timestamp())
        end_unix = int(request.end.timestamp())
        request_block = {
            "method": "GET",
            "endpoint_path": "withings.measure.getmeas",
            "params": self._sanitize_params(
                {
                    "action": "getmeas",
                    "category": 1,
                    "startdate": start_unix,
                    "enddate": end_unix,
                }
            ),
        }
        error_block = None
        if status == "error":
            code = (error_info or {}).get("code", "WITHINGS_ERROR")
            message = (error_info or {}).get("msg", "")
            error_block = {"code": str(code), "message": str(message)}
        metadata: dict[str, Any] = {
            "schema_version": "meta/1.0",
            "vendor": "withings",
            "endpoint": "measures",
            "day": target_day.isoformat(),
            "scope": {
                "date_from": request.start_iso,
                "date_to": request.end_iso,
                "data_scope": "day",
                "day_context": self._timezone_name,
            },
            "status": status,
            "payload": payload_info,
            "items": items if payload_exists else 0,
            "request": request_block,
            "error": error_block,
            "run": {"id": run_id},
        }
        return metadata

    @staticmethod
    def _relative_payload_path(out_root: Path, payload_path: Path) -> str:
        try:
            return payload_path.relative_to(out_root).as_posix()
        except ValueError:
            return payload_path.as_posix()

    @staticmethod
    def _normalise_extension(extension: str) -> str:
        if not extension:
            return ".json"
        return extension if extension.startswith(".") else f".{extension}"

    @staticmethod
    def _sanitize_params(value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[Any, Any] = {}
            for key, val in value.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in _PII_TOKENS):
                    sanitized[key] = "***"
                else:
                    sanitized[key] = WithingsFetcher._sanitize_params(val)
            return sanitized
        if isinstance(value, list):
            return [WithingsFetcher._sanitize_params(item) for item in value]
        if isinstance(value, tuple):
            return [WithingsFetcher._sanitize_params(item) for item in value]
        if isinstance(value, str):
            lowered = value.lower()
            if any(token in lowered for token in _PII_TOKENS) or "@" in value:
                return "***"
            return value
        return value

    def _request_window(self, day: date) -> _RequestWindow:
        start = datetime.combine(day, dt_time.min, tzinfo=self._timezone)
        end = start + timedelta(days=1)
        return _RequestWindow(start=start, end=end)

    def _payload_slug(
        self,
        *,
        request: _RequestWindow,
        target_day: date,
        payload: list[dict[str, Any]],
    ) -> str:
        local_ts = None
        return target_day.strftime("%Y%m%d")

    def _iter_days(self, start: date, end: date) -> Iterable[date]:
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)

    def _record_manifest_snapshot(self, out_root: Path, run_id: str) -> None:
        runs_dir = out_root / "runs"
        matches = sorted(runs_dir.glob(f"run_*_{run_id}.meta.json"))
        if not matches:
            self._last_manifest_path = None
            self._last_manifest = None
            return
        self._last_manifest_path = matches[-1]
        try:
            reader = RunMetaReader(out_root, run_id)
            self._last_manifest = reader.load()
        except FileNotFoundError:  # pragma: no cover - race safe
            self._last_manifest = None

    def _normalise_records(self, payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [record for record in payload if isinstance(record, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []

    def _resolve_run_id(self) -> str:
        run_id = self._run_id_provider()
        if not isinstance(run_id, str) or not run_id:
            return self._default_run_id()
        return run_id

    @staticmethod
    def _default_run_id() -> str:
        return f"withings-{int(time.time())}"

    @staticmethod
    def _resolve_timezone(name: str) -> ZoneInfo | dt_timezone:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:  # pragma: no cover
            if name == "UTC":
                return dt_timezone.utc
            raise RuntimeError(
                f"Time zone '{name}' is unavailable. Install the 'tzdata' package or configure zoneinfo support."
            )

    @staticmethod
    def _parse_cutover(value: str) -> dt_time:
        try:
            hours, minutes = value.split(":", 1)
            hour = int(hours)
            minute = int(minutes)
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid day_cutover: {value!r}") from exc
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError(f"Invalid day_cutover: {value!r}")
        return dt_time(hour=hour, minute=minute, tzinfo=None)

    def _now(self) -> datetime:
        return datetime.now(self._timezone)

    def _ensure_day_dir(self, out_root: Path, day: date) -> Path:
        day_dir = out_root / "l0" / "withings" / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _compute_backoff(self, attempt: int, retry_after: float | None) -> float:
        base = 2 ** max(0, attempt - 1)
        jitter = self._random.uniform(0.5, 1.5)
        delay = base * jitter
        if retry_after is not None:
            delay = max(delay, float(retry_after))
        return min(delay, self._BACKOFF_CAP_SECONDS)

