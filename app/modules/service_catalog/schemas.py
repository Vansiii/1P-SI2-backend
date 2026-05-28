from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional


class ServiceCatalogItemCreate(BaseModel):
    servicio_id: int
    modalidad: Literal["taller", "domicilio", "ambas"] = "taller"
    tiempo_estimado_min: Optional[int] = None
    precio: Optional[float] = None
    descripcion: Optional[str] = None

    @model_validator(mode="after")
    def validate_time_positive(self):
        if self.tiempo_estimado_min is not None and self.tiempo_estimado_min <= 0:
            raise ValueError("tiempo_estimado_min debe ser mayor a 0")
        if self.precio is not None and self.precio < 0:
            raise ValueError("precio debe ser >= 0")
        return self


class ServiceCatalogItemUpdate(BaseModel):
    modalidad: Optional[Literal["taller", "domicilio", "ambas"]] = None
    tiempo_estimado_min: Optional[int] = None
    precio: Optional[float] = None
    descripcion: Optional[str] = None

    @model_validator(mode="after")
    def validate_time_positive(self):
        if self.tiempo_estimado_min is not None and self.tiempo_estimado_min <= 0:
            raise ValueError("tiempo_estimado_min debe ser mayor a 0")
        if self.precio is not None and self.precio < 0:
            raise ValueError("precio debe ser >= 0")
        return self


class ServiceCatalogItemResponse(BaseModel):
    id: int
    servicio_id: int
    servicio_nombre: str
    categoria_id: int
    categoria_nombre: str
    modalidad: str
    tiempo_estimado_min: Optional[int] = None
    precio: Optional[float] = None
    descripcion: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    icon: Optional[str] = None

    class Config:
        from_attributes = True


class BaseServiceResponse(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    categoria_id: int
    categoria_nombre: str

    class Config:
        from_attributes = True
