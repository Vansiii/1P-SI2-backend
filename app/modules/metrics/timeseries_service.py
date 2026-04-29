"""
Service for time series metrics calculations.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, extract, case
from sqlalchemy.orm import selectinload

from ...models.incidente import Incidente
from ...models.technician import Technician
from ...models.categoria import Categoria
from ...models.historial_servicio import HistorialServicio
from ...core.logging import get_logger

logger = get_logger(__name__)


class MetricsTimeSeriesService:
    """Service for calculating time series metrics."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_aware_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Normalize datetime to aware UTC."""
        if dt is None:
            return None
        from datetime import timezone
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=timezone.utc)

    async def get_response_time_series(
        self,
        days: int = 30,
        workshop_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get daily average response times.
        
        Args:
            days: Number of days to retrieve
            workshop_id: Optional workshop filter
            
        Returns:
            List of daily response time data points
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)

        # Build query
        query = select(
            func.date(Incidente.created_at).label('date'),
            func.avg(
                func.extract('epoch', Incidente.assigned_at - Incidente.created_at) / 60
            ).label('avg_response_minutes')
        ).where(
            and_(
                Incidente.created_at >= start_date,
                Incidente.assigned_at.isnot(None)
            )
        ).group_by(
            func.date(Incidente.created_at)
        ).order_by(
            func.date(Incidente.created_at)
        )

        if workshop_id:
            query = query.where(Incidente.taller_id == workshop_id)

        result = await self.session.execute(query)
        rows = result.all()

        # Fill in missing dates with null values
        data_dict = {row.date: row.avg_response_minutes for row in rows}
        
        series = []
        current_date = start_date.date()
        while current_date <= end_date.date():
            series.append({
                "date": current_date.isoformat(),
                "value": round(data_dict.get(current_date, 0) or 0, 2)
            })
            current_date += timedelta(days=1)

        return series

    async def get_resolution_time_series(
        self,
        days: int = 30,
        workshop_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get daily average resolution times.
        
        Args:
            days: Number of days to retrieve
            workshop_id: Optional workshop filter
            
        Returns:
            List of daily resolution time data points
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)

        # Build query
        query = select(
            func.date(Incidente.created_at).label('date'),
            func.avg(
                func.extract('epoch', Incidente.resolved_at - Incidente.created_at) / 60
            ).label('avg_resolution_minutes')
        ).where(
            and_(
                Incidente.created_at >= start_date,
                Incidente.resolved_at.isnot(None)
            )
        ).group_by(
            func.date(Incidente.created_at)
        ).order_by(
            func.date(Incidente.created_at)
        )

        if workshop_id:
            query = query.where(Incidente.taller_id == workshop_id)

        result = await self.session.execute(query)
        rows = result.all()

        # Fill in missing dates
        data_dict = {row.date: row.avg_resolution_minutes for row in rows}
        
        series = []
        current_date = start_date.date()
        while current_date <= end_date.date():
            series.append({
                "date": current_date.isoformat(),
                "value": round(data_dict.get(current_date, 0) or 0, 2)
            })
            current_date += timedelta(days=1)

        return series

    async def get_incidents_count_series(
        self,
        days: int = 30,
        workshop_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get daily incident counts.
        
        Args:
            days: Number of days to retrieve
            workshop_id: Optional workshop filter
            status: Optional status filter
            
        Returns:
            List of daily incident count data points
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)

        # Build query
        query = select(
            func.date(Incidente.created_at).label('date'),
            func.count(Incidente.id).label('count')
        ).where(
            Incidente.created_at >= start_date
        ).group_by(
            func.date(Incidente.created_at)
        ).order_by(
            func.date(Incidente.created_at)
        )

        if workshop_id:
            query = query.where(Incidente.taller_id == workshop_id)
        
        if status:
            query = query.where(Incidente.estado_actual == status)

        result = await self.session.execute(query)
        rows = result.all()

        # Fill in missing dates
        data_dict = {row.date: row.count for row in rows}
        
        series = []
        current_date = start_date.date()
        while current_date <= end_date.date():
            series.append({
                "date": current_date.isoformat(),
                "value": data_dict.get(current_date, 0)
            })
            current_date += timedelta(days=1)

        return series

    async def get_technician_performance(
        self,
        workshop_id: int,
        days: int = 30,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get technician performance metrics.
        
        Args:
            workshop_id: Workshop ID
            days: Number of days to analyze
            limit: Number of top technicians to return
            
        Returns:
            List of technician performance data
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)

        # Query for technician performance
        query = select(
            Technician.id,
            Technician.user_id,
            func.count(Incidente.id).label('total_incidents'),
            func.count(
                case((Incidente.estado_actual == 'resuelto', 1))
            ).label('resolved_incidents'),
            func.avg(
                func.extract('epoch', Incidente.resolved_at - Incidente.assigned_at) / 60
            ).label('avg_resolution_minutes'),
            func.avg(Incidente.calificacion).label('avg_rating')
        ).join(
            Incidente, Incidente.technician_id == Technician.id
        ).where(
            and_(
                Technician.workshop_id == workshop_id,
                Incidente.created_at >= start_date
            )
        ).group_by(
            Technician.id,
            Technician.user_id
        ).order_by(
            func.count(Incidente.id).desc()
        ).limit(limit)

        result = await self.session.execute(query)
        rows = result.all()

        # Get technician names
        technician_data = []
        for row in rows:
            # Get user info
            from ...models.user import User
            user = await self.session.scalar(
                select(User).where(User.id == row.user_id)
            )
            
            technician_name = f"{user.first_name} {user.last_name}" if user else f"Technician {row.id}"
            
            technician_data.append({
                "technician_id": row.id,
                "technician_name": technician_name,
                "total_incidents": row.total_incidents,
                "resolved_incidents": row.resolved_incidents,
                "avg_resolution_minutes": round(row.avg_resolution_minutes or 0, 2),
                "avg_rating": round(row.avg_rating or 0, 2),
                "resolution_rate": round((row.resolved_incidents / row.total_incidents * 100) if row.total_incidents > 0 else 0, 2)
            })

        return technician_data

    async def get_category_trends(
        self,
        days: int = 30,
        workshop_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get category trends over time.
        
        Args:
            days: Number of days to analyze
            workshop_id: Optional workshop filter
            
        Returns:
            List of category trend data
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)

        # Query for category trends
        query = select(
            Incidente.categoria_ia,
            func.date(Incidente.created_at).label('date'),
            func.count(Incidente.id).label('count')
        ).where(
            and_(
                Incidente.created_at >= start_date,
                Incidente.categoria_ia.isnot(None)
            )
        ).group_by(
            Incidente.categoria_ia,
            func.date(Incidente.created_at)
        ).order_by(
            Incidente.categoria_ia,
            func.date(Incidente.created_at)
        )

        if workshop_id:
            query = query.where(Incidente.taller_id == workshop_id)

        result = await self.session.execute(query)
        rows = result.all()

        # Organize data by category
        categories = {}
        for row in rows:
            if row.categoria_ia not in categories:
                categories[row.categoria_ia] = []
            categories[row.categoria_ia].append({
                "date": row.date.isoformat(),
                "count": row.count
            })

        # Convert to list format
        trends = []
        for cat_name, data_points in categories.items():
            trends.append({
                "category_name": cat_name or "General",
                "data": data_points
            })

        return trends

    async def get_hourly_distribution(
        self,
        days: int = 30,
        workshop_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get hourly distribution of incidents.
        
        Args:
            days: Number of days to analyze
            workshop_id: Optional workshop filter
            
        Returns:
            List of hourly distribution data
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)

        # Query for hourly distribution
        query = select(
            extract('hour', Incidente.created_at).label('hour'),
            func.count(Incidente.id).label('count')
        ).where(
            Incidente.created_at >= start_date
        ).group_by(
            extract('hour', Incidente.created_at)
        ).order_by(
            extract('hour', Incidente.created_at)
        )

        if workshop_id:
            query = query.where(Incidente.taller_id == workshop_id)

        result = await self.session.execute(query)
        rows = result.all()

        # Fill in all 24 hours
        data_dict = {int(row.hour): row.count for row in rows}
        
        distribution = []
        for hour in range(24):
            distribution.append({
                "hour": hour,
                "count": data_dict.get(hour, 0),
                "label": f"{hour:02d}:00"
            })

        return distribution

    async def get_weekly_comparison(
        self,
        weeks: int = 4,
        workshop_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get weekly comparison data.
        
        Args:
            weeks: Number of weeks to compare
            workshop_id: Optional workshop filter
            
        Returns:
            List of weekly comparison data
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(weeks=weeks)
        
        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)

        # Query for weekly data
        query = select(
            extract('week', Incidente.created_at).label('week'),
            extract('year', Incidente.created_at).label('year'),
            func.count(Incidente.id).label('total_incidents'),
            func.count(
                case((Incidente.estado_actual == 'resuelto', 1))
            ).label('resolved_incidents'),
            func.avg(
                func.extract('epoch', Incidente.resolved_at - Incidente.created_at) / 60
            ).label('avg_resolution_minutes')
        ).where(
            Incidente.created_at >= start_date
        ).group_by(
            extract('week', Incidente.created_at),
            extract('year', Incidente.created_at)
        ).order_by(
            extract('year', Incidente.created_at),
            extract('week', Incidente.created_at)
        )

        if workshop_id:
            query = query.where(Incidente.taller_id == workshop_id)

        result = await self.session.execute(query)
        rows = result.all()

        comparison = []
        for row in rows:
            comparison.append({
                "week": int(row.week),
                "year": int(row.year),
                "week_label": f"Semana {int(row.week)}, {int(row.year)}",
                "total_incidents": row.total_incidents,
                "resolved_incidents": row.resolved_incidents,
                "avg_resolution_minutes": round(row.avg_resolution_minutes or 0, 2),
                "resolution_rate": round((row.resolved_incidents / row.total_incidents * 100) if row.total_incidents > 0 else 0, 2)
            })

        return comparison
