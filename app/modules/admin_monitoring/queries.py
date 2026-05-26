"""
Admin Monitoring Queries

Optimized SQL queries for admin monitoring endpoints.
"""

from sqlalchemy import select, func, and_, or_, case, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

from app.models.incidente import Incidente
from app.models.workshop import Workshop
from app.models.technician import Technician
from app.models.incident_ai_analysis import IncidentAIAnalysis
from app.models.service_rating import ServiceRating  # CU06

logger = logging.getLogger(__name__)


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
                    Incidente.updated_at >= datetime.utcnow().date()
                ), 1), else_=0)).label('resuelto_hoy')
            )
        )
        
        incident_row = incident_counts.first()
        
        # Count workshops by availability
        # A workshop is "available" if it has at least one available technician
        # A workshop is "busy" if all technicians are busy
        # A workshop is "offline" if it has no technicians or all are offline
        
        workshop_counts = await db.execute(
            select(
                func.count(Workshop.id).label('total'),
                func.sum(case((
                    and_(
                        Workshop.is_active == True,
                        Workshop.is_verified == True
                    ), 1
                ), else_=0)).label('available'),
                func.sum(case((
                    Workshop.is_active == False, 1
                ), else_=0)).label('offline')
            )
        )
        
        workshop_row = workshop_counts.first()
        
        # Calculate busy workshops (workshops with all technicians busy)
        # This requires a subquery
        busy_workshops_query = await db.execute(
            select(func.count()).select_from(
                select(Workshop.id).join(
                    Technician, Workshop.id == Technician.workshop_id
                ).group_by(Workshop.id).having(
                    func.count(Technician.id) > 0
                ).having(
                    func.sum(case((Technician.is_available == True, 1), else_=0)) == 0
                ).subquery()
            )
        )
        
        busy_count = busy_workshops_query.scalar() or 0
        
        # Rating metrics (CU06)
        rating_metrics = await db.execute(
            select(
                func.count(ServiceRating.id).label('total_ratings'),
                func.avg(ServiceRating.rating).label('average_rating'),
                func.sum(case((
                    ServiceRating.created_at >= datetime.utcnow().date(), 1
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
            'available_workshops': (workshop_row.available or 0) - busy_count,
            'busy_workshops': busy_count,
            'offline_workshops': workshop_row.offline or 0,
            # Rating metrics (CU06)
            'total_ratings': rating_row.total_ratings or 0,
            'average_rating': round(float(rating_row.average_rating or 0), 2),
            'ratings_today': rating_row.ratings_today or 0,
            'updated_at': datetime.utcnow()
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
        # Get workshops with technician counts using subquery to avoid GROUP BY issues
        from sqlalchemy import literal_column
        
        # First, get technician counts per workshop
        tech_counts_subq = select(
            Technician.workshop_id,
            func.count(Technician.id).label('total_technicians'),
            func.sum(case((Technician.is_available == True, 1), else_=0)).label('available_technicians'),
            func.sum(case((Technician.is_available == False, 1), else_=0)).label('busy_technicians')
        ).group_by(Technician.workshop_id).subquery()
        
        # Then join with workshops
        query = select(
            Workshop,
            func.coalesce(tech_counts_subq.c.total_technicians, 0).label('total_technicians'),
            func.coalesce(tech_counts_subq.c.available_technicians, 0).label('available_technicians'),
            func.coalesce(tech_counts_subq.c.busy_technicians, 0).label('busy_technicians')
        ).outerjoin(
            tech_counts_subq, Workshop.id == tech_counts_subq.c.workshop_id
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        workshops_with_status = []
        by_status = {
            'available': 0,
            'busy': 0,
            'offline': 0,
            'out_of_service': 0
        }
        
        for row in rows:
            workshop = row.Workshop
            total_techs = row.total_technicians or 0
            available_techs = row.available_technicians or 0
            busy_techs = row.busy_technicians or 0
            
            # Determine availability status
            if not workshop.is_active:
                status = 'offline'
                by_status['offline'] += 1
            elif not workshop.is_verified:
                status = 'out_of_service'
                by_status['out_of_service'] += 1
            elif total_techs == 0:
                status = 'offline'
                by_status['offline'] += 1
            elif available_techs > 0:
                status = 'available'
                by_status['available'] += 1
            else:
                status = 'busy'
                by_status['busy'] += 1
            
            # Count active incidents for this workshop
            active_incidents_query = await db.execute(
                select(func.count(Incidente.id)).where(
                    and_(
                        Incidente.taller_id == workshop.id,
                        Incidente.estado_actual.in_([
                            'asignado', 'en_proceso', 'en_camino', 'en_sitio'
                        ])
                    )
                )
            )
            active_incidents = active_incidents_query.scalar() or 0
            
            workshops_with_status.append({
                'id': workshop.id,
                'workshop_name': workshop.workshop_name,
                'is_verified': workshop.is_verified,
                'address': workshop.address,
                'coverage_radius_km': workshop.coverage_radius_km,
                'total_technicians': total_techs,
                'available_technicians': available_techs,
                'busy_technicians': busy_techs,
                'active_incidents': active_incidents,
                'availability_status': status,
                'updated_at': datetime.utcnow()
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
        workshops_by_status_query = await db.execute(
            select(
                case(
                    (Workshop.is_active == True, 'Disponible'),
                    else_='Fuera de línea'
                ).label('name'),
                func.count(Workshop.id).label('value')
            ).group_by(
                Workshop.is_active
            )
        )
        workshops_by_status = [
            {'name': 'Disponible' if row.name else 'Fuera de línea', 'value': row.value}
            for row in workshops_by_status_query.all()
        ]
        
        # Incidents timeline (last 24 hours, grouped by hour)
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        
        # This is a simplified version - would need more complex query for real timeline
        incidents_timeline = []
        for i in range(24):
            hour_start = start_time + timedelta(hours=i)
            hour_end = hour_start + timedelta(hours=1)
            hour_label = hour_start.strftime('%H:00')
            
            # Count active and resolved incidents in this hour
            active_count_query = await db.execute(
                select(func.count(Incidente.id)).where(
                    and_(
                        Incidente.created_at >= hour_start,
                        Incidente.created_at < hour_end,
                        Incidente.estado_actual.in_([
                            'pendiente', 'asignado', 'en_proceso', 'en_camino', 'en_sitio'
                        ])
                    )
                )
            )
            active_count = active_count_query.scalar() or 0
            
            resolved_count_query = await db.execute(
                select(func.count(Incidente.id)).where(
                    and_(
                        Incidente.updated_at >= hour_start,
                        Incidente.updated_at < hour_end,
                        Incidente.estado_actual == 'resuelto'
                    )
                )
            )
            resolved_count = resolved_count_query.scalar() or 0
            
            incidents_timeline.append({
                'name': hour_label,
                'series': [
                    {'name': 'Activos', 'value': active_count},
                    {'name': 'Resueltos', 'value': resolved_count}
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
