"""
Configuración de Supabase Storage.

IMPORTANTE: Este módulo usa SUPABASE_SERVICE_ROLE_KEY que tiene permisos completos.
Solo debe usarse en el backend, NUNCA exponer al frontend.
"""
from supabase import create_client, Client
from .config import get_settings

settings = get_settings()


def get_supabase_client() -> Client:
    """
    Obtener cliente de Supabase con service role key.
    
    SEGURIDAD: Usa service_role_key que bypasea RLS (Row Level Security).
    Solo para operaciones del backend que requieren permisos elevados.
    """
    return create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key
    )


# Cliente singleton para reutilizar conexión
supabase_client = get_supabase_client()
