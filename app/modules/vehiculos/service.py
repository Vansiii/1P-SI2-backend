"""
Service para gestión de vehículos.
"""
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger, ConflictException, NotFoundException
from ...models.vehiculo import Vehiculo
from .repository import VehiculoRepository
from .schemas import VehiculoCreateRequest, VehiculoUpdateRequest

logger = get_logger(__name__)


class VehiculoService:
    """Service para lógica de negocio de vehículos."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = VehiculoRepository(session)
    
    async def create_vehiculo(
        self,
        client_id: int,
        request: VehiculoCreateRequest
    ) -> Vehiculo:
        """Crear un nuevo vehículo para un cliente."""
        # Verificar si ya existe un vehículo con esa matrícula
        existing = await self.repository.find_by_matricula(request.matricula)
        if existing:
            raise ConflictException(
                f"Ya existe un vehículo registrado con la matrícula {request.matricula}"
            )
        
        # Crear el objeto Vehiculo directamente
        vehiculo = Vehiculo(
            client_id=client_id,
            matricula=request.matricula.upper(),
            marca=request.marca,
            modelo=request.modelo,
            anio=request.anio,
            color=request.color,
            imagen=request.imagen,
        )
        
        # Agregar a la sesión y hacer commit
        self.session.add(vehiculo)
        await self.session.commit()
        await self.session.refresh(vehiculo)
        
        logger.info(
            "Vehículo creado",
            vehiculo_id=vehiculo.id,
            client_id=client_id,
            matricula=vehiculo.matricula
        )
        
        return vehiculo
    
    async def get_vehiculo(self, vehiculo_id: int, client_id: int) -> Vehiculo:
        """Obtener un vehículo por ID."""
        vehiculo = await self.repository.find_by_id(vehiculo_id)
        
        if not vehiculo:
            raise NotFoundException(f"Vehículo con ID {vehiculo_id} no encontrado")
        
        # Verificar que el vehículo pertenece al cliente
        if vehiculo.client_id != client_id:
            raise NotFoundException(f"Vehículo con ID {vehiculo_id} no encontrado")
        
        return vehiculo
    
    async def get_client_vehiculos(
        self,
        client_id: int,
        active_only: bool = True
    ) -> List[Vehiculo]:
        """Obtener todos los vehículos de un cliente."""
        return await self.repository.find_by_client(client_id, active_only)
    
    async def get_all_vehiculos(self, active_only: bool = True) -> List[Vehiculo]:
        """Obtener todos los vehículos del sistema (solo admin)."""
        return await self.repository.find_all_vehicles(active_only)
    
    async def update_vehiculo(
        self,
        vehiculo_id: int,
        client_id: int,
        request: VehiculoUpdateRequest
    ) -> Vehiculo:
        """Actualizar un vehículo."""
        vehiculo = await self.get_vehiculo(vehiculo_id, client_id)
        
        # Actualizar campos si están presentes
        if request.marca is not None:
            vehiculo.marca = request.marca
        if request.modelo is not None:
            vehiculo.modelo = request.modelo
        if request.anio is not None:
            vehiculo.anio = request.anio
        if request.color is not None:
            vehiculo.color = request.color
        if request.imagen is not None:
            vehiculo.imagen = request.imagen
        if request.is_active is not None:
            vehiculo.is_active = request.is_active
        
        # Commit changes
        await self.session.commit()
        await self.session.refresh(vehiculo)
        
        logger.info(
            "Vehículo actualizado",
            vehiculo_id=vehiculo.id,
            client_id=client_id
        )
        
        return vehiculo
    
    async def delete_vehiculo(self, vehiculo_id: int, client_id: int) -> None:
        """Eliminar un vehículo (soft delete)."""
        vehiculo = await self.get_vehiculo(vehiculo_id, client_id)
        
        # Soft delete usando el método del repositorio
        await self.repository.soft_delete(vehiculo.id)
        
        logger.info(
            "Vehículo eliminado",
            vehiculo_id=vehiculo_id,
            client_id=client_id
        )
    
    async def get_vehiculo_historial(self, vehiculo_id: int, client_id: int) -> dict:
        """Obtener historial de incidentes del vehículo."""
        # Verificar que el vehículo pertenece al cliente
        vehiculo = await self.get_vehiculo(vehiculo_id, client_id)
        
        # Obtener incidentes del vehículo
        from sqlalchemy import select
        from ...models.incidente import Incidente
        
        result = await self.session.execute(
            select(Incidente)
            .where(Incidente.vehiculo_id == vehiculo_id)
            .order_by(Incidente.created_at.desc())
        )
        incidentes = result.scalars().all()
        
        # Formatear respuesta
        historial_items = []
        for incidente in incidentes:
            historial_items.append({
                "id": incidente.id,
                "tipo": "incidente",
                "fecha": incidente.created_at.isoformat(),
                "estado": incidente.estado_actual,
                "descripcion": incidente.descripcion,
                "categoria": incidente.categoria_ia,
                "prioridad": incidente.prioridad_ia,
                "direccion": incidente.direccion_referencia,
            })
        
        logger.info(
            "Historial de vehículo obtenido",
            vehiculo_id=vehiculo_id,
            client_id=client_id,
            total_items=len(historial_items)
        )
        
        return {
            "vehiculo_id": vehiculo_id,
            "vehiculo": {
                "id": vehiculo.id,
                "matricula": vehiculo.matricula,
                "marca": vehiculo.marca,
                "modelo": vehiculo.modelo,
                "anio": vehiculo.anio,
                "color": vehiculo.color,
                "imagen": vehiculo.imagen,
            },
            "total_incidentes": len(historial_items),
            "historial": historial_items,
        }
