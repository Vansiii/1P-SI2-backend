"""
Base repository with generic CRUD operations.
"""
from typing import Any, Generic, TypeVar, Type, Sequence, Optional
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from ...core.exceptions import NotFoundException
from ...core.logging import get_logger

logger = get_logger(__name__)

ModelType = TypeVar("ModelType", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class BaseRepository(Generic[ModelType]):
    """Base repository with generic CRUD operations."""
    
    def __init__(self, session: AsyncSession, model: Type[ModelType]):
        """
        Initialize repository.
        
        Args:
            session: Database session
            model: SQLAlchemy model class
        """
        self.model = model
        self.session = session
    
    async def find_by_id(self, id: Any) -> ModelType | None:
        """
        Find entity by ID.
        
        Args:
            id: Entity ID
            
        Returns:
            Entity or None if not found
        """
        try:
            result = await self.session.get(self.model, id)
            if result:
                logger.debug("Found entity by ID", model=self.model.__name__, id=id)
            return result
        except Exception as exc:
            logger.error(
                "Error finding entity by ID",
                model=self.model.__name__,
                id=id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_by_id_or_raise(self, id: Any) -> ModelType:
        """
        Find entity by ID or raise NotFoundException.
        
        Args:
            id: Entity ID
            
        Returns:
            Entity
            
        Raises:
            NotFoundException: If entity not found
        """
        entity = await self.find_by_id(id)
        if entity is None:
            raise NotFoundException(
                resource_type=self.model.__name__,
                resource_id=id,
            )
        return entity
    
    async def find_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        **filters
    ) -> Sequence[ModelType]:
        """
        Find all entities with optional filtering and pagination.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            order_by: Field to order by
            **filters: Additional filters
            
        Returns:
            List of entities
        """
        try:
            query = select(self.model)
            
            # Apply filters
            for field, value in filters.items():
                if hasattr(self.model, field) and value is not None:
                    query = query.where(getattr(self.model, field) == value)
            
            # Apply ordering
            if order_by and hasattr(self.model, order_by):
                query = query.order_by(getattr(self.model, order_by))
            
            # Apply pagination
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            entities = result.scalars().all()
            
            logger.debug(
                "Found entities",
                model=self.model.__name__,
                count=len(entities),
                skip=skip,
                limit=limit,
                filters=filters,
            )
            
            return entities
            
        except Exception as exc:
            logger.error(
                "Error finding entities",
                model=self.model.__name__,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def count(self, **filters) -> int:
        """
        Count entities with optional filtering.
        
        Args:
            **filters: Filters to apply
            
        Returns:
            Number of entities
        """
        try:
            query = select(func.count(self.model.id))
            
            # Apply filters
            for field, value in filters.items():
                if hasattr(self.model, field) and value is not None:
                    query = query.where(getattr(self.model, field) == value)
            
            result = await self.session.execute(query)
            count = result.scalar() or 0
            
            logger.debug(
                "Counted entities",
                model=self.model.__name__,
                count=count,
                filters=filters,
            )
            
            return count
            
        except Exception as exc:
            logger.error(
                "Error counting entities",
                model=self.model.__name__,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        """
        Create new entity.
        
        Args:
            obj_in: Create schema with entity data
            
        Returns:
            Created entity
        """
        try:
            # Convert schema to dict
            if hasattr(obj_in, 'model_dump'):
                obj_data = obj_in.model_dump()
            elif hasattr(obj_in, 'dict'):
                obj_data = obj_in.dict()
            else:
                obj_data = dict(obj_in)
            
            # Create entity
            db_obj = self.model(**obj_data)
            self.session.add(db_obj)
            await self.session.commit()
            await self.session.refresh(db_obj)
            
            logger.info(
                "Created entity",
                model=self.model.__name__,
                id=getattr(db_obj, 'id', None),
            )
            
            return db_obj
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error creating entity",
                model=self.model.__name__,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def update(
        self,
        id: Any,
        obj_in: UpdateSchemaType | dict[str, Any]
    ) -> ModelType:
        """
        Update entity by ID.
        
        Args:
            id: Entity ID
            obj_in: Update schema or dict with new data
            
        Returns:
            Updated entity
            
        Raises:
            NotFoundException: If entity not found
        """
        try:
            # Find existing entity
            db_obj = await self.find_by_id_or_raise(id)
            
            # Convert schema to dict
            if hasattr(obj_in, 'model_dump'):
                update_data = obj_in.model_dump(exclude_unset=True)
            elif hasattr(obj_in, 'dict'):
                update_data = obj_in.dict(exclude_unset=True)
            else:
                update_data = dict(obj_in)
            
            # Update fields
            for field, value in update_data.items():
                if hasattr(db_obj, field):
                    setattr(db_obj, field, value)
            
            await self.session.commit()
            await self.session.refresh(db_obj)
            
            logger.info(
                "Updated entity",
                model=self.model.__name__,
                id=id,
                updated_fields=list(update_data.keys()),
            )
            
            return db_obj
            
        except Exception as exc:
            await self.session.rollback()
            if isinstance(exc, NotFoundException):
                raise
            logger.error(
                "Error updating entity",
                model=self.model.__name__,
                id=id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def delete(self, id: Any) -> bool:
        """
        Delete entity by ID.
        
        Args:
            id: Entity ID
            
        Returns:
            True if deleted, False if not found
        """
        try:
            # Check if entity exists
            db_obj = await self.find_by_id(id)
            if db_obj is None:
                return False
            
            await self.session.delete(db_obj)
            await self.session.commit()
            
            logger.info(
                "Deleted entity",
                model=self.model.__name__,
                id=id,
            )
            
            return True
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error deleting entity",
                model=self.model.__name__,
                id=id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def delete_by_filter(self, **filters) -> int:
        """
        Delete entities by filter.
        
        Args:
            **filters: Filters to apply
            
        Returns:
            Number of deleted entities
        """
        try:
            query = delete(self.model)
            
            # Apply filters
            for field, value in filters.items():
                if hasattr(self.model, field) and value is not None:
                    query = query.where(getattr(self.model, field) == value)
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            deleted_count = result.rowcount or 0
            
            logger.info(
                "Deleted entities by filter",
                model=self.model.__name__,
                count=deleted_count,
                filters=filters,
            )
            
            return deleted_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error deleting entities by filter",
                model=self.model.__name__,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def exists(self, id: Any) -> bool:
        """
        Check if entity exists by ID.
        
        Args:
            id: Entity ID
            
        Returns:
            True if exists, False otherwise
        """
        try:
            query = select(func.count(self.model.id)).where(self.model.id == id)
            result = await self.session.execute(query)
            count = result.scalar() or 0
            
            return count > 0
            
        except Exception as exc:
            logger.error(
                "Error checking entity existence",
                model=self.model.__name__,
                id=id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_by_field(self, field: str, value: Any) -> ModelType | None:
        """
        Find entity by specific field.
        
        Args:
            field: Field name
            value: Field value
            
        Returns:
            Entity or None if not found
        """
        try:
            if not hasattr(self.model, field):
                raise ValueError(f"Field '{field}' does not exist on model {self.model.__name__}")
            
            query = select(self.model).where(getattr(self.model, field) == value)
            result = await self.session.execute(query)
            entity = result.scalar_one_or_none()
            
            if entity:
                logger.debug(
                    "Found entity by field",
                    model=self.model.__name__,
                    field=field,
                    value=value,
                )
            
            return entity
            
        except Exception as exc:
            logger.error(
                "Error finding entity by field",
                model=self.model.__name__,
                field=field,
                value=value,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def bulk_create(self, objects: list[CreateSchemaType]) -> list[ModelType]:
        """
        Create multiple entities in bulk.
        
        Args:
            objects: List of create schemas
            
        Returns:
            List of created entities
        """
        try:
            db_objects = []
            
            for obj_in in objects:
                # Convert schema to dict
                if hasattr(obj_in, 'model_dump'):
                    obj_data = obj_in.model_dump()
                elif hasattr(obj_in, 'dict'):
                    obj_data = obj_in.dict()
                else:
                    obj_data = dict(obj_in)
                
                db_obj = self.model(**obj_data)
                db_objects.append(db_obj)
            
            self.session.add_all(db_objects)
            await self.session.commit()
            
            # Refresh all objects
            for db_obj in db_objects:
                await self.session.refresh(db_obj)
            
            logger.info(
                "Bulk created entities",
                model=self.model.__name__,
                count=len(db_objects),
            )
            
            return db_objects
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error bulk creating entities",
                model=self.model.__name__,
                count=len(objects),
                error=str(exc),
                exc_info=True,
            )
            raise