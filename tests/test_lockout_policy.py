import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.login_attempt_service import check_account_lockout


class _FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalarResult(self._items)


class _FakeAsyncSession:
    def __init__(self, responses):
        self._responses = responses
        self._index = 0

    async def execute(self, _query):
        if self._index >= len(self._responses):
            items = []
        else:
            items = self._responses[self._index]
            self._index += 1
        return _FakeExecuteResult(items)


def test_level1_lockout_is_five_minutes_from_latest_attempt():
    now = datetime.now(UTC)
    failed_attempts = [
        SimpleNamespace(attempted_at=now - timedelta(minutes=4, seconds=30)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=3, seconds=50)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=3, seconds=10)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=2, seconds=20)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=1, seconds=0)),
    ]
    session = _FakeAsyncSession([failed_attempts])

    is_locked, remaining_seconds, reason = asyncio.run(
        check_account_lockout(
            session=session,
            email="user@example.com",
        )
    )

    assert is_locked is True
    assert 180 <= remaining_seconds <= 320
    assert "5 minutos" in reason


def test_level1_lockout_expires_five_minutes_after_latest_attempt():
    now = datetime.now(UTC)
    failed_attempts = [
        SimpleNamespace(attempted_at=now - timedelta(minutes=14)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=13)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=12)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=11)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=10)),
    ]
    # The second and third queries are needed when level 1 is not active.
    session = _FakeAsyncSession([failed_attempts, failed_attempts, failed_attempts])

    is_locked, remaining_seconds, reason = asyncio.run(
        check_account_lockout(
            session=session,
            email="user@example.com",
        )
    )

    assert is_locked is False
    assert remaining_seconds == 0
    assert reason == ""


def test_level2_lockout_is_thirty_minutes_from_latest_attempt():
    now = datetime.now(UTC)
    failed_15min = [
        SimpleNamespace(attempted_at=now - timedelta(minutes=14)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=13)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=12)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=11)),
    ]
    failed_1hour = [
        SimpleNamespace(attempted_at=now - timedelta(minutes=55)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=50)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=45)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=40)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=35)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=30)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=25)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=20)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=10)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=1)),
    ]
    session = _FakeAsyncSession([failed_15min, failed_1hour])

    is_locked, remaining_seconds, reason = asyncio.run(
        check_account_lockout(
            session=session,
            email="user@example.com",
        )
    )

    assert is_locked is True
    assert 1700 <= remaining_seconds <= 1800
    assert "30 minutos" in reason


def test_level2_lockout_expires_thirty_minutes_after_latest_attempt():
    now = datetime.now(UTC)
    failed_15min = [
        SimpleNamespace(attempted_at=now - timedelta(minutes=14)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=13)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=12)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=11)),
    ]
    failed_1hour = [
        SimpleNamespace(attempted_at=now - timedelta(minutes=59)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=58)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=57)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=56)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=55)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=54)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=53)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=52)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=51)),
        SimpleNamespace(attempted_at=now - timedelta(minutes=31)),
    ]
    failed_24hours = failed_1hour
    session = _FakeAsyncSession([failed_15min, failed_1hour, failed_24hours])

    is_locked, remaining_seconds, reason = asyncio.run(
        check_account_lockout(
            session=session,
            email="user@example.com",
        )
    )

    assert is_locked is False
    assert remaining_seconds == 0
    assert reason == ""
