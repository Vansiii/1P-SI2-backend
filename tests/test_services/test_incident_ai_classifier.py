"""Unit tests for incident AI classifier helpers and schema validation."""

import pytest

from app.core import ValidationException
from app.modules.incidentes.ai_classifier import (
    GeminiIncidentClassifier,
    GeminiIncidentClassification,
    parse_gemini_response_json,
)
from app.modules.incidentes.ai_service import IncidentAIService


def test_parse_gemini_response_json_with_plain_json() -> None:
    raw_response = (
        '{"category":"bateria","priority":"alta","summary":"Batería descargada",'
        '"is_ambiguous":false,"confidence":0.93,"findings":[],"missing_data":[],'
        '"workshop_recommendation":"Realizar diagnóstico de carga"}'
    )

    parsed_response = parse_gemini_response_json(raw_response)

    assert parsed_response["category"] == "bateria"
    assert parsed_response["priority"] == "alta"


def test_parse_gemini_response_json_with_markdown_code_fence() -> None:
    raw_response = (
        "```json\n"
        '{"category":"llanta","priority":"media","summary":"Llantas con posible pinchazo",'
        '"is_ambiguous":false,"confidence":0.81,"findings":["ruido en rodadura"],'
        '"missing_data":[],"workshop_recommendation":"Revisar presión y válvula"}'
        "\n```"
    )

    parsed_response = parse_gemini_response_json(raw_response)

    assert parsed_response["category"] == "llanta"
    assert parsed_response["priority"] == "media"


def test_parse_gemini_response_json_raises_on_invalid_payload() -> None:
    with pytest.raises(ValidationException):
        parse_gemini_response_json("not-a-json-response")


def test_gemini_incident_classification_schema_validation() -> None:
    payload = {
        "category": "motor",
        "priority": "alta",
        "summary": "Motor se apagó en circulación y no vuelve a encender.",
        "is_ambiguous": False,
        "confidence": 0.88,
        "findings": ["apagado repentino", "sin encendido posterior"],
        "missing_data": ["temperatura exacta del motor"],
        "workshop_recommendation": "Verificar sistema eléctrico y combustible",
    }

    result = GeminiIncidentClassification.model_validate(payload)

    assert result.category == "motor"
    assert result.priority == "alta"
    assert result.confidence == 0.88


def test_incident_request_hash_is_deterministic() -> None:
    first_hash = IncidentAIService._build_request_hash(
        description="vehiculo no enciende",
        image_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
        audio_urls=["https://example.com/a.mp3"],
    )
    second_hash = IncidentAIService._build_request_hash(
        description="vehiculo no enciende",
        image_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
        audio_urls=["https://example.com/a.mp3"],
    )

    assert first_hash == second_hash


def test_gemini_model_candidates_include_fallbacks_without_duplicates() -> None:
    classifier = GeminiIncidentClassifier()
    classifier.settings.gemini_model = "gemini-2.0-flash"
    classifier.settings.gemini_fallback_models = " gemini-1.5-flash , gemini-2.0-flash,gemini-1.5-flash "

    candidates = classifier._build_model_candidates()

    assert candidates == ["gemini-2.0-flash", "gemini-1.5-flash"]


def test_gemini_endpoint_builder_uses_model_name() -> None:
    endpoint = GeminiIncidentClassifier._build_endpoint("gemini-1.5-flash")

    assert endpoint.endswith("/models/gemini-1.5-flash:generateContent")


def test_incident_ai_summary_builder_adds_context_sections() -> None:
    classification = GeminiIncidentClassification.model_validate(
        {
            "category": "motor",
            "priority": "alta",
            "summary": "El motor presenta apagado repentino luego de vibración intensa y olor a combustible.",
            "is_ambiguous": True,
            "confidence": 0.72,
            "findings": [
                "vibración previa al apagado",
                "olor marcado a combustible",
                "sin respuesta al encendido inmediato",
            ],
            "missing_data": ["lectura de códigos OBD", "estado de presión de combustible"],
            "workshop_recommendation": "Realizar diagnóstico inicial de inyección, bomba y chispa con protocolo de seguridad.",
        }
    )

    enriched_summary = IncidentAIService._build_incident_ai_summary(classification)

    assert "Hallazgos clave:" in enriched_summary
    assert "Recomendación de taller:" in enriched_summary
    assert "Información adicional recomendada" in enriched_summary
    assert "Confianza estimada del análisis:" in enriched_summary
    assert "Caso marcado como ambiguo" in enriched_summary
