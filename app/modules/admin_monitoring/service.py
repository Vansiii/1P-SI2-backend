"""
Admin Monitoring Service

Business logic for admin monitoring endpoints.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional, Tuple
import logging

from .queries import (
    get_system_metrics,
    get_all_incidents_with_filters,
    get_all_workshops_with_status,
    get_chart_data
)
from .schemas import (
    SystemMetrics,
    IncidentsResponse,
    IncidentsByStatus,
    WorkshopsResponse,
    WorkshopsByStatus,
    WorkshopWithStatus,
    ChartData
)

logger = logging.getLogger(__name__)


class AdminMonitoringService:
    """Service for admin monitoring operations"""
    
    @staticmethod
    async def get_system_summary(db: AsyncSession) -> SystemMetrics:
        """
        Get system-wide metrics summary.
        
        Args:
            db: Database session
            
        Returns:
            SystemMetrics with current system state
        """
        try:
            metrics_data = await get_system_metrics(db)
            return SystemMetrics(**metrics_data)
        except Exception as e:
            logger.error(f"Error getting system summary: {e}")
            raise
    
    @staticmethod
    async def get_incidents_with_filters(
        db: AsyncSession,
        estado: Optional[str] = None,
        prioridad_ia: Optional[str] = None,
        categoria_ia: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> IncidentsResponse:
        """
        Get all incidents with optional filters.
        
        Args:
            db: Database session
            estado: Filter by status
            prioridad_ia: Filter by AI priority
            categoria_ia: Filter by AI category
            search: Search by ID, client, workshop, or description
            limit: Maximum results to return
            offset: Offset for pagination
            
        Returns:
            IncidentsResponse with incidents, total count, and by_status breakdown
        """
        try:
            incidents, total, by_status_dict = await get_all_incidents_with_filters(
                db=db,
                estado=estado,
                prioridad_ia=prioridad_ia,
                categoria_ia=categoria_ia,
                search=search,
                limit=limit,
                offset=offset
            )
            
            # Convert incidents to dict format
            incidents_data = []
            for incident in incidents:
                incident_dict = {
                    'id': incident.id,
                    'descripcion': incident.descripcion,
                    'estado_actual': incident.estado_actual,
                    'latitude': incident.latitude,
                    'longitude': incident.longitude,
                    'direccion_referencia': incident.direccion_referencia,
                    'created_at': incident.created_at.isoformat() if incident.created_at else None,
                    'updated_at': incident.updated_at.isoformat() if incident.updated_at else None,
                    'client_id': incident.client_id,
                    'vehiculo_id': incident.vehiculo_id,
                    'taller_id': incident.taller_id,
                    'tecnico_id': incident.tecnico_id
                }
                
                # Add related data if loaded
                if incident.client:
                    incident_dict['cliente'] = {
                        'id': incident.client.id,
                        'nombre': incident.client.first_name,
                        'apellido': incident.client.last_name,
                        'email': incident.client.email,
                        'telefono': incident.client.phone
                    }
                
                if incident.vehiculo:
                    incident_dict['vehiculo'] = {
                        'id': incident.vehiculo.id,
                        'marca': incident.vehiculo.marca,
                        'modelo': incident.vehiculo.modelo,
                        'anio': incident.vehiculo.anio,
                        'matricula': incident.vehiculo.matricula,
                        'color': incident.vehiculo.color
                    }
                
                if incident.workshop:
                    incident_dict['taller'] = {
                        'id': incident.workshop.id,
                        'workshop_name': incident.workshop.workshop_name,
                        'address': incident.workshop.address,
                        'phone': incident.workshop.phone
                    }
                
                if incident.technician:
                    incident_dict['tecnico'] = {
                        'id': incident.technician.id,
                        'first_name': incident.technician.first_name,
                        'last_name': incident.technician.last_name,
                        'phone': incident.technician.phone
                    }
                
                incidents_data.append(incident_dict)
            
            # Convert by_status dict to IncidentsByStatus
            by_status = IncidentsByStatus(
                pendiente=by_status_dict.get('pendiente', 0),
                asignado=by_status_dict.get('asignado', 0),
                en_proceso=by_status_dict.get('en_proceso', 0),
                en_camino=by_status_dict.get('en_camino', 0),
                en_sitio=by_status_dict.get('en_sitio', 0),
                resuelto=by_status_dict.get('resuelto', 0),
                cancelado=by_status_dict.get('cancelado', 0),
                sin_taller_disponible=by_status_dict.get('sin_taller_disponible', 0)
            )
            
            return IncidentsResponse(
                incidents=incidents_data,
                total=total,
                by_status=by_status
            )
        except Exception as e:
            logger.error(f"Error getting incidents with filters: {e}")
            raise
    
    @staticmethod
    async def get_workshops_with_status(db: AsyncSession) -> WorkshopsResponse:
        """
        Get all workshops with their availability status.
        
        Args:
            db: Database session
            
        Returns:
            WorkshopsResponse with workshops, total count, and by_status breakdown
        """
        try:
            workshops_data, total, by_status_dict = await get_all_workshops_with_status(db)
            
            # Convert to WorkshopWithStatus objects
            workshops = [WorkshopWithStatus(**workshop) for workshop in workshops_data]
            
            # Convert by_status dict to WorkshopsByStatus
            by_status = WorkshopsByStatus(
                available=by_status_dict.get('available', 0),
                busy=by_status_dict.get('busy', 0),
                offline=by_status_dict.get('offline', 0),
                out_of_service=by_status_dict.get('out_of_service', 0)
            )
            
            return WorkshopsResponse(
                workshops=workshops,
                total=total,
                by_status=by_status
            )
        except Exception as e:
            logger.error(f"Error getting workshops with status: {e}")
            raise
    
    @staticmethod
    async def get_charts_data(db: AsyncSession) -> ChartData:
        """
        Get data for all charts in admin dashboard.
        
        Args:
            db: Database session
            
        Returns:
            ChartData with all chart datasets
        """
        try:
            chart_data = await get_chart_data(db)
            return ChartData(**chart_data)
        except Exception as e:
            logger.error(f"Error getting charts data: {e}")
            raise
