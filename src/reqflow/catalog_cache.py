"""Utilities for caching parsed requirement catalogs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Callable


@dataclass
class _Snapshot:
    signature: tuple[int, int]
    text: str
    parsed: dict[str, Any] = field(default_factory=dict)


class CatalogDigestCache:
    """Cache catalog contents keyed by filesystem signature."""

    def __init__(self) -> None:
        self._cache: dict[Path, _Snapshot] = {}
        self._lock = RLock()

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._cache.clear()

    def invalidate(self, path: Path) -> None:
        """Remove cached data for *path* if present."""
        resolved = path.resolve()
        with self._lock:
            self._cache.pop(resolved, None)

    def parse(
        self,
        path: Path,
        key: str,
        parser: Callable[[str], Any],
        *,
        refresh: bool = False,
    ) -> Any:
        """Return parsed data for *path* using *parser*, reusing cached content."""

        resolved = path.resolve()
        with self._lock:
            snapshot = self._ensure_snapshot(resolved, refresh=refresh)
            if refresh:
                snapshot.parsed.pop(key, None)
            if key not in snapshot.parsed:
                snapshot.parsed[key] = parser(snapshot.text)
            return snapshot.parsed[key]

    def text(self, path: Path, *, refresh: bool = False) -> str:
        """Return cached text for *path*, reading from disk only when changed."""

        resolved = path.resolve()
        with self._lock:
            snapshot = self._ensure_snapshot(resolved, refresh=refresh)
            return snapshot.text

    def _ensure_snapshot(self, path: Path, *, refresh: bool) -> _Snapshot:
        snapshot = self._cache.get(path)
        signature = self._signature(path)
        if refresh or snapshot is None or snapshot.signature != signature:
            text = path.read_text(encoding="utf-8")
            snapshot = _Snapshot(signature=signature, text=text)
            self._cache[path] = snapshot
        return snapshot

    @staticmethod
    def _signature(path: Path) -> tuple[int, int]:
        stat_result = path.stat()
        return (int(stat_result.st_mtime_ns), stat_result.st_size)


catalog_cache = CatalogDigestCache()
