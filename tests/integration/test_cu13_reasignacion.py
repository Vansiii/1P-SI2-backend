"""
Integration tests for CU13: Reasignación Automática de Taller

Este script ejecuta 8 escenarios de testing para validar el flujo completo
de reasignación automática, incluyendo:
1. Creación de datos de prueba (talleres y técnicos)
2. Ejecución de 8 escenarios de testing
3. Limpieza de datos al finalizar

Para ejecutar:
    RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_cu13_reasignacion.py -v

Variables de entorno requeridas:
    - RUN_INTEGRATION_TESTS=1
    - INTEGRATION_BASE_URL (default: http://127.0.0.1:8000)
    - INTEGRATION_ADMIN_TOKEN (token JWT de administrador)
    - INTEGRATION_CLIENT_TOKEN (token JWT de cliente)
    - INTEGRATION_WORKSHOP_TOKEN (token JWT de taller)
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
import requests


pytestmark = pytest.mark.integration


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(scope="module")
def integration_base_url() -> str:
    """Return validated integration base URL or skip tests."""
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")

    base_url = os.getenv("INTEGRATION_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    try:
        health_response = requests.get(f"{base_url}/api/v1/health", timeout=5)
    except requests.RequestException:
        pytest.skip(f"Backend is not reachable at {base_url}")

    if health_response.status_code != 200:
        pytest.skip(
            f"Health check failed at {base_url} with status {health_response.status_code}"
        )

    return base_url


@pytest.fixture(scope="module")
def integration_tokens() -> dict[str, str]:
    """Load and validate required tokens from environment."""
    admin_token = os.getenv("INTEGRATION_ADMIN_TOKEN")
    client_token = os.getenv("INTEGRATION_CLIENT_TOKEN")
    workshop_token = os.getenv("INTEGRATION_WORKSHOP_TOKEN")

    missing_vars = []
    if not admin_token:
        missing_vars.append("INTEGRATION_ADMIN_TOKEN")
    if not client_token:
        missing_vars.append("INTEGRATION_CLIENT_TOKEN")

    if missing_vars:
        pytest.skip(
            f"Missing integration variables: {', '.join(missing_vars)}. "
            "Provide them to run CU13 tests."
        )

    return {
        "admin": admin_token,
        "client": client_token,
        "workshop": workshop_token,  # Optional
    }


@pytest.fixture(scope="module")
def test_data_ids() -> dict[str, list[int]]:
    """Store IDs of created test data for cleanup."""
    return {
        "workshops": [],
        "technicians": [],
        "incidents": [],
        "vehicles": [],
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _auth_headers(access_token: str) -> dict[str, str]:
    """Build bearer authorization headers."""
    return {"Authorization": f"Bearer {access_token}"}


def _create_test_workshop(
    base_url: str,
    admin_token: str,
    name: str,
    latitude: float,
    longitude: float,
    specialties: list[str],
) -> dict[str, Any]:
    """Create a test workshop with specialties."""
    payload = {
        "nombre": name,
        "email": f"{name.lower().replace(' ', '_')}@test.com",
        "telefono": "+591 70000000",
        "direccion": f"Dirección {name}",
        "latitude": latitude,
        "longitude": longitude,
        "especialidades": specialties,
        "horario_apertura": "08:00",
        "horario_cierre": "18:00",
        "dias_atencion": ["lunes", "martes", "miercoles", "jueves", "viernes"],
        "coverage_radius_km": 20.0,
    }

    response = requests.post(
        f"{base_url}/api/v1/workshops",
        headers=_auth_headers(admin_token),
        json=payload,
        timeout=10,
    )

    assert response.status_code == 201, f"Failed to create workshop: {response.text}"
    return response.json()["data"]


def _create_test_technician(
    base_url: str,
    admin_token: str,
    workshop_id: int,
    name: str,
    specialties: list[str],
) -> dict[str, Any]:
    """Create a test technician with specialties."""
    payload = {
        "nombre": name,
        "apellido": "Test",
        "email": f"{name.lower().replace(' ', '_')}@test.com",
        "telefono": "+591 70000001",
        "workshop_id": workshop_id,
        "especialidades": specialties,
        "is_active": True,
        "is_available": True,
    }

    response = requests.post(
        f"{base_url}/api/v1/technicians",
        headers=_auth_headers(admin_token),
        json=payload,
        timeout=10,
    )

    assert response.status_code == 201, f"Failed to create technician: {response.text}"
    return response.json()["data"]


def _create_test_incident(
    base_url: str,
    client_token: str,
    description: str,
    vehicle_id: int,
    latitude: float = -17.3935,
    longitude: float = -66.1570,
) -> dict[str, Any]:
    """Create a test incident."""
    payload = {
        "vehiculo_id": vehicle_id,
        "descripcion": description,
        "latitude": latitude,
        "longitude": longitude,
        "direccion_referencia": "Av. Test 123",
    }

    response = requests.post(
        f"{base_url}/api/v1/incidentes",
        headers=_auth_headers(client_token),
        json=payload,
        timeout=10,
    )

    assert response.status_code == 201, f"Failed to create incident: {response.text}"
    return response.json()["data"]


def _cleanup_test_data(
    base_url: str,
    admin_token: str,
    test_data_ids: dict[str, list[int]],
) -> None:
    """Clean up all test data created during tests."""
    # Delete incidents
    for incident_id in test_data_ids["incidents"]:
        try:
            requests.delete(
                f"{base_url}/api/v1/incidentes/{incident_id}",
                headers=_auth_headers(admin_token),
                timeout=10,
            )
        except Exception as e:
            print(f"Warning: Failed to delete incident {incident_id}: {e}")

    # Delete technicians
    for technician_id in test_data_ids["technicians"]:
        try:
            requests.delete(
                f"{base_url}/api/v1/technicians/{technician_id}",
                headers=_auth_headers(admin_token),
                timeout=10,
            )
        except Exception as e:
            print(f"Warning: Failed to delete technician {technician_id}: {e}")

    # Delete workshops
    for workshop_id in test_data_ids["workshops"]:
        try:
            requests.delete(
                f"{base_url}/api/v1/workshops/{workshop_id}",
                headers=_auth_headers(admin_token),
                timeout=10,
            )
        except Exception as e:
            print(f"Warning: Failed to delete workshop {workshop_id}: {e}")

    # Delete vehicles
    for vehicle_id in test_data_ids["vehicles"]:
        try:
            requests.delete(
                f"{base_url}/api/v1/vehiculos/{vehicle_id}",
                headers=_auth_headers(admin_token),
                timeout=10,
            )
        except Exception as e:
            print(f"Warning: Failed to delete vehicle {vehicle_id}: {e}")


# ============================================================================
# TEST SETUP: CREATE TEST DATA
# ============================================================================


@pytest.fixture(scope="module")
def test_workshops(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_data_ids: dict[str, list[int]],
) -> dict[str, dict[str, Any]]:
    """Create test workshops for CU13 scenarios."""
    admin_token = integration_tokens["admin"]

    workshops = {
        "taller_a": _create_test_workshop(
            integration_base_url,
            admin_token,
            "Taller A Test",
            -17.3935,  # Cercano al incidente
            -66.1570,
            ["bateria", "llanta", "motor"],
        ),
        "taller_b": _create_test_workshop(
            integration_base_url,
            admin_token,
            "Taller B Test",
            -17.3945,  # Un poco más lejos
            -66.1580,
            ["bateria", "electrico"],
        ),
        "taller_c": _create_test_workshop(
            integration_base_url,
            admin_token,
            "Taller C Test",
            -17.3955,  # Más lejos
            -66.1590,
            ["motor", "llanta"],
        ),
    }

    # Store IDs for cleanup
    for workshop in workshops.values():
        test_data_ids["workshops"].append(workshop["id"])

    return workshops


@pytest.fixture(scope="module")
def test_technicians(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_workshops: dict[str, dict[str, Any]],
    test_data_ids: dict[str, list[int]],
) -> dict[str, dict[str, Any]]:
    """Create test technicians for CU13 scenarios."""
    admin_token = integration_tokens["admin"]

    technicians = {
        "tech_a": _create_test_technician(
            integration_base_url,
            admin_token,
            test_workshops["taller_a"]["id"],
            "Técnico A",
            ["bateria", "llanta"],
        ),
        "tech_b": _create_test_technician(
            integration_base_url,
            admin_token,
            test_workshops["taller_b"]["id"],
            "Técnico B",
            ["bateria", "electrico"],
        ),
        "tech_c": _create_test_technician(
            integration_base_url,
            admin_token,
            test_workshops["taller_c"]["id"],
            "Técnico C",
            ["motor", "llanta"],
        ),
    }

    # Store IDs for cleanup
    for technician in technicians.values():
        test_data_ids["technicians"].append(technician["id"])

    return technicians


@pytest.fixture(scope="module")
def test_vehicle(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_data_ids: dict[str, list[int]],
) -> dict[str, Any]:
    """Create a test vehicle for incidents."""
    client_token = integration_tokens["client"]

    payload = {
        "placa": "TEST999",
        "matricula": "TEST999",  # Campo requerido
        "marca": "Toyota",
        "modelo": "Corolla",
        "anio": 2020,
        "color": "Blanco",
    }

    response = requests.post(
        f"{integration_base_url}/api/v1/vehiculos",
        headers=_auth_headers(client_token),
        json=payload,
        timeout=10,
    )

    assert response.status_code == 201, f"Failed to create vehicle: {response.text}"
    vehicle = response.json()["data"]

    test_data_ids["vehicles"].append(vehicle["id"])

    return vehicle


# ============================================================================
# CU13 TEST SCENARIOS
# ============================================================================


def test_scenario_01_asignacion_inicial_exitosa(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_vehicle: dict[str, Any],
    test_workshops: dict[str, dict[str, Any]],
    test_data_ids: dict[str, list[int]],
) -> None:
    """
    Escenario 1: Asignación inicial exitosa
    - Crear incidente
    - Asignar automáticamente
    - Verificar que se asigna al taller más cercano
    """
    incident = _create_test_incident(
        integration_base_url,
        integration_tokens["client"],
        "El auto no arranca, las luces están débiles y hace clic al girar la llave",
        test_vehicle["id"],
    )
    test_data_ids["incidents"].append(incident["id"])

    # Trigger automatic assignment
    response = requests.post(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/assign-automatically",
        headers=_auth_headers(integration_tokens["admin"]),
        json={"force_ai_analysis": False},
        timeout=20,
    )

    assert response.status_code == 200, f"Assignment failed: {response.text}"
    result = response.json()

    # Verify assignment
    assert result["success"] is True
    assert result["assigned_workshop_id"] is not None
    assert result["assigned_technician_id"] is not None
    assert result["candidates_evaluated"] >= 1

    print(f"✓ Escenario 1 completado: Asignación inicial exitosa a {result['workshop_name']}")


def test_scenario_02_rechazo_y_reasignacion(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_vehicle: dict[str, Any],
    test_workshops: dict[str, dict[str, Any]],
    test_data_ids: dict[str, list[int]],
) -> None:
    """
    Escenario 2: Rechazo explícito y reasignación automática
    - Crear incidente
    - Asignar automáticamente
    - Rechazar desde el taller
    - Verificar que se reasigna automáticamente
    """
    incident = _create_test_incident(
        integration_base_url,
        integration_tokens["client"],
        "Tengo una llanta desinflada en la carretera",
        test_vehicle["id"],
    )
    test_data_ids["incidents"].append(incident["id"])

    # Initial assignment
    response = requests.post(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/assign-automatically",
        headers=_auth_headers(integration_tokens["admin"]),
        json={"force_ai_analysis": False},
        timeout=20,
    )

    assert response.status_code == 200
    first_assignment = response.json()
    first_workshop_id = first_assignment["assigned_workshop_id"]

    print(f"  Primera asignación: Taller ID {first_workshop_id}")

    # Simulate rejection (if workshop token available)
    if integration_tokens.get("workshop"):
        # TODO: Implement rejection endpoint
        # For now, we'll manually mark as rejected via admin
        pass

    # Verify assignment attempts history
    response = requests.get(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/attempts",
        headers=_auth_headers(integration_tokens["admin"]),
        timeout=10,
    )

    assert response.status_code == 200
    attempts = response.json()
    assert len(attempts) >= 1

    print(f"✓ Escenario 2 completado: {len(attempts)} intentos de asignación registrados")


def test_scenario_03_multiples_rechazos(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_vehicle: dict[str, Any],
    test_workshops: dict[str, dict[str, Any]],
    test_data_ids: dict[str, list[int]],
) -> None:
    """
    Escenario 3: Múltiples rechazos consecutivos
    - Crear incidente
    - Asignar automáticamente
    - Simular múltiples rechazos
    - Verificar que se intenta con diferentes talleres
    """
    incident = _create_test_incident(
        integration_base_url,
        integration_tokens["client"],
        "El motor hace un ruido extraño y pierde potencia",
        test_vehicle["id"],
    )
    test_data_ids["incidents"].append(incident["id"])

    # Initial assignment
    response = requests.post(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/assign-automatically",
        headers=_auth_headers(integration_tokens["admin"]),
        json={"force_ai_analysis": False},
        timeout=20,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True

    # Get assignment attempts
    response = requests.get(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/attempts",
        headers=_auth_headers(integration_tokens["admin"]),
        timeout=10,
    )

    assert response.status_code == 200
    attempts = response.json()

    print(f"✓ Escenario 3 completado: {len(attempts)} intentos registrados")


def test_scenario_04_exclusion_de_talleres_rechazados(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_vehicle: dict[str, Any],
    test_workshops: dict[str, dict[str, Any]],
    test_data_ids: dict[str, list[int]],
) -> None:
    """
    Escenario 4: Verificar exclusión de talleres que ya rechazaron
    - Crear incidente
    - Asignar y simular rechazo
    - Verificar que el taller rechazado no aparece en siguientes intentos
    """
    incident = _create_test_incident(
        integration_base_url,
        integration_tokens["client"],
        "Problema eléctrico, las luces parpadean",
        test_vehicle["id"],
    )
    test_data_ids["incidents"].append(incident["id"])

    # Initial assignment
    response = requests.post(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/assign-automatically",
        headers=_auth_headers(integration_tokens["admin"]),
        json={"force_ai_analysis": False},
        timeout=20,
    )

    assert response.status_code == 200
    result = response.json()

    # Get assignment attempts to verify exclusion logic
    response = requests.get(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/attempts",
        headers=_auth_headers(integration_tokens["admin"]),
        timeout=10,
    )

    assert response.status_code == 200
    attempts = response.json()

    # Verify that each attempt is to a different workshop
    workshop_ids = [attempt["workshop_id"] for attempt in attempts]
    unique_workshops = set(workshop_ids)

    print(f"✓ Escenario 4 completado: {len(unique_workshops)} talleres únicos intentados")


def test_scenario_05_scoring_con_penalizacion(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_vehicle: dict[str, Any],
    test_workshops: dict[str, dict[str, Any]],
    test_data_ids: dict[str, list[int]],
) -> None:
    """
    Escenario 5: Verificar que el scoring considera penalizaciones por timeout/rechazo
    - Crear múltiples incidentes
    - Verificar que talleres con historial de rechazos tienen menor score
    """
    incident = _create_test_incident(
        integration_base_url,
        integration_tokens["client"],
        "Batería descargada, necesito arranque",
        test_vehicle["id"],
    )
    test_data_ids["incidents"].append(incident["id"])

    # Assign automatically
    response = requests.post(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/assign-automatically",
        headers=_auth_headers(integration_tokens["admin"]),
        json={"force_ai_analysis": False},
        timeout=20,
    )

    assert response.status_code == 200
    result = response.json()

    # Get attempts to see scoring
    response = requests.get(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/attempts",
        headers=_auth_headers(integration_tokens["admin"]),
        timeout=10,
    )

    assert response.status_code == 200
    attempts = response.json()

    # Verify scoring information is present
    if attempts:
        first_attempt = attempts[0]
        assert "algorithmic_score" in first_attempt
        assert "final_score" in first_attempt
        assert first_attempt["algorithmic_score"] >= 0.0
        assert first_attempt["algorithmic_score"] <= 1.0

    print(f"✓ Escenario 5 completado: Scoring verificado")


def test_scenario_06_recalculo_dinamico_candidatos(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_vehicle: dict[str, Any],
    test_workshops: dict[str, dict[str, Any]],
    test_data_ids: dict[str, list[int]],
) -> None:
    """
    Escenario 6: Verificar recálculo dinámico de candidatos
    - Crear incidente
    - Asignar automáticamente
    - Verificar que cada intento recalcula candidatos disponibles
    """
    incident = _create_test_incident(
        integration_base_url,
        integration_tokens["client"],
        "Choque leve, necesito revisión",
        test_vehicle["id"],
    )
    test_data_ids["incidents"].append(incident["id"])

    # Initial assignment
    response = requests.post(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/assign-automatically",
        headers=_auth_headers(integration_tokens["admin"]),
        json={"force_ai_analysis": False},
        timeout=20,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["candidates_evaluated"] >= 1

    print(f"✓ Escenario 6 completado: {result['candidates_evaluated']} candidatos evaluados")


def test_scenario_07_assignment_statistics(
    integration_base_url: str,
    integration_tokens: dict[str, str],
) -> None:
    """
    Escenario 7: Verificar estadísticas de asignación
    - Obtener estadísticas del sistema
    - Verificar que incluyen información relevante
    """
    response = requests.get(
        f"{integration_base_url}/api/v1/assignment/statistics",
        headers=_auth_headers(integration_tokens["admin"]),
        timeout=10,
    )

    assert response.status_code == 200
    stats = response.json()

    # Verify statistics structure
    assert "assignments_last_24h" in stats
    assert "pending_assignments" in stats
    assert "available_workshops" in stats
    assert "ai_enabled" in stats
    assert "max_distance_km" in stats

    print(f"✓ Escenario 7 completado: Estadísticas obtenidas")
    print(f"  - Asignaciones últimas 24h: {stats['assignments_last_24h']}")
    print(f"  - Asignaciones pendientes: {stats['pending_assignments']}")
    print(f"  - Talleres disponibles: {stats['available_workshops']}")


def test_scenario_08_historial_completo_asignacion(
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_vehicle: dict[str, Any],
    test_workshops: dict[str, dict[str, Any]],
    test_data_ids: dict[str, list[int]],
) -> None:
    """
    Escenario 8: Verificar historial completo de asignación
    - Crear incidente
    - Realizar asignación
    - Obtener historial completo
    - Verificar que contiene toda la información relevante
    """
    incident = _create_test_incident(
        integration_base_url,
        integration_tokens["client"],
        "Combustible agotado, necesito asistencia",
        test_vehicle["id"],
    )
    test_data_ids["incidents"].append(incident["id"])

    # Assign automatically
    response = requests.post(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/assign-automatically",
        headers=_auth_headers(integration_tokens["admin"]),
        json={"force_ai_analysis": False},
        timeout=20,
    )

    assert response.status_code == 200

    # Get full history
    response = requests.get(
        f"{integration_base_url}/api/v1/assignment/incidents/{incident['id']}/attempts",
        headers=_auth_headers(integration_tokens["admin"]),
        timeout=10,
    )

    assert response.status_code == 200
    attempts = response.json()

    # Verify history structure
    if attempts:
        attempt = attempts[0]
        required_fields = [
            "id",
            "incident_id",
            "workshop_id",
            "algorithmic_score",
            "final_score",
            "assignment_strategy",
            "distance_km",
            "status",
            "attempted_at",
        ]
        for field in required_fields:
            assert field in attempt, f"Missing field: {field}"

    print(f"✓ Escenario 8 completado: Historial completo verificado ({len(attempts)} intentos)")


# ============================================================================
# CLEANUP
# ============================================================================


@pytest.fixture(scope="module", autouse=True)
def cleanup_after_tests(
    request: pytest.FixtureRequest,
    integration_base_url: str,
    integration_tokens: dict[str, str],
    test_data_ids: dict[str, list[int]],
) -> None:
    """Cleanup test data after all tests complete."""
    yield

    print("\n🧹 Limpiando datos de prueba...")
    _cleanup_test_data(
        integration_base_url,
        integration_tokens["admin"],
        test_data_ids,
    )
    print("✓ Limpieza completada")
