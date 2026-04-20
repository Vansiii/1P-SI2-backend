"""
Real-time service for WebSocket integration with business logic.
"""
import json
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ...core.websocket import manager
from ...core.websocket_events import emit_to_incident_room, EventTypes
from ...core.logging import get_logger
from ...models.incidente import Incidente
from ...models.technician import Technician
from ...models.technician_location_history import TechnicianLocationHistory
from ...models.tracking_session import TrackingSession
from ...models.notification import Notification
from ..push_notifications.services import PushNotificationService, PushNotificationData

logger = get_logger(__name__)

# In-memory throttling for location updates (technician_id -> last_emission_time)
last_location_emit: Dict[int, datetime] = {}


class RealTimeService:
    """
    Service for real-time operations using WebSocket integration.
    Handles location updates, incident status changes, and notifications.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.push_service = PushNotificationService(session)

    async def update_technician_location(
        self,
        technician_id: int,
        latitude: float,
        longitude: float,
        accuracy: Optional[float] = None,
        speed: Optional[float] = None,
        heading: Optional[float] = None
    ) -> bool:
        """
        Update technician location and broadcast to relevant incidents and workshop.
        
        Args:
            technician_id: ID of the technician
            latitude: GPS latitude
            longitude: GPS longitude
            accuracy: GPS accuracy in meters
            speed: Speed in km/h
            heading: Direction in degrees
            
        Returns:
            True if update was successful
        """
        try:
            logger.info(f"📍 RealTimeService: Actualizando ubicación de técnico {technician_id}")
            
            # Get technician info first
            technician = await self.session.scalar(
                select(Technician).where(Technician.id == technician_id)
            )
            
            if not technician:
                logger.warning(f"❌ Technician {technician_id} not found")
                return False

            logger.info(f"✅ Técnico encontrado: {technician.first_name} {technician.last_name}, Workshop: {technician.workshop_id}")

            # Update technician's current location
            logger.info(f"📝 Actualizando ubicación en tabla technicians...")
            await self.session.execute(
                update(Technician)
                .where(Technician.id == technician_id)
                .values(
                    current_latitude=latitude,
                    current_longitude=longitude,
                    location_accuracy=accuracy,
                    location_updated_at=datetime.utcnow(),
                    is_online=True,
                    last_seen_at=datetime.utcnow()
                )
            )
            logger.info(f"✅ Ubicación actualizada en tabla technicians")

            # Save location history
            logger.info(f"📝 Guardando en historial de ubicaciones...")
            location_history = TechnicianLocationHistory(
                technician_id=technician_id,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy,
                speed=speed,
                heading=heading,
                recorded_at=datetime.utcnow()
            )
            self.session.add(location_history)
            logger.info(f"✅ Historial de ubicación agregado")

            # Find active incidents for this technician
            logger.info(f"🔍 Buscando incidentes activos...")
            active_incidents = await self.session.scalars(
                select(Incidente).where(
                    Incidente.tecnico_id == technician_id,
                    Incidente.estado_actual.in_(["asignado", "en_proceso"])
                )
            )
            active_incidents_list = list(active_incidents)
            logger.info(f"📊 Incidentes activos encontrados: {len(active_incidents_list)}")

            # Check throttling: only emit if last emission was more than 5 seconds ago
            current_time = datetime.utcnow()
            should_emit = True
            
            if technician_id in last_location_emit:
                time_since_last_emit = (current_time - last_location_emit[technician_id]).total_seconds()
                if time_since_last_emit < 5:
                    should_emit = False
                    logger.debug(f"⏱️ Throttling location update for technician {technician_id} (last emit: {time_since_last_emit:.1f}s ago)")
            
            # Broadcast location update to each incident (with throttling)
            if should_emit:
                for incident in active_incidents_list:
                    logger.info(f"📡 Enviando actualización a incidente {incident.id}")
                    
                    # Legacy WebSocket method (keep for backward compatibility)
                    await manager.send_location_update(
                        incident_id=incident.id,
                        technician_id=technician_id,
                        latitude=latitude,
                        longitude=longitude,
                        accuracy=accuracy,
                        speed=speed,
                        heading=heading
                    )
                    
                    # New standardized WebSocket event
                    await emit_to_incident_room(
                        incident_id=incident.id,
                        event_type=EventTypes.LOCATION_UPDATE,
                        data={
                            "technician_id": technician_id,
                            "incident_id": incident.id,
                            "latitude": latitude,
                            "longitude": longitude,
                            "accuracy": accuracy,
                            "speed": speed,
                            "heading": heading,
                            "timestamp": current_time.isoformat()
                        }
                    )
                
                # Update last emission time
                last_location_emit[technician_id] = current_time
                logger.info(f"✅ Location update emitted for technician {technician_id}")
            else:
                logger.debug(f"⏭️ Skipped location update emission for technician {technician_id} (throttled)")

            # Broadcast location update to workshop dashboard
            if technician.workshop_id:
                logger.info(f"📡 Enviando actualización a workshop {technician.workshop_id}")
                await manager.send_personal_message(technician.workshop_id, {
                    "type": "technician_location_update",
                    "data": {
                        "technician_id": technician_id,
                        "location": {
                            "latitude": latitude,
                            "longitude": longitude,
                            "accuracy": accuracy,
                            "speed": speed,
                            "heading": heading
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    }
                })
                logger.info(f"✅ Mensaje WebSocket enviado a workshop {technician.workshop_id}")

            logger.info(f"💾 Haciendo commit a la base de datos...")
            await self.session.commit()
            logger.info(f"✅ Location updated for technician {technician_id}")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Error updating technician location: {str(e)}", exc_info=True)
            return False

    async def update_incident_status(
        self,
        incident_id: int,
        new_status: str,
        changed_by: int,
        notes: Optional[str] = None
    ) -> bool:
        """
        Update incident status and notify all participants.
        
        Args:
            incident_id: ID of the incident
            new_status: New status value
            changed_by: ID of user making the change
            notes: Optional notes about the change
            
        Returns:
            True if update was successful
        """
        try:
            # Update incident status
            result = await self.session.execute(
                update(Incidente)
                .where(Incidente.id == incident_id)
                .values(
                    estado_actual=new_status,
                    updated_at=datetime.utcnow(),
                    assigned_at=datetime.utcnow() if new_status == "asignado" else None,
                    resolved_at=datetime.utcnow() if new_status == "resuelto" else None
                )
                .returning(Incidente)
            )
            
            incident = result.scalar_one_or_none()
            if not incident:
                logger.warning(f"Incident {incident_id} not found")
                return False

            # Create notification
            notification = Notification(
                user_id=incident.client_id,
                type="incident_status_change",
                title="Estado del incidente actualizado",
                message=f"Tu incidente cambió a estado: {new_status}",
                data_json=json.dumps({
                    "incident_id": incident_id,
                    "new_status": new_status,
                    "changed_by": changed_by,
                    "notes": notes
                }),
                created_at=datetime.utcnow()
            )
            self.session.add(notification)

            # Broadcast status change
            await manager.send_incident_status_change(
                incident_id=incident_id,
                new_status=new_status,
                changed_by=changed_by
            )

            # Send push notification to client
            if self.push_service.is_enabled():
                await self.push_service.send_incident_notification(
                    user_id=incident.client_id,
                    incident_id=incident_id,
                    notification_type="incident_status_change",
                    title="Estado del incidente actualizado",
                    body=f"Tu incidente cambió a estado: {new_status}",
                    additional_data={"notes": notes}
                )

            await self.session.commit()
            logger.info(f"Incident {incident_id} status updated to {new_status}")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating incident status: {str(e)}")
            return False

    async def assign_technician_to_incident(
        self,
        incident_id: int,
        technician_id: int,
        assigned_by: int
    ) -> bool:
        """
        Assign technician to incident and notify all parties.
        
        Args:
            incident_id: ID of the incident
            technician_id: ID of the technician
            assigned_by: ID of user making the assignment
            
        Returns:
            True if assignment was successful
        """
        try:
            from sqlalchemy.orm import selectinload
            
            # Get technician with workshop relationship loaded
            technician = await self.session.scalar(
                select(Technician)
                .options(selectinload(Technician.workshop))
                .where(Technician.id == technician_id)
            )
            
            if not technician:
                logger.warning(f"Technician {technician_id} not found")
                return False

            # Update incident with technician assignment
            await self.session.execute(
                update(Incidente)
                .where(Incidente.id == incident_id)
                .values(
                    tecnico_id=technician_id,
                    taller_id=technician.workshop_id,
                    estado_actual="en_proceso",  # Cambiar a en_proceso cuando se asigna técnico
                    assigned_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            )

            # Update technician status to on_duty and mark as not available
            # Note: Only updating Technician-specific fields to avoid joined table inheritance issues
            await self.session.execute(
                update(Technician)
                .where(Technician.id == technician_id)
                .values(
                    is_on_duty=True,
                    is_available=False  # Marcar como no disponible cuando está ocupado
                )
            )
            
            # Broadcast technician status change to workshop
            if technician.workshop_id:
                await manager.send_personal_message(technician.workshop_id, {
                    "type": "technician_status_update",
                    "data": {
                        "technician_id": technician_id,
                        "is_available": False,
                        "is_on_duty": True,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                })

            # Create tracking session
            tracking_session = TrackingSession(
                incidente_id=incident_id,
                technician_id=technician_id,
                started_at=datetime.utcnow(),
                is_active=True
            )
            self.session.add(tracking_session)

            # Get incident with client relationship loaded
            incident = await self.session.scalar(
                select(Incidente)
                .options(selectinload(Incidente.client))
                .where(Incidente.id == incident_id)
            )

            # Prepare workshop name
            workshop_name = technician.workshop.workshop_name if technician.workshop else "N/A"

            # Create notifications
            # Notify client
            client_notification = Notification(
                user_id=incident.client_id,
                type="technician_assigned",
                title="Técnico asignado",
                message=f"Se asignó el técnico {technician.first_name} {technician.last_name}",
                data_json=json.dumps({
                    "incident_id": incident_id,
                    "technician_id": technician_id,
                    "technician_name": f"{technician.first_name} {technician.last_name}",
                    "workshop_name": workshop_name
                }),
                created_at=datetime.utcnow()
            )
            self.session.add(client_notification)

            # Notify technician
            tech_notification = Notification(
                user_id=technician_id,
                type="incident_assigned",
                title="Nuevo incidente asignado",
                message=f"Se te asignó un nuevo incidente #{incident_id}",
                data_json=json.dumps({
                    "incident_id": incident_id,
                    "client_name": f"{incident.client.first_name} {incident.client.last_name}" if incident.client else "N/A",
                    "location": {
                        "latitude": float(incident.latitude),
                        "longitude": float(incident.longitude)
                    }
                }),
                created_at=datetime.utcnow()
            )
            self.session.add(tech_notification)

            # Broadcast assignment
            await manager.send_technician_assigned(
                incident_id=incident_id,
                technician_id=technician_id,
                technician_name=f"{technician.first_name} {technician.last_name}",
                workshop_name=workshop_name
            )

            # Send push notifications
            if self.push_service.is_enabled():
                # Notify client
                await self.push_service.send_incident_notification(
                    user_id=incident.client_id,
                    incident_id=incident_id,
                    notification_type="technician_assigned",
                    title="Técnico asignado",
                    body=f"Se asignó el técnico {technician.first_name} {technician.last_name}",
                    additional_data={
                        "technician_name": f"{technician.first_name} {technician.last_name}",
                        "workshop_name": workshop_name
                    }
                )
                
                # Notify technician
                await self.push_service.send_incident_notification(
                    user_id=technician_id,
                    incident_id=incident_id,
                    notification_type="incident_assigned",
                    title="Nuevo incidente asignado",
                    body=f"Se te asignó un nuevo incidente #{incident_id}",
                    additional_data={
                        "client_name": f"{incident.client.first_name} {incident.client.last_name}" if incident.client else "N/A",
                        "location": {
                            "latitude": float(incident.latitude),
                            "longitude": float(incident.longitude)
                        }
                    }
                )

            await self.session.commit()
            logger.info(f"Technician {technician_id} assigned to incident {incident_id} and marked as on_duty")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error assigning technician to incident: {str(e)}", exc_info=True)
            return False

    async def notify_technician_arrived(
        self,
        incident_id: int,
        technician_id: int
    ) -> bool:
        """
        Notify that technician has arrived at the incident location.
        
        Args:
            incident_id: ID of the incident
            technician_id: ID of the technician
            
        Returns:
            True if notification was successful
        """
        try:
            # Update incident status
            await self.session.execute(
                update(Incidente)
                .where(Incidente.id == incident_id)
                .values(
                    estado_actual="en_proceso",
                    updated_at=datetime.utcnow()
                )
            )

            # Update tracking session
            await self.session.execute(
                update(TrackingSession)
                .where(
                    TrackingSession.incident_id == incident_id,
                    TrackingSession.technician_id == technician_id,
                    TrackingSession.is_active == True
                )
                .values(
                    arrived_at=datetime.utcnow()
                )
            )

            # Get incident for notification
            incident = await self.session.scalar(
                select(Incidente).where(Incidente.id == incident_id)
            )

            # Create notification for client
            notification = Notification(
                user_id=incident.client_id,
                type="technician_arrived",
                title="El técnico ha llegado",
                message="El técnico ha llegado a tu ubicación y comenzará el servicio",
                data_json=json.dumps({
                    "incident_id": incident_id,
                    "technician_id": technician_id
                }),
                created_at=datetime.utcnow()
            )
            self.session.add(notification)

            # Broadcast arrival
            await manager.send_technician_arrived(
                incident_id=incident_id,
                technician_id=technician_id
            )

            # Send push notification to client
            if self.push_service.is_enabled():
                await self.push_service.send_incident_notification(
                    user_id=incident.client_id,
                    incident_id=incident_id,
                    notification_type="technician_arrived",
                    title="El técnico ha llegado",
                    body="El técnico ha llegado a tu ubicación y comenzará el servicio"
                )

            await self.session.commit()
            logger.info(f"Technician {technician_id} arrived at incident {incident_id}")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error notifying technician arrival: {str(e)}")
            return False

    async def send_chat_message(
        self,
        incident_id: int,
        sender_id: int,
        message: str
    ) -> bool:
        """
        Send chat message to incident participants.
        
        Args:
            incident_id: ID of the incident
            sender_id: ID of the message sender
            message: Message text
            
        Returns:
            True if message was sent successfully
        """
        try:
            # Get sender info
            sender = await self.session.scalar(
                select(Technician).where(Technician.id == sender_id)
            )
            
            if not sender:
                # Try client
                from ...models.client import Client
                sender = await self.session.scalar(
                    select(Client).where(Client.id == sender_id)
                )

            if not sender:
                logger.warning(f"Sender {sender_id} not found")
                return False

            sender_name = f"{sender.first_name} {sender.last_name}"

            # Broadcast message
            await manager.send_message_notification(
                incident_id=incident_id,
                sender_id=sender_id,
                sender_name=sender_name,
                message_text=message
            )

            logger.info(f"Chat message sent in incident {incident_id} by user {sender_id}")
            return True

        except Exception as e:
            logger.error(f"Error sending chat message: {str(e)}")
            return False

    async def get_connection_stats(self) -> dict:
        """
        Get WebSocket connection statistics.
        
        Returns:
            Dictionary with connection statistics
        """
        return {
            "connected_users": manager.get_connected_users_count(),
            "active_incident_rooms": len(manager.incident_rooms),
            "incident_rooms": {
                str(incident_id): len(users) 
                for incident_id, users in manager.incident_rooms.items()
            }
        }

    async def broadcast_technician_status_change(
        self,
        technician_id: int,
        is_available: bool = None,
        is_online: bool = None,
        last_seen_at: datetime = None
    ) -> bool:
        """
        Broadcast technician status changes to workshop dashboard.
        
        Args:
            technician_id: ID of the technician
            is_available: Availability status
            is_online: Online status
            last_seen_at: Last seen timestamp
            
        Returns:
            True if broadcast was successful
        """
        try:
            # Get technician info
            technician = await self.session.scalar(
                select(Technician).where(Technician.id == technician_id)
            )
            
            if not technician or not technician.workshop_id:
                return False

            # Prepare status update message
            status_data = {
                "technician_id": technician_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if is_available is not None:
                status_data["is_available"] = is_available
            if is_online is not None:
                status_data["is_online"] = is_online
            if last_seen_at is not None:
                status_data["last_seen_at"] = last_seen_at.isoformat()

            # Broadcast to workshop
            await manager.send_personal_message(technician.workshop_id, {
                "type": "technician_status_update",
                "data": status_data
            })

            logger.info(f"Status update broadcasted for technician {technician_id}")
            return True

        except Exception as e:
            logger.error(f"Error broadcasting technician status: {str(e)}")
            return False