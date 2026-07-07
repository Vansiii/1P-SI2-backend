"""
Definición de "tools" (function-calling) que el MecánicoBot puede invocar.

El tool-calling nativo de Groq/Llama no es 100% confiable (puede devolver argumentos
mal formados), así que cada tool valida sus argumentos con Pydantic antes de ejecutar
nada contra la base de datos, y existe un fallback determinístico por palabras clave
(`detect_intent_keywords`) que dispara la misma tool aunque el modelo no la invoque.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...models.vehiculo import Vehiculo
from ...models.workshop import Workshop
from ...models.tenant import Tenant
from ...models.tenant_subscription import TenantSubscription
from ...models.service_rating import ServiceRating
from ...modules.marketplace.service import MarketplaceService
from ...modules.workshop_selection.service import WorkshopSelectionService

SEARCH_MARKETPLACE_TOOL = "buscar_repuestos_marketplace"
LIST_VEHICLES_TOOL = "obtener_vehiculos_cliente"
SEARCH_WORKSHOPS_TOOL = "buscar_talleres_cercanos"

DEFAULT_WORKSHOP_SEARCH_RADIUS_KM = 15.0

# Esquema estilo OpenAI function-calling (compatible con Groq).
TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": SEARCH_MARKETPLACE_TOOL,
            "description": (
                "Busca repuestos/productos reales disponibles en el marketplace de MecánicoYa. "
                "Úsala cuando el usuario pregunte dónde comprar una pieza, su precio, o pida una recomendación de repuesto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Término de búsqueda, ej: 'batería', 'pastillas de freno', 'filtro de aceite'.",
                    },
                    "vehicle_brand": {
                        "type": "string",
                        "description": "Marca del vehículo del usuario, si se conoce (ej: 'Toyota').",
                    },
                    "vehicle_model": {
                        "type": "string",
                        "description": "Modelo del vehículo del usuario, si se conoce (ej: 'Corolla').",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Precio máximo en bolivianos, si el usuario lo menciona.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": LIST_VEHICLES_TOOL,
            "description": "Obtiene la lista de vehículos registrados por el cliente actual, para usarlos como contexto.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": SEARCH_WORKSHOPS_TOOL,
            "description": (
                "Busca talleres mecánicos reales cercanos a la ubicación actual del usuario "
                "(la app envía la ubicación del dispositivo por separado, no la pidas como texto). "
                "Úsala cuando el usuario pregunte por talleres cercanos, dónde llevar su auto, "
                "o pida recomendaciones de talleres en su zona."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "radius_km": {
                        "type": "number",
                        "description": "Radio de búsqueda en kilómetros (por defecto 15 km).",
                    },
                },
            },
        },
    },
]


class BuscarRepuestosArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    vehicle_brand: str | None = Field(default=None, max_length=60)
    vehicle_model: str | None = Field(default=None, max_length=100)
    max_price: float | None = Field(default=None, gt=0)


class ObtenerVehiculosArgs(BaseModel):
    pass


class BuscarTalleresArgs(BaseModel):
    radius_km: float | None = Field(default=None, gt=0, le=100)


_SEARCH_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "para", "por",
    "mi", "mis", "tu", "tus", "su", "sus", "y", "en", "con", "que", "es", "al", "a",
    "necesito", "quiero", "busco", "auto", "carro", "vehiculo", "vehículo",
}


def _extract_search_term(query: str) -> str:
    """
    Reduce una consulta en lenguaje natural (que puede incluir marca/modelo/año,
    como arma el LLM al invocar la tool) a un término corto que sí pueda coincidir
    con un `ILIKE` de título/marca/número de parte en el marketplace.
    """
    words = [
        w for w in re.findall(r"[\wáéíóúñÁÉÍÓÚÑ]+", query.lower())
        if w not in _SEARCH_STOPWORDS and not w.isdigit() and len(w) > 2
    ]
    return words[0] if words else query.strip()


async def _execute_search_marketplace(
    session: AsyncSession, user_id: int, raw_arguments: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    args = BuscarRepuestosArgs.model_validate(raw_arguments)
    search_term = _extract_search_term(args.query)

    filters: dict[str, Any] = {"search": search_term, "size": 5, "sort_by": "rating"}
    if args.vehicle_brand:
        filters["vehicle_brand"] = args.vehicle_brand
    if args.vehicle_model:
        filters["vehicle_model"] = args.vehicle_model
    if args.max_price:
        filters["max_price"] = args.max_price

    service = MarketplaceService(session)
    items, total = await service.list_listings(filters)

    products = [
        {
            "listing_id": item["id"],
            "title": item["title"] or item["product_name"],
            "brand": item["product_brand"],
            "price": item["public_price"],
            "compare_at_price": item["compare_at_price"],
            "image_url": item["product_image_url"],
            "in_stock": item["current_stock"] > 0,
            # Nombre del taller dueño de la publicación, para que el bot siempre
            # pueda decir "en el taller X" en vez de solo listar el producto.
            "workshop_name": item.get("workshop_name"),
        }
        for item in items
    ]

    summary_for_llm = [
        {
            "listing_id": p["listing_id"],
            "title": p["title"],
            "brand": p["brand"],
            "price": p["price"],
            "in_stock": p["in_stock"],
            "workshop_name": p["workshop_name"],
        }
        for p in products
    ]

    return {
        "tool": SEARCH_MARKETPLACE_TOOL,
        "total_found": total,
        "results_for_model": summary_for_llm,
        "products": products,
    }


async def _execute_list_vehicles(
    session: AsyncSession, user_id: int, raw_arguments: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    ObtenerVehiculosArgs.model_validate(raw_arguments or {})

    # Client.id == User.id (herencia de tabla conjunta), así que el vehículo
    # pertenece al usuario actual cuando Vehiculo.client_id == user_id.
    stmt = select(Vehiculo).where(Vehiculo.client_id == user_id, Vehiculo.is_active == True)  # noqa: E712
    result = await session.execute(stmt)
    vehicles = result.scalars().all()

    vehicles_for_model = [
        {
            "id": v.id,
            "marca": v.marca,
            "modelo": v.modelo,
            "anio": v.anio,
            "matricula": v.matricula,
        }
        for v in vehicles
    ]

    return {"tool": LIST_VEHICLES_TOOL, "results_for_model": vehicles_for_model, "products": []}


async def _execute_search_workshops(
    session: AsyncSession, user_id: int, raw_arguments: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Busca talleres reales cerca de la ubicación del dispositivo. La ubicación NO es
    un argumento que el LLM invente: la app la manda por separado en `context`
    (latitude/longitude) junto con cada mensaje, igual que ya hace CU_incidentes.
    """
    args = BuscarTalleresArgs.model_validate(raw_arguments or {})
    context = context or {}
    latitude = context.get("latitude")
    longitude = context.get("longitude")

    if latitude is None or longitude is None:
        return {
            "tool": SEARCH_WORKSHOPS_TOOL,
            "location_missing": True,
            "results_for_model": [],
            "products": [],
        }

    radius_km = args.radius_km or DEFAULT_WORKSHOP_SEARCH_RADIUS_KM

    stmt = (
        select(Workshop)
        .where(Workshop.is_active == True, Workshop.is_verified == True)  # noqa: E712
        .options(
            selectinload(Workshop.tenant).selectinload(Tenant.subscriptions).selectinload(TenantSubscription.plan),
        )
    )
    result = await session.execute(stmt)
    workshops = list(result.scalars().all())

    nearby: list[dict[str, Any]] = []
    for workshop in workshops:
        if not WorkshopSelectionService._is_tenant_valid(workshop):
            continue

        distance_km = WorkshopSelectionService._haversine(
            float(latitude), float(longitude), float(workshop.latitude), float(workshop.longitude)
        )
        coverage_km = float(workshop.coverage_radius_km) if workshop.coverage_radius_km else radius_km
        if distance_km > radius_km or distance_km > coverage_km:
            continue

        rating_res = await session.execute(
            select(
                func.avg(ServiceRating.rating).label("avg_rating"),
                func.count(ServiceRating.id).label("count"),
            ).where(ServiceRating.workshop_id == workshop.id)
        )
        rating_row = rating_res.one()

        nearby.append(
            {
                "workshop_id": workshop.id,
                "workshop_name": workshop.workshop_name,
                "address": workshop.address,
                "phone": workshop.workshop_phone or workshop.phone,
                "distance_km": round(distance_km, 2),
                "rating": round(float(rating_row.avg_rating), 1) if rating_row.avg_rating else None,
                "rating_count": rating_row.count,
                "is_available": workshop.is_available,
            }
        )

    nearby.sort(key=lambda w: w["distance_km"])
    nearby = nearby[:5]

    return {
        "tool": SEARCH_WORKSHOPS_TOOL,
        "location_missing": False,
        "location_used": {"latitude": latitude, "longitude": longitude},
        "total_found": len(nearby),
        "results_for_model": nearby,
        "products": [],
    }


ToolExecutor = Callable[[AsyncSession, int, dict[str, Any], dict[str, Any] | None], Awaitable[dict[str, Any]]]

TOOL_REGISTRY: dict[str, ToolExecutor] = {
    SEARCH_MARKETPLACE_TOOL: _execute_search_marketplace,
    LIST_VEHICLES_TOOL: _execute_list_vehicles,
    SEARCH_WORKSHOPS_TOOL: _execute_search_workshops,
}


_MARKETPLACE_KEYWORDS = re.compile(
    r"\b(repuesto|repuestos|comprar|precio de|d[oó]nde consigo|marketplace|"
    r"bater[ií]a|pastilla|filtro|llanta|neum[aá]tico|amortiguador|aceite)\b",
    re.IGNORECASE,
)

_WORKSHOP_KEYWORDS = re.compile(
    r"\b(taller(es)?\s+(cerca|cercano|cercanos|cercana|cercanas)|"
    r"mec[aá]nico\s+cerca|d[oó]nde\s+hay\s+(un\s+)?taller|"
    r"taller\s+m[aá]s\s+cercano|recomiendas?\s+(un\s+)?taller|"
    r"talleres?\s+en\s+mi\s+zona)\b",
    re.IGNORECASE,
)


def detect_intent_keywords(user_message: str) -> str | None:
    """
    Fallback determinístico: si el modelo no invocó ninguna tool pero el mensaje
    del usuario sugiere claramente intención de compra/búsqueda de repuestos o de
    talleres cercanos, devuelve el nombre de la tool a ejecutar de todas formas.
    """
    message = user_message or ""
    if _WORKSHOP_KEYWORDS.search(message):
        return SEARCH_WORKSHOPS_TOOL
    if _MARKETPLACE_KEYWORDS.search(message):
        return SEARCH_MARKETPLACE_TOOL
    return None


def build_fallback_arguments(tool_name: str, user_message: str) -> dict[str, Any]:
    """
    Argumentos razonables para ejecutar una tool disparada por el fallback de keywords.

    Usa la palabra clave detectada (ej. "batería") como término de búsqueda en vez
    de la oración completa del usuario — una oración completa casi nunca coincide
    con el `ILIKE` de título/marca/número de parte en el marketplace.
    """
    if tool_name == SEARCH_MARKETPLACE_TOOL:
        match = _MARKETPLACE_KEYWORDS.search(user_message or "")
        query = match.group(0) if match else (user_message or "").strip()[:200]
        return {"query": query}
    return {}


def parse_tool_call_arguments(raw_arguments: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parsea defensivamente los argumentos que devuelve el proveedor (pueden venir mal formados)."""
    import json

    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    try:
        parsed = json.loads(raw_arguments)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
