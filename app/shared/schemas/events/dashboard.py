"""Dashboard event schemas for real-time metrics updates."""

from typing import Any, Dict, Optional, Literal

from pydantic import Field

from .base import BaseEvent, EventPriority


class DashboardMetricsUpdatedEvent(BaseEvent):
    """Event emitted when dashboard metrics are updated."""
    
    event_type: Literal["dashboard.metrics_updated"] = "dashboard.metrics_updated"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    total_incidents: int = Field(..., description="Total number of incidents")
    active_incidents: int = Field(..., description="Number of active incidents")
    completed_today: int = Field(..., description="Incidents completed today")
    avg_response_time: Optional[float] = Field(None, description="Average response time in minutes")
    active_technicians: Optional[int] = Field(None, description="Number of active technicians")


class DashboardIncidentCountChangedEvent(BaseEvent):
    """Event emitted when incident count for a status changes."""
    
    event_type: Literal["dashboard.incident_count_changed"] = "dashboard.incident_count_changed"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    status: str = Field(..., description="Incident status")
    count: int = Field(..., description="Current count")
    delta: int = Field(..., description="Change from previous count")


class DashboardActiveTechniciansChangedEvent(BaseEvent):
    """Event emitted when active technician count changes."""
    
    event_type: Literal["dashboard.active_technicians_changed"] = "dashboard.active_technicians_changed"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    active_count: int = Field(..., description="Number of active technicians")
    available_count: int = Field(..., description="Number of available technicians")
    on_duty_count: int = Field(..., description="Number of technicians on duty")


class DashboardAlertTriggeredEvent(BaseEvent):
    """Event emitted when a dashboard alert is triggered."""
    
    event_type: Literal["dashboard.alert_triggered"] = "dashboard.alert_triggered"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    alert_type: str = Field(..., description="Type of alert")
    severity: str = Field(..., description="Severity level (info, warning, error, critical)")
    message: str = Field(..., description="Alert message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional alert data")
