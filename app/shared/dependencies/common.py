"""
Common dependencies for pagination, filtering, etc.
"""
from typing import Annotated

from fastapi import Query

from ...core.constants import Pagination


def get_pagination_params(
    page: Annotated[int, Query(ge=1, description="Número de página")] = Pagination.DEFAULT_PAGE,
    size: Annotated[int, Query(ge=1, le=Pagination.MAX_SIZE, description="Elementos por página")] = Pagination.DEFAULT_SIZE,
) -> dict[str, int]:
    """
    Get pagination parameters with validation.
    
    Args:
        page: Page number (1-based)
        size: Items per page (max 100)
        
    Returns:
        Dictionary with page, size, skip, and limit
    """
    skip = (page - 1) * size
    
    return {
        "page": page,
        "size": size,
        "skip": skip,
        "limit": size,
    }


def get_search_params(
    q: Annotated[str | None, Query(description="Término de búsqueda")] = None,
    sort_by: Annotated[str | None, Query(description="Campo para ordenar")] = None,
    sort_order: Annotated[str, Query(pattern="^(asc|desc)$", description="Orden de clasificación")] = "asc",
) -> dict[str, str | None]:
    """
    Get search and sorting parameters.
    
    Args:
        q: Search query
        sort_by: Field to sort by
        sort_order: Sort order (asc or desc)
        
    Returns:
        Dictionary with search parameters
    """
    return {
        "query": q,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }