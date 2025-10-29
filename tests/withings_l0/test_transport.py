from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agentlab.withings.transport import WithingsTransport
from agentlab.utils.withings_tokens import WithingsTokenBundle, WithingsTokenStore


class DummyResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict[str, object]:
        return self._payload


class DummySession:
    def __init__(self, responses: list[DummyResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def request(self, method: str, url: str, *, data: dict[str, object], timeout: float, headers: dict[str, str]):
        self.calls.append({"method": method, "url": url, "data": data, "headers": headers, "timeout": timeout})
        return self._responses.pop(0)


class DummyStore(WithingsTokenStore):
    def __init__(self, bundle: WithingsTokenBundle) -> None:
        self._bundle = bundle

    def load(self) -> WithingsTokenBundle:  # type: ignore[override]
        return self._bundle

    def save(self, bundle: WithingsTokenBundle) -> None:  # type: ignore[override]
        self._bundle = bundle


def make_bundle() -> WithingsTokenBundle:
    return WithingsTokenBundle(
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        client_id="client",
        client_secret="secret",
    )


def test_paginates_and_sleeps_between_calls() -> None:
    responses = [
        DummyResponse({"body": {"measuregrps": [{"g": 1}], "more": 1, "offset": 42}}),
        DummyResponse({"body": {"measuregrps": [{"g": 2}], "more": 0}}),
    ]
    session = DummySession(responses)
    sleeps: list[float] = []

    transport = WithingsTransport(
        token_store=DummyStore(make_bundle()),
        http_session=session,
        request_delay=1.5,
        sleep=lambda seconds: sleeps.append(seconds),
    )

    groups = transport.get_measures(
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
    )

    assert groups == [{"g": 1}, {"g": 2}]
    assert len(session.calls) == 2
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(1.5, rel=1e-3)
    assert session.calls[1]["data"]["offset"] == 42


def test_default_delay_applies_between_measure_calls() -> None:
    responses = [
        DummyResponse({"body": {"measuregrps": [], "more": 0}}),
        DummyResponse({"body": {"measuregrps": [], "more": 0}}),
    ]
    session = DummySession(responses)
    sleeps: list[float] = []

    transport = WithingsTransport(
        token_store=DummyStore(make_bundle()),
        http_session=session,
        sleep=lambda seconds: sleeps.append(seconds),
    )

    transport.get_measures(
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    transport.get_measures(
        datetime(2025, 1, 2, tzinfo=timezone.utc),
        datetime(2025, 1, 3, tzinfo=timezone.utc),
    )

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(1.0, rel=1e-3)

