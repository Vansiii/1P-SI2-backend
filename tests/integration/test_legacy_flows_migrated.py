"""Integration tests migrated from legacy root scripts.

These tests run only when RUN_INTEGRATION_TESTS=1.
"""

import os
import uuid

import pytest
import requests


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def integration_base_url() -> str:
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")

    base_url = os.getenv("INTEGRATION_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    try:
        response = requests.get(f"{base_url}/health", timeout=5)
    except requests.RequestException:
        pytest.skip(f"Backend is not reachable at {base_url}")

    if response.status_code != 200:
        pytest.skip(f"Health check failed at {base_url} with status {response.status_code}")

    return base_url


def _new_email(prefix: str) -> str:
    token = uuid.uuid4().hex[:10]
    return f"{prefix}.{token}@example.com"


def _register_client(base_url: str, email: str, password: str) -> requests.Response:
    return requests.post(
        f"{base_url}/api/v1/clients/register",
        json={
            "first_name": "Test",
            "last_name": "User",
            "email": email,
            "phone": "70000000",
            "password": password,
        },
        timeout=20,
    )


@pytest.fixture(scope="module")
def registered_client(integration_base_url: str) -> dict[str, str]:
    email = _new_email("client")
    password = "TestPass123!"

    register_response = _register_client(integration_base_url, email, password)
    if register_response.status_code == 429:
        pytest.skip("Rate limit reached for /clients/register; retry later or whitelist test IP")
    assert register_response.status_code == 201, register_response.text

    register_data = register_response.json()
    assert register_data["access_token"]
    assert register_data["refresh_token"]
    assert register_data["user"]["email"] == email
    return {
        "email": email,
        "password": password,
        "access_token": register_data["access_token"],
        "refresh_token": register_data["refresh_token"],
    }


def test_register_client_and_unified_login(
    integration_base_url: str,
    registered_client: dict[str, str],
) -> None:

    login_response = requests.post(
        f"{integration_base_url}/api/v1/auth/login/unified",
        json={"email": registered_client["email"], "password": registered_client["password"]},
        timeout=20,
    )
    assert login_response.status_code == 200, login_response.text

    login_data = login_response.json()
    assert login_data["user_type"] == "client"
    assert login_data["user"]["email"] == registered_client["email"]


def test_refresh_rotation_and_reuse_rejected(
    integration_base_url: str,
    registered_client: dict[str, str],
) -> None:
    old_refresh = registered_client["refresh_token"]
    access_token = registered_client["access_token"]

    refresh_response = requests.post(
        f"{integration_base_url}/api/v1/tokens/refresh",
        json={"refresh_token": old_refresh},
        timeout=20,
    )
    assert refresh_response.status_code == 200, refresh_response.text

    refreshed = refresh_response.json()
    assert refreshed["refresh_token"] != old_refresh
    assert refreshed["access_token"]

    reuse_response = requests.post(
        f"{integration_base_url}/api/v1/tokens/refresh",
        json={"refresh_token": old_refresh},
        timeout=20,
    )
    assert reuse_response.status_code in {400, 401}, reuse_response.text

    revoke_response = requests.post(
        f"{integration_base_url}/api/v1/tokens/revoke-all",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    assert revoke_response.status_code == 200, revoke_response.text


def test_password_reset_request_has_consistent_response(
    integration_base_url: str,
    registered_client: dict[str, str],
) -> None:
    existing_email = registered_client["email"]

    existing_response = requests.post(
        f"{integration_base_url}/api/v1/password/reset/request",
        json={"email": existing_email},
        timeout=20,
    )
    assert existing_response.status_code == 200, existing_response.text

    missing_response = requests.post(
        f"{integration_base_url}/api/v1/password/reset/request",
        json={"email": _new_email("missing")},
        timeout=20,
    )
    assert missing_response.status_code == 200, missing_response.text

    assert existing_response.json()["message"] == missing_response.json()["message"]
