import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.schemas.profile import ClientProfilePublic
from app.schemas.profile import DeleteAccountRequest, UpdateProfileRequest
from app.services import auth_service


class _FakeExecuteResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, scalar_values):
        self._scalar_values = list(scalar_values)
        self.refresh_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self._execute_value = None

    async def scalar(self, _query):
        if not self._scalar_values:
            return None
        return self._scalar_values.pop(0)

    async def execute(self, _query):
        return _FakeExecuteResult(self._execute_value)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1

    async def refresh(self, _obj):
        self.refresh_calls += 1


def _build_user(user_type: str = "client"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=101,
        first_name="Juan",
        last_name="Perez",
        email="juan.perez@example.com",
        phone="70000000",
        user_type=user_type,
        is_active=True,
        email_verified=False,
        two_factor_enabled=False,
        last_login=None,
        blocked_until=None,
        created_at=now,
        updated_at=now,
        password_hash="hashed-password",
    )


def _build_client_specific():
    return SimpleNamespace(
        id=101,
        direccion="",
        ci=None,
        fecha_nacimiento=None,
    )


@pytest.mark.parametrize(
    "payload_data",
    [
        {"ci": "1234567"},
        {"direccion": "Av. Siempre Viva", "ci": "987654"},
    ],
)
def test_update_profile_rejects_disallowed_fields_for_workshop(payload_data):
    user = _build_user(user_type="workshop")
    workshop_specific = SimpleNamespace(
        id=101,
        workshop_name="Mi Taller",
        owner_name="Juan Perez",
        workshop_phone="72222222",
        latitude=-17.78,
        longitude=-63.18,
        address="",
        description="",
        coverage_radius_km=10,
        is_available=True,
        is_verified=False,
    )
    session = _FakeAsyncSession([user, workshop_specific])

    payload = UpdateProfileRequest(**payload_data)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_service.update_profile(session, user.id, payload))

    assert exc_info.value.status_code == 403
    assert "no pueden actualizarse" in exc_info.value.detail


def test_update_profile_updates_client_fields_and_logs(monkeypatch):
    user = _build_user(user_type="client")
    client_specific = _build_client_specific()
    session = _FakeAsyncSession([user, client_specific])

    async def _fake_log_action(**_kwargs):
        return None

    async def _fake_get_profile(_session, _user_id):
        return ClientProfilePublic(
            id=_user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            phone=user.phone,
            user_type=user.user_type,
            is_active=user.is_active,
            email_verified=user.email_verified,
            two_factor_enabled=user.two_factor_enabled,
            last_login=user.last_login,
            last_password_change_at=None,
            created_at=user.created_at,
            updated_at=user.updated_at,
            direccion=client_specific.direccion,
            ci=client_specific.ci,
            fecha_nacimiento=client_specific.fecha_nacimiento,
        )

    monkeypatch.setattr(auth_service, "log_action", _fake_log_action)
    monkeypatch.setattr(auth_service, "get_current_user_profile_data", _fake_get_profile)

    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest-agent"},
    )

    payload = UpdateProfileRequest(
        first_name="Pedro",
        direccion="Av. Principal 123",
        ci="1234567",
    )

    response = asyncio.run(auth_service.update_profile(session, user.id, payload, request))

    assert response.message == "Perfil actualizado exitosamente"
    assert user.first_name == "Pedro"
    assert client_specific.direccion == "Av. Principal 123"
    assert client_specific.ci == "1234567"
    assert session.commit_calls == 1
    assert session.refresh_calls == 2


def test_get_current_user_profile_data_returns_enriched_client_profile():
    user = _build_user(user_type="client")
    client_specific = _build_client_specific()
    client_specific.direccion = "Calle A"
    client_specific.ci = "7654321"
    last_password_change_at = datetime.now(UTC)

    session = _FakeAsyncSession([user, client_specific])
    session._execute_value = last_password_change_at

    profile = asyncio.run(auth_service.get_current_user_profile_data(session, user.id))

    assert profile.id == user.id
    assert profile.user_type == "client"
    assert profile.direccion == "Calle A"
    assert profile.ci == "7654321"
    assert profile.two_factor_enabled is False
    assert profile.last_password_change_at == last_password_change_at


def test_delete_account_deactivates_user_and_revokes_sessions(monkeypatch):
    user = _build_user(user_type="client")
    session = _FakeAsyncSession([user])

    async def _fake_revoke_all_user_tokens(_session, _user_id):
        return 3

    async def _fake_log_action(**_kwargs):
        return None

    async def _fake_send_security_notification_email(**_kwargs):
        return True

    monkeypatch.setattr(auth_service, "verify_password", lambda current_password, _hash: current_password == "correcta")
    monkeypatch.setattr(auth_service, "revoke_all_user_tokens", _fake_revoke_all_user_tokens)
    monkeypatch.setattr(auth_service, "log_action", _fake_log_action)
    monkeypatch.setattr(auth_service, "send_security_notification_email", _fake_send_security_notification_email)

    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest-agent"},
    )

    payload = DeleteAccountRequest(current_password="correcta")

    response = asyncio.run(auth_service.delete_account(session, user.id, payload, request))

    assert response.sessions_revoked == 3
    assert user.is_active is False
    assert user.two_factor_enabled is False
    assert user.blocked_until is None


def test_delete_account_rejects_wrong_password(monkeypatch):
    user = _build_user(user_type="client")
    session = _FakeAsyncSession([user])

    monkeypatch.setattr(auth_service, "verify_password", lambda *_args, **_kwargs: False)

    payload = DeleteAccountRequest(current_password="incorrecta")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_service.delete_account(session, user.id, payload))

    assert exc_info.value.status_code == 400
    assert "contraseña actual" in exc_info.value.detail
