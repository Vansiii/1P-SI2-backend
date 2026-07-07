import pytest
from pydantic import ValidationError
from app.models.inventory_product import InventoryProduct
from app.models.supplier import Supplier
from app.models.inventory_category import InventoryCategory
from app.modules.inventory.schemas import (
    InventoryProductCreate,
    InventoryMovementCreate,
)


class TestInventoryCategoryModel:
    def test_category_creation_defaults(self):
        category = InventoryCategory(
            tenant_id=1,
            name="Repuestos Motor",
            description="Filtros, bujías y partes de motor",
            is_active=True
        )
        assert category.tenant_id == 1
        assert category.name == "Repuestos Motor"
        assert category.description == "Filtros, bujías y partes de motor"
        assert category.is_active is True


class TestSupplierModel:
    def test_supplier_creation_defaults(self):
        supplier = Supplier(
            tenant_id=1,
            name="Importadora El Condor",
            contact_name="Pedro Condori",
            country="Bolivia",
            is_active=True
        )
        assert supplier.tenant_id == 1
        assert supplier.name == "Importadora El Condor"
        assert supplier.contact_name == "Pedro Condori"
        assert supplier.country == "Bolivia"
        assert supplier.is_active is True


class TestInventoryProductModel:
    def test_product_creation_defaults(self):
        product = InventoryProduct(
            tenant_id=1,
            name="Bujía Bosch Spark",
            current_stock=10,
            min_stock=2,
            cost_price=15.50,
            avg_cost_price=15.50,
            is_active=True,
            is_published=False
        )
        assert product.tenant_id == 1
        assert product.name == "Bujía Bosch Spark"
        assert product.current_stock == 10
        assert product.min_stock == 2
        assert float(product.cost_price) == 15.50
        assert float(product.avg_cost_price) == 15.50
        assert product.is_active is True
        assert product.is_published is False


class TestInventorySchemas:
    def test_create_product_schema_validation(self):
        # Valid data
        data = {
            "name": "Pastillas de Freno",
            "current_stock": 5,
            "min_stock": 1,
            "cost_price": 45.0,
            "compatible_brands": ["Toyota", "Suzuki"]
        }
        product = InventoryProductCreate.model_validate(data)
        assert product.name == "Pastillas de Freno"
        assert product.current_stock == 5
        assert product.min_stock == 1
        assert product.cost_price == 45.0
        assert product.compatible_brands == ["Toyota", "Suzuki"]

        # Invalid stock (negative)
        with pytest.raises(ValidationError):
            InventoryProductCreate.model_validate({**data, "current_stock": -1})

        # Invalid min stock (negative)
        with pytest.raises(ValidationError):
            InventoryProductCreate.model_validate({**data, "min_stock": -1})

        # Invalid cost (negative)
        with pytest.raises(ValidationError):
            InventoryProductCreate.model_validate({**data, "cost_price": -10.0})

    def test_create_movement_schema_validation(self):
        # Entrada requires unit_cost
        with pytest.raises(ValidationError):
            InventoryMovementCreate.model_validate({
                "product_id": 1,
                "type": "entrada",
                "quantity": 10,
                "unit_cost": None
            })

        # Entrada with valid unit_cost
        mov = InventoryMovementCreate.model_validate({
            "product_id": 1,
            "type": "entrada",
            "quantity": 10,
            "unit_cost": 25.0
        })
        assert mov.product_id == 1
        assert mov.type == "entrada"
        assert mov.quantity == 10
        assert mov.unit_cost == 25.0

        # Salida doesn't require unit_cost
        mov_salida = InventoryMovementCreate.model_validate({
            "product_id": 1,
            "type": "salida",
            "quantity": 2
        })
        assert mov_salida.product_id == 1
        assert mov_salida.type == "salida"
        assert mov_salida.quantity == 2
        assert mov_salida.unit_cost is None
