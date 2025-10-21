"""Core contracts for Garmin data collection workflows."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence


@dataclass(slots=True, frozen=True)
class GarminCredentials:
    """Credential bundle used to authenticate with Garmin Connect."""

    username: str
    password: str
    mfa_code: str | None = None


@dataclass(slots=True, frozen=True)
class GarminFetchRequest:
    """Describe the span and subset of data to collect."""

    start_date: date
    end_date: date
    endpoints: Sequence[str] | None = None

    def iter_dates(self) -> Iterable[date]:
        """Yield each date in the inclusive range."""

        current = self.start_date
        while current <= self.end_date:
            yield current
            current = date.fromordinal(current.toordinal() + 1)

    def includes(self, endpoint: str) -> bool:
        """Return True when *endpoint* should be collected."""

        if self.endpoints is None:
            return True
        return endpoint in self.endpoints


@dataclass(slots=True)
class EndpointResult:
    """Capture the payload fetched for a specific endpoint call."""

    endpoint: str
    scope: dict[str, str | int]
    payload: object
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class EndpointError:
    """Capture details about an endpoint invocation failure."""

    endpoint: str
    scope: dict[str, str | int]
    message: str
    traceback: str


@dataclass(slots=True)
class RetrySummary:
    """Track retry outcomes for a fetch run."""

    scheduled: int = 0
    succeeded: int = 0
    failed: int = 0


@dataclass(slots=True)
class FetchOutcome:
    """Aggregate successful results and failures from a fetch run."""

    results: list[EndpointResult]
    errors: list[EndpointError]
    retries: RetrySummary = field(default_factory=RetrySummary)
