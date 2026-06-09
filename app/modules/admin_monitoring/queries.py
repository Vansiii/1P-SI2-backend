"""
Admin Monitoring Queries

Optimized SQL queries for admin monitoring endpoints.
"""

from sqlalchemy import select, func, and_, or_, case, cast, Integer, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import logging

from app.models.incidente import Incidente
from app.models.workshop import Workshop
from app.models.technician import Technician
from app.models.incident_ai_analysis import IncidentAIAnalysis
from app.models.service_rating import ServiceRating  # CU06

logger = logging.getLogger(__name__)

ACTIVE_INCIDENT_STATUS_ALIASES = [
    'asignado', 'assigned',
    'aceptado', 'accepted',
    'en_proceso', 'in_progress', 'en proceso', 'en_progreso',
    'en_camino', 'on_way', 'en camino',
    'en_sitio', 'on_site', 'en sitio',
]


def _empty_workshop_status_counts() -> Dict[str, int]:
    return {
        'available': 0,
        'busy': 0,
        'offline': 0,
        'out_of_service': 0,
    }


def _derive_workshop_availability_status(
    workshop: Workshop,
    total_technicians: int,
    available_technicians: int,
) -> str:
    if not getattr(workshop, 'is_active', True):
        return 'offline'
    if getattr(workshop, 'is_available', True) is False:
        return 'offline'
    if getattr(workshop, 'is_verified', True) is False:
        return 'out_of_service'
    if total_technicians <= 0:
        return 'offline'
    if available_technicians > 0:
        return 'available'
    return 'busy'


# ============================================================================
# System Metrics Queries
# ============================================================================

async def get_system_metrics(db: AsyncSession) -> Dict:
    """
    Get system-wide metrics for admin dashboard.
    Optimized with a single query using conditional aggregation.
    """
    try:
        pending_aliases = ['pendiente', 'pending']
        assigned_aliases = ['asignado', 'assigned']
        in_progress_aliases = ['en_proceso', 'in_progress', 'en proceso', 'en_progreso', 'aceptado']
        on_way_aliases = ['en_camino', 'on_way', 'en camino']
        on_site_aliases = ['en_sitio', 'on_site', 'en sitio']
        resolved_aliases = ['resuelto', 'resolved', 'completado', 'completed']
        no_workshop_aliases = [
            'sin_taller_disponible',
            'sin_taller',
            'sin_taller_asignado',
            'sin taller disponible',
            'sin taller asignado',
            'no_workshop_available',
        ]
        # Normalize state in SQL to avoid case/spacing mismatches from legacy data.
        normalized_status = func.lower(func.trim(Incidente.estado_actual))

        # Count incidents by status using conditional aggregation
        incident_counts = await db.execute(
            select(
                func.sum(case((normalized_status.in_(pending_aliases), 1), else_=0)).label('pendiente'),
                func.sum(case((normalized_status.in_(assigned_aliases), 1), else_=0)).label('asignado'),
                func.sum(case((normalized_status.in_(in_progress_aliases), 1), else_=0)).label('en_proceso'),
                func.sum(case((normalized_status.in_(on_way_aliases), 1), else_=0)).label('en_camino'),
                func.sum(case((normalized_status.in_(on_site_aliases), 1), else_=0)).label('en_sitio'),
                func.sum(case((normalized_status.in_(no_workshop_aliases), 1), else_=0)).label('sin_taller'),
                func.sum(case((
                    or_(
                        normalized_status.in_(pending_aliases),
                        normalized_status.in_(assigned_aliases),
                        normalized_status.in_(in_progress_aliases),
                        normalized_status.in_(on_way_aliases),
                        normalized_status.in_(on_site_aliases),
                        normalized_status.in_(no_workshop_aliases),
                    ),
                    1
                ), else_=0)).label('total'),
                func.sum(case((and_(
                    normalized_status.in_(resolved_aliases),
                    Incidente.updated_at >= datetime.now(timezone.utc).date()
                ), 1), else_=0)).label('resuelto_hoy')
            )
        )
        
        incident_row = incident_counts.first()
        
        _, _, workshop_status_counts = await get_all_workshops_with_status(db)
        
        # Rating metrics (CU06)
        rating_metrics = await db.execute(
            select(
                func.count(ServiceRating.id).label('total_ratings'),
                func.avg(ServiceRating.rating).label('average_rating'),
                func.sum(case((
                    ServiceRating.created_at >= datetime.now(timezone.utc).date(), 1
                ), else_=0)).label('ratings_today')
            )
        )
        rating_row = rating_metrics.first()
        
        return {
            'active_incidents': incident_row.total or 0,
            'unassigned_incidents': incident_row.sin_taller or 0,
            'pending_incidents': incident_row.pendiente or 0,
            'assigned_incidents': incident_row.asignado or 0,
            'in_progress_incidents': (incident_row.en_proceso or 0) + (incident_row.en_camino or 0) + (incident_row.en_sitio or 0),
            'resolved_today': incident_row.resuelto_hoy or 0,
            'available_workshops': workshop_status_counts.get('available', 0),
            'busy_workshops': workshop_status_counts.get('busy', 0),
            'offline_workshops': workshop_status_counts.get('offline', 0) + workshop_status_counts.get('out_of_service', 0),
            # Rating metrics (CU06)
            'total_ratings': rating_row.total_ratings or 0,
            'average_rating': round(float(rating_row.average_rating or 0), 2),
            'ratings_today': rating_row.ratings_today or 0,
            'updated_at': datetime.now(timezone.utc)
        }
    
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        raise


# ============================================================================
# Incidents Queries
# ============================================================================

async def get_all_incidents_with_filters(
    db: AsyncSession,
    estado: Optional[str] = None,
    prioridad_ia: Optional[str] = None,
    categoria_ia: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[Incidente], int, Dict]:
    """
    Get all incidents with filters and pagination.
    Returns (incidents, total_count, by_status_dict)
    """
    try:
        # Base query with eager loading
        query = select(Incidente).options(
            selectinload(Incidente.client),
            selectinload(Incidente.vehiculo),
            selectinload(Incidente.workshop),
            selectinload(Incidente.technician)
        )
        
        # Apply filters
        filters = []
        
        if estado:
            filters.append(Incidente.estado_actual == estado)
        
        if prioridad_ia:
            # Join with IncidentAIAnalysis to filter by priority
            query = query.join(
                IncidentAIAnalysis,
                Incidente.id == IncidentAIAnalysis.incident_id,
                isouter=True
            )
            filters.append(IncidentAIAnalysis.priority == prioridad_ia)
        
        if categoria_ia:
            # Join with IncidentAIAnalysis to filter by category
            if not prioridad_ia:  # Avoid double join
                query = query.join(
                    IncidentAIAnalysis,
                    Incidente.id == IncidentAIAnalysis.incident_id,
                    isouter=True
                )
            filters.append(IncidentAIAnalysis.category == categoria_ia)
        
        if search:
            # Search by ID, client name, workshop name, or description
            search_filter = or_(
                cast(Incidente.id, Integer) == int(search) if search.isdigit() else False,
                Incidente.descripcion.ilike(f'%{search}%'),
                Incidente.direccion_referencia.ilike(f'%{search}%')
            )
            filters.append(search_filter)
        
        if filters:
            query = query.where(and_(*filters))
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply pagination
        query = query.limit(limit).offset(offset).order_by(Incidente.created_at.desc())
        
        # Execute query
        result = await db.execute(query)
        incidents = result.scalars().all()
        
        # Get incidents by status
        by_status_query = await db.execute(
            select(
                Incidente.estado_actual,
                func.count(Incidente.id).label('count')
            ).group_by(Incidente.estado_actual)
        )
        
        by_status = {row.estado_actual: row.count for row in by_status_query.all()}
        
        return incidents, total, by_status
    
    except Exception as e:
        logger.error(f"Error getting incidents with filters: {e}")
        raise


# ============================================================================
# Workshops Queries
# ============================================================================

async def get_all_workshops_with_status(db: AsyncSession) -> Tuple[List[Dict], int, Dict]:
    """
    Get all workshops with their availability status.
    Returns (workshops_with_status, total_count, by_status_dict)
    """
    try:
        tech_counts_subq = select(
            Technician.workshop_id,
            func.count(Technician.id).label('total_technicians'),
            func.sum(case((Technician.is_available == True, 1), else_=0)).label('available_technicians'),
            func.sum(case((Technician.is_available == False, 1), else_=0)).label('busy_technicians')
        ).group_by(Technician.workshop_id).subquery()

        normalized_incident_status = func.lower(func.trim(Incidente.estado_actual))
        active_incidents_subq = select(
            Incidente.taller_id.label('workshop_id'),
            func.count(Incidente.id).label('active_incidents')
        ).where(
            and_(
                Incidente.taller_id.isnot(None),
                normalized_incident_status.in_(ACTIVE_INCIDENT_STATUS_ALIASES)
            )
        ).group_by(Incidente.taller_id).subquery()

        query = select(
            Workshop,
            func.coalesce(tech_counts_subq.c.total_technicians, 0).label('total_technicians'),
            func.coalesce(tech_counts_subq.c.available_technicians, 0).label('available_technicians'),
            func.coalesce(tech_counts_subq.c.busy_technicians, 0).label('busy_technicians'),
            func.coalesce(active_incidents_subq.c.active_incidents, 0).label('active_incidents')
        ).outerjoin(
            tech_counts_subq, Workshop.id == tech_counts_subq.c.workshop_id
        ).outerjoin(
            active_incidents_subq, Workshop.id == active_incidents_subq.c.workshop_id
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        workshops_with_status = []
        by_status = _empty_workshop_status_counts()
        
        for row in rows:
            workshop = row.Workshop
            total_techs = row.total_technicians or 0
            available_techs = row.available_technicians or 0
            busy_techs = row.busy_technicians or 0
            
            active_incidents = row.active_incidents or 0
            status = _derive_workshop_availability_status(workshop, total_techs, available_techs)
            by_status[status] += 1
            
            workshops_with_status.append({
                'id': workshop.id,
                'workshop_name': workshop.workshop_name,
                'is_active': workshop.is_active,
                'is_available': workshop.is_available,
                'is_verified': workshop.is_verified,
                'address': workshop.address,
                'coverage_radius_km': workshop.coverage_radius_km,
                'total_technicians': total_techs,
                'available_technicians': available_techs,
                'busy_technicians': busy_techs,
                'active_incidents': active_incidents,
                'availability_status': status,
                'updated_at': datetime.now(timezone.utc)
            })
        
        return workshops_with_status, len(workshops_with_status), by_status
    
    except Exception as e:
        logger.error(f"Error getting workshops with status: {e}")
        raise


# ============================================================================
# Chart Data Queries
# ============================================================================

async def get_chart_data(db: AsyncSession) -> Dict:
    """
    Get data for all charts in admin dashboard.
    """
    try:
        # Incidents by status
        incidents_by_status_query = await db.execute(
            select(
                Incidente.estado_actual.label('name'),
                func.count(Incidente.id).label('value')
            ).where(
                Incidente.estado_actual.in_([
                    'pendiente', 'asignado', 'en_proceso', 'en_camino',
                    'en_sitio', 'resuelto', 'cancelado', 'sin_taller_disponible'
                ])
            ).group_by(Incidente.estado_actual)
        )
        incidents_by_status = [
            {'name': row.name, 'value': row.value}
            for row in incidents_by_status_query.all()
        ]
        
        # Incidents by category (from AI analysis)
        incidents_by_category_query = await db.execute(
            select(
                IncidentAIAnalysis.category.label('name'),
                func.count(IncidentAIAnalysis.id).label('value')
            ).where(
                IncidentAIAnalysis.category.isnot(None)
            ).group_by(IncidentAIAnalysis.category).limit(10)
        )
        incidents_by_category = [
            {'name': row.name or 'Sin categoría', 'value': row.value}
            for row in incidents_by_category_query.all()
        ]
        
        # Incidents by priority (from AI analysis)
        incidents_by_priority_query = await db.execute(
            select(
                IncidentAIAnalysis.priority.label('name'),
                func.count(IncidentAIAnalysis.id).label('value')
            ).where(
                IncidentAIAnalysis.priority.isnot(None)
            ).group_by(IncidentAIAnalysis.priority)
        )
        incidents_by_priority = [
            {'name': row.name or 'Sin prioridad', 'value': row.value}
            for row in incidents_by_priority_query.all()
        ]
        
        # Workshops by status (simplified - would need more complex query for real status)
        _, _, workshop_status_counts = await get_all_workshops_with_status(db)
        workshops_by_status = [
            {'name': status, 'value': workshop_status_counts.get(status, 0)}
            for status in ['available', 'busy', 'offline', 'out_of_service']
        ]
        
        # Incidents timeline (last 24 hours, grouped by hour) — single batched query
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=24)
        
        timeline_active_result = await db.execute(
            select(
                extract('hour', Incidente.created_at).label('hour'),
                func.count(Incidente.id).label('count'),
            )
            .where(
                and_(
                    Incidente.created_at >= start_time,
                    Incidente.estado_actual.in_([
                        'pendiente', 'asignado', 'en_proceso', 'en_camino', 'en_sitio'
                    ])
                )
            )
            .group_by(extract('hour', Incidente.created_at))
        )
        active_by_hour = {int(row.hour): row.count for row in timeline_active_result.all()}
        
        timeline_resolved_result = await db.execute(
            select(
                extract('hour', Incidente.updated_at).label('hour'),
                func.count(Incidente.id).label('count'),
            )
            .where(
                and_(
                    Incidente.updated_at >= start_time,
                    Incidente.estado_actual == 'resuelto'
                )
            )
            .group_by(extract('hour', Incidente.updated_at))
        )
        resolved_by_hour = {int(row.hour): row.count for row in timeline_resolved_result.all()}
        
        incidents_timeline = []
        for i in range(24):
            hour_dt = start_time + timedelta(hours=i)
            hour_label = hour_dt.strftime('%H:00')
            hour_val = hour_dt.hour
            
            incidents_timeline.append({
                'name': hour_label,
                'series': [
                    {'name': 'Activos', 'value': active_by_hour.get(hour_val, 0)},
                    {'name': 'Resueltos', 'value': resolved_by_hour.get(hour_val, 0)}
                ]
            })
        
        # Ratings distribution (CU06)
        ratings_distribution_query = await db.execute(
            select(
                ServiceRating.rating.label('name'),
                func.count(ServiceRating.id).label('value')
            ).group_by(ServiceRating.rating).order_by(ServiceRating.rating)
        )
        ratings_distribution = [
            {'name': f'{row.name} estrellas', 'value': row.value}
            for row in ratings_distribution_query.all()
        ]
        
        # Top rated workshops (CU06)
        top_rated_workshops_query = await db.execute(
            select(
                Workshop.workshop_name.label('name'),
                func.avg(ServiceRating.rating).label('value')
            ).join(
                ServiceRating, Workshop.id == ServiceRating.workshop_id
            ).group_by(
                Workshop.id, Workshop.workshop_name
            ).having(
                func.count(ServiceRating.id) >= 3  # Minimum 3 ratings
            ).order_by(
                func.avg(ServiceRating.rating).desc()
            ).limit(10)
        )
        top_rated_workshops = [
            {'name': row.name, 'value': round(float(row.value), 2)}
            for row in top_rated_workshops_query.all()
        ]
        
        return {
            'incidents_by_status': incidents_by_status,
            'incidents_by_category': incidents_by_category,
            'incidents_by_priority': incidents_by_priority,
            'workshops_by_status': workshops_by_status,
            'incidents_timeline': incidents_timeline,
            # Rating charts (CU06)
            'ratings_distribution': ratings_distribution,
            'top_rated_workshops': top_rated_workshops
        }
    
    except Exception as e:
        logger.error(f"Error getting chart data: {e}")
        raise
