"""Integration tests for UC10 incident AI endpoints.

These tests run only when RUN_INTEGRATION_TESTS=1 and required
environment variables are provided.
"""

from __future__ import annotations

import os

import pytest
import requests


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def integration_base_url() -> str:
    """Return validated integration base URL or skip tests."""
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")

    base_url = os.getenv("INTEGRATION_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    try:
        health_response = requests.get(f"{base_url}/health", timeout=5)
    except requests.RequestException:
        pytest.skip(f"Backend is not reachable at {base_url}")

    if health_response.status_code != 200:
        pytest.skip(
            f"Health check failed at {base_url} with status {health_response.status_code}"
        )

    return base_url


@pytest.fixture(scope="module")
def integration_incident_context() -> dict[str, str | int | None]:
    """Load and validate required credentials/incident context from env."""
    incident_id_raw = os.getenv("INTEGRATION_INCIDENT_ID")
    admin_token = os.getenv("INTEGRATION_ADMIN_TOKEN")
    owner_token = os.getenv("INTEGRATION_INCIDENT_OWNER_TOKEN")

    missing_vars = [
        variable_name
        for variable_name, variable_value in {
            "INTEGRATION_INCIDENT_ID": incident_id_raw,
            "INTEGRATION_ADMIN_TOKEN": admin_token,
        }.items()
        if not variable_value
    ]
    if missing_vars:
        pytest.skip(
            "Missing integration variables: "
            + ", ".join(missing_vars)
            + ". Provide them to run UC10 endpoint tests."
        )

    try:
        incident_id = int(incident_id_raw)
    except (TypeError, ValueError):
        pytest.skip("INTEGRATION_INCIDENT_ID must be a valid integer")

    return {
        "incident_id": incident_id,
        "admin_token": admin_token,
        "owner_token": owner_token,
    }


def _auth_headers(access_token: str) -> dict[str, str]:
    """Build bearer authorization headers."""
    return {"Authorization": f"Bearer {access_token}"}


def test_01_process_incident_ai_endpoint(
    integration_base_url: str,
    integration_incident_context: dict[str, str | int | None],
) -> None:
    """POST /procesar-ia should return queued or already-completed analysis."""
    incident_id = int(integration_incident_context["incident_id"])
    admin_token = str(integration_incident_context["admin_token"])

    response = requests.post(
        f"{integration_base_url}/api/v1/incidentes/{incident_id}/procesar-ia",
        headers=_auth_headers(admin_token),
        timeout=20,
    )

    assert response.status_code in {200, 202}, response.text

    payload = response.json()
    assert "data" in payload
    assert int(payload["data"]["incident_id"]) == incident_id
    assert payload["data"]["status"] in {"pending", "processing", "completed", "failed"}


def test_02_reprocess_incident_ai_endpoint(
    integration_base_url: str,
    integration_incident_context: dict[str, str | int | None],
) -> None:
    """POST /reprocesar-ia should always enqueue a new AI run."""
    incident_id = int(integration_incident_context["incident_id"])
    admin_token = str(integration_incident_context["admin_token"])

    response = requests.post(
        f"{integration_base_url}/api/v1/incidentes/{incident_id}/reprocesar-ia",
        headers=_auth_headers(admin_token),
        timeout=20,
    )

    assert response.status_code == 202, response.text

    payload = response.json()
    assert "data" in payload
    assert int(payload["data"]["incident_id"]) == incident_id
    assert payload["data"]["status"] in {"pending", "processing", "completed", "failed"}


def test_03_get_incident_ai_analysis_history_endpoint(
    integration_base_url: str,
    integration_incident_context: dict[str, str | int | None],
) -> None:
    """GET /analisis-ia/historial should return a list response."""
    incident_id = int(integration_incident_context["incident_id"])
    admin_token = str(integration_incident_context["admin_token"])

    response = requests.get(
        f"{integration_base_url}/api/v1/incidentes/{incident_id}/analisis-ia/historial",
        headers=_auth_headers(admin_token),
        timeout=20,
    )

    assert response.status_code == 200, response.text

    payload = response.json()
    assert "data" in payload
    assert isinstance(payload["data"], list)

    if payload["data"]:
        latest = payload["data"][0]
        assert int(latest["incident_id"]) == incident_id
        assert latest["status"] in {"pending", "processing", "completed", "failed"}


def test_04_get_latest_incident_ai_analysis_endpoint(
    integration_base_url: str,
    integration_incident_context: dict[str, str | int | None],
) -> None:
    """GET /analisis-ia should return latest analysis for the owner-access token."""
    incident_id = int(integration_incident_context["incident_id"])
    owner_token = integration_incident_context["owner_token"]

    if not owner_token:
        pytest.skip(
            "INTEGRATION_INCIDENT_OWNER_TOKEN is required to validate /analisis-ia access"
        )

    response = requests.get(
        f"{integration_base_url}/api/v1/incidentes/{incident_id}/analisis-ia",
        headers=_auth_headers(str(owner_token)),
        timeout=20,
    )

    assert response.status_code == 200, response.text

    payload = response.json()
    assert "data" in payload
    assert int(payload["data"]["incident_id"]) == incident_id
    assert payload["data"]["status"] in {"pending", "processing", "completed", "failed"}


def test_05_client_can_get_incident_ai_analysis_history(
    integration_base_url: str,
    integration_incident_context: dict[str, str | int | None],
) -> None:
    """Client owner token should be able to read AI analysis history for own incident."""
    incident_id = int(integration_incident_context["incident_id"])
    owner_token = integration_incident_context["owner_token"]

    if not owner_token:
        pytest.skip(
            "INTEGRATION_INCIDENT_OWNER_TOKEN is required to validate /analisis-ia/historial access"
        )

    response = requests.get(
        f"{integration_base_url}/api/v1/incidentes/{incident_id}/analisis-ia/historial",
        headers=_auth_headers(str(owner_token)),
        timeout=20,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "data" in payload
    assert isinstance(payload["data"], list)


def test_06_client_cannot_trigger_incident_ai_processing(
    integration_base_url: str,
    integration_incident_context: dict[str, str | int | None],
) -> None:
    """Client owner token must not access admin-only manual AI processing action."""
    incident_id = int(integration_incident_context["incident_id"])
    owner_token = integration_incident_context["owner_token"]

    if not owner_token:
        pytest.skip(
            "INTEGRATION_INCIDENT_OWNER_TOKEN is required to validate /procesar-ia denial"
        )

    response = requests.post(
        f"{integration_base_url}/api/v1/incidentes/{incident_id}/procesar-ia",
        headers=_auth_headers(str(owner_token)),
        timeout=20,
    )

    assert response.status_code == 403, response.text
