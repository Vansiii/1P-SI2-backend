"""Unit tests for the MecánicoBot tool-calling layer (CU36)."""

from unittest.mock import AsyncMock

import pytest

from app.core import ExternalServiceException
from app.modules.bot.ai_client import BotAIClient, ChatResult
from app.modules.bot.orchestrator import BotToolOrchestrator
from app.modules.bot import tools as bot_tools


def test_detect_intent_keywords_matches_marketplace_terms() -> None:
    assert bot_tools.detect_intent_keywords("necesito un repuesto para mi auto") == bot_tools.SEARCH_MARKETPLACE_TOOL
    assert bot_tools.detect_intent_keywords("¿dónde consigo pastillas de freno?") == bot_tools.SEARCH_MARKETPLACE_TOOL
    assert bot_tools.detect_intent_keywords("mi carro hace un ruido extraño") is None


def test_extract_search_term_strips_vehicle_details_and_stopwords() -> None:
    assert bot_tools._extract_search_term("filtro de aire para Toyota Corolla 2020") == "filtro"
    assert bot_tools._extract_search_term("necesito un aceite sintetico para mi auto") == "aceite"
    assert bot_tools._extract_search_term("bateria") == "bateria"


def test_parse_tool_call_arguments_handles_malformed_json() -> None:
    assert bot_tools.parse_tool_call_arguments('{"query": "batería"}') == {"query": "batería"}
    assert bot_tools.parse_tool_call_arguments("not-json-at-all") == {}
    assert bot_tools.parse_tool_call_arguments(None) == {}
    assert bot_tools.parse_tool_call_arguments({"query": "ya-es-dict"}) == {"query": "ya-es-dict"}


def test_buscar_repuestos_args_validation() -> None:
    args = bot_tools.BuscarRepuestosArgs.model_validate({"query": "batería", "max_price": 250})
    assert args.query == "batería"
    assert args.max_price == 250

    with pytest.raises(Exception):
        bot_tools.BuscarRepuestosArgs.model_validate({"max_price": 250})  # falta 'query'


def test_gemini_model_candidates_dedupe() -> None:
    client = BotAIClient()
    client.settings.gemini_model = "gemini-2.0-flash"
    client.settings.gemini_fallback_models = " gemini-1.5-flash , gemini-2.0-flash,gemini-1.5-flash "

    candidates = client._build_gemini_model_candidates()

    assert candidates == ["gemini-2.0-flash", "gemini-1.5-flash"]


@pytest.fixture
def fake_marketplace_result() -> dict:
    return {
        "tool": bot_tools.SEARCH_MARKETPLACE_TOOL,
        "total_found": 1,
        "results_for_model": [{"listing_id": 42, "title": "Batería Bosch 12V", "brand": "Bosch", "price": 450.0, "in_stock": True}],
        "products": [{"listing_id": 42, "title": "Batería Bosch 12V", "brand": "Bosch", "price": 450.0, "compare_at_price": None, "image_url": None, "in_stock": True}],
    }


@pytest.mark.asyncio
async def test_resolve_tools_executes_native_tool_call(fake_marketplace_result: dict) -> None:
    ai_client = BotAIClient()
    orchestrator = BotToolOrchestrator(session=object(), ai_client=ai_client)

    decision = ChatResult(
        content=None,
        tool_calls=[
            {
                "id": "call_1",
                "function": {"name": bot_tools.SEARCH_MARKETPLACE_TOOL, "arguments": '{"query": "bateria"}'},
            }
        ],
        model_used="llama-3.3-70b-versatile",
        tokens_used=120,
        latency_ms=300,
    )
    ai_client.chat_with_tools = AsyncMock(return_value=decision)  # type: ignore[method-assign]

    original_executor = bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL]
    bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL] = AsyncMock(return_value=fake_marketplace_result)
    try:
        resolution = await orchestrator.resolve_tools(
            user_id=1,
            base_messages=[{"role": "system", "content": "system"}, {"role": "user", "content": "necesito una bateria"}],
            history=[{"role": "user", "content": "necesito una bateria"}],
        )
    finally:
        bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL] = original_executor

    assert resolution.groq_available is True
    assert len(resolution.executed_tool_calls) == 1
    assert resolution.executed_tool_calls[0]["name"] == bot_tools.SEARCH_MARKETPLACE_TOOL
    assert resolution.products == fake_marketplace_result["products"]
    # El mensaje "tool" con el resultado debe haberse añadido a los mensajes aumentados.
    assert any(m.get("role") == "tool" for m in resolution.augmented_messages)


@pytest.mark.asyncio
async def test_resolve_tools_falls_back_to_keyword_detection(fake_marketplace_result: dict) -> None:
    ai_client = BotAIClient()
    orchestrator = BotToolOrchestrator(session=object(), ai_client=ai_client)

    # El modelo respondió texto plano, sin invocar ninguna tool.
    decision = ChatResult(
        content="Puede ser la batería.",
        tool_calls=None,
        model_used="llama-3.3-70b-versatile",
        tokens_used=80,
        latency_ms=200,
    )
    ai_client.chat_with_tools = AsyncMock(return_value=decision)  # type: ignore[method-assign]

    original_executor = bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL]
    bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL] = AsyncMock(return_value=fake_marketplace_result)
    try:
        resolution = await orchestrator.resolve_tools(
            user_id=1,
            base_messages=[{"role": "system", "content": "system"}, {"role": "user", "content": "necesito un repuesto de batería"}],
            history=[{"role": "user", "content": "necesito un repuesto de batería"}],
        )
    finally:
        bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL] = original_executor

    assert len(resolution.executed_tool_calls) == 1
    assert resolution.products == fake_marketplace_result["products"]
    assert any(m.get("role") == "system" and "Resultados reales disponibles" in m.get("content", "") for m in resolution.augmented_messages)


@pytest.mark.asyncio
async def test_resolve_tools_when_groq_completely_unavailable() -> None:
    ai_client = BotAIClient()
    orchestrator = BotToolOrchestrator(session=object(), ai_client=ai_client)

    ai_client.chat_with_tools = AsyncMock(  # type: ignore[method-assign]
        side_effect=ExternalServiceException(service_name="Groq", message="down")
    )

    resolution = await orchestrator.resolve_tools(
        user_id=1,
        base_messages=[{"role": "system", "content": "system"}, {"role": "user", "content": "hace un ruido raro el motor"}],
        history=[{"role": "user", "content": "hace un ruido raro el motor"}],
    )

    assert resolution.groq_available is False
    assert resolution.executed_tool_calls == []
    assert resolution.products == []


@pytest.mark.asyncio
async def test_resolve_tools_keeps_groq_available_on_tool_schema_error(fake_marketplace_result: dict) -> None:
    """Un HTTP 400 'tool_use_failed' (el modelo mandó argumentos mal formados) es un
    fallo puntual de esa llamada, no una caída real de Groq — no debe descartarse Groq
    para la síntesis final, y el fallback por keywords debe seguir corriendo."""
    ai_client = BotAIClient()
    orchestrator = BotToolOrchestrator(session=object(), ai_client=ai_client)

    ai_client.chat_with_tools = AsyncMock(  # type: ignore[method-assign]
        side_effect=ExternalServiceException(
            service_name="Groq", message="Groq API HTTP 400: tool_use_failed"
        )
    )

    original_executor = bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL]
    bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL] = AsyncMock(return_value=fake_marketplace_result)
    try:
        resolution = await orchestrator.resolve_tools(
            user_id=1,
            base_messages=[{"role": "system", "content": "system"}, {"role": "user", "content": "necesito una bateria"}],
            history=[{"role": "user", "content": "necesito una bateria"}],
        )
    finally:
        bot_tools.TOOL_REGISTRY[bot_tools.SEARCH_MARKETPLACE_TOOL] = original_executor

    assert resolution.groq_available is True
    assert len(resolution.executed_tool_calls) == 1
    assert resolution.products == fake_marketplace_result["products"]


def test_build_fallback_arguments_uses_matched_keyword_not_full_sentence() -> None:
    args = bot_tools.build_fallback_arguments(
        bot_tools.SEARCH_MARKETPLACE_TOOL,
        "Necesito una bateria nueva para mi auto, que me recomiendas",
    )
    assert args["query"].lower() == "bateria"


@pytest.mark.asyncio
async def test_run_uses_gemini_when_groq_unavailable() -> None:
    ai_client = BotAIClient()
    orchestrator = BotToolOrchestrator(session=object(), ai_client=ai_client)

    ai_client.chat_with_tools = AsyncMock(  # type: ignore[method-assign]
        side_effect=ExternalServiceException(service_name="Groq", message="down")
    )
    ai_client.call_gemini_text = AsyncMock(return_value="Respuesta de Gemini de emergencia.")  # type: ignore[method-assign]
    ai_client.settings.gemini_model = "gemini-2.0-flash"

    result = await orchestrator.run(
        user_id=1,
        system_prompt="system prompt",
        history=[{"role": "user", "content": "hace un ruido raro el motor"}],
    )

    assert result.content == "Respuesta de Gemini de emergencia."
    assert result.model_used == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_stream_yields_tokens_then_final_in_order() -> None:
    ai_client = BotAIClient()
    orchestrator = BotToolOrchestrator(session=object(), ai_client=ai_client)

    # Sin tool-calls: el modelo responde directo.
    ai_client.chat_with_tools = AsyncMock(  # type: ignore[method-assign]
        return_value=ChatResult(content=None, tool_calls=None, model_used="llama-3.3-70b-versatile", tokens_used=None, latency_ms=1)
    )

    async def fake_stream(messages):
        yield {"type": "token", "content": "Puede "}
        yield {"type": "token", "content": "ser la batería."}
        yield {"type": "final", "content": "Puede ser la batería.", "model_used": "llama-3.3-70b-versatile"}

    ai_client.stream_groq_chat = fake_stream  # type: ignore[method-assign]

    events = [event async for event in orchestrator.stream(
        user_id=1,
        system_prompt="system",
        history=[{"role": "user", "content": "no enciende el auto"}],
    )]

    types = [e["type"] for e in events]
    assert types == ["token", "token", "final"]
    final_event = events[-1]
    assert final_event["content"] == "Puede ser la batería."
    assert final_event["tool_calls"] is None
    assert final_event["products"] == []
