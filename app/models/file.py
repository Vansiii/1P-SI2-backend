"""
Modelo para gestión de archivos.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Index
from .base import Base


class File(Base):
    """Modelo para archivos subidos al storage."""
    
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False, unique=True)
    file_url = Column(String(1000), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size = Column(BigInteger, nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    uploaded_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_entity', 'entity_type', 'entity_id'),
        Index('idx_uploaded_by', 'uploaded_by'),
    )
