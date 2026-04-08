"""
Tests unitarios para AuditRepository.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.repository import AuditRepository
from app.models.audit_log import AuditLog
from app.models.client import Client
from app.core.security import hash_password


@pytest.fixture
async def audit_repository(db_session: AsyncSession):
    """Fixture para AuditRepository."""
    return AuditRepository(db_session)


@pytest.fixture
async def sample_client(db_session: AsyncSession):
    """Fixture para crear un cliente de prueba."""
    client = Client(
        email="audit_test@example.com",
        password_hash=hash_password("TestPassword123!"),
        first_name="Audit",
        last_name="Test",
        phone="+1234567890",
        is_active=True
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


class TestAuditRepository:
    """Tests para AuditRepository."""

    async def test_create_audit_log(
        self,
        audit_repository: AuditRepository,
        sample_client: Client
    ):
        """Test crear log de auditoría."""
        audit_log = await audit_repository.create_audit_log(
            user_id=sample_client.id,
            user_type="client",
            action="LOGIN",
            resource_type="AUTH",
            resource_id=str(sample_client.id),
            ip_address="192.168.1.1",
            user_agent="Test Agent",
            details={"method": "password"}
        )
        
        assert audit_log.id is not None
        assert audit_log.user_id == sample_client.id
        assert audit_log.user_type == "client"
        assert audit_log.action == "LOGIN"
        assert audit_log.resource_type == "AUTH"
        assert audit_log.ip_address == "192.168.1.1"
        assert audit_log.details["method"] == "password"

    async def test_find_audit_logs_all(
        self,
        audit_repository: AuditRepository,
        sample_client: Client
    ):
        """Test buscar todos los logs de auditoría."""
        # Crear múltiples logs
        for i in range(5):
            await audit_repository.create_audit_log(
                user_id=sample_client.id,
                user_type="client",
                action=f"ACTION_{i}",
                resource_type="TEST",
                ip_address="192.168.1.1"
            )
        
        # Buscar todos
        logs, total = await audit_repository.find_audit_logs(
            skip=0,
            limit=10
        )
        
        assert len(logs) >= 5
        assert total >= 5

    async def test_find_audit_logs_by_user(
        self,
        audit_repository: AuditRepository,
        sample_client: Client,
        db_session: AsyncSession
    ):
        """Test buscar logs por usuario."""
        # Crear otro cliente
        client2 = Client(
            email="audit_test2@example.com",
            password_hash=hash_password("TestPassword123!"),
            first_name="Audit2",
            last_name="Test2",
            phone="+9876543210",
            is_active=True
        )
        db_session.add(client2)
        await db_session.commit()
        await db_session.refresh(client2)
        
        # Crear logs para ambos usuarios
        await audit_repository.create_audit_log(
            user_id=sample_client.id,
            user_type="client",
            action="ACTION_1",
            resource_type="TEST",
            ip_address="192.168.1.1"
        )
        
        await audit_repository.create_audit_log(
            user_id=client2.id,
            user_type="client",
            action="ACTION_2",
            resource_type="TEST",
            ip_address="192.168.1.2"
        )
        
        # Buscar logs del primer usuario
        logs, total = await audit_repository.find_audit_logs(
            user_id=sample_client.id,
            user_type="client",
            skip=0,
            limit=10
        )
        
        assert len(logs) >= 1
        assert all(log.user_id == sample_client.id for log in logs)

    async def test_find_audit_logs_by_action(
        self,
        audit_repository: AuditRepository,
        sample_client: Client
    ):
        """Test buscar logs por acción."""
        # Crear logs con diferentes acciones
        await audit_repository.create_audit_log(
            user_id=sample_client.id,
            user_type="client",
            action="LOGIN",
            resource_type="AUTH",
            ip_address="192.168.1.1"
        )
        
        await audit_repository.create_audit_log(
            user_id=sample_client.id,
            user_type="client",
            action="LOGOUT",
            resource_type="AUTH",
            ip_address="192.168.1.1"
        )
        
        # Buscar logs de LOGIN
        logs, total = await audit_repository.find_audit_logs(
            action="LOGIN",
            skip=0,
            limit=10
        )
        
        assert len(logs) >= 1
        assert all(log.action == "LOGIN" for log in logs)

    async def test_find_audit_logs_by_resource_type(
        self,
        audit_repository: AuditRepository,
        sample_client: Client
    ):
        """Test buscar logs por tipo de recurso."""
        # Crear logs con diferentes tipos de recurso
        await audit_repository.create_audit_log(
            user_id=sample_client.id,
            user_type="client",
            action="CREATE",
            resource_type="USER",
            ip_address="192.168.1.1"
        )
        
        await audit_repository.create_audit_log(
            user_id=sample_client.id,
            user_type="client",
            action="UPDATE",
            resource_type="PROFILE",
            ip_address="192.168.1.1"
        )
        
        # Buscar logs de USER
        logs, total = await audit_repository.find_audit_logs(
            resource_type="USER",
            skip=0,
            limit=10
        )
        
        assert len(logs) >= 1
        assert all(log.resource_type == "USER" for log in logs)

    async def test_find_audit_logs_by_date_range(
        self,
        audit_repository: AuditRepository,
        sample_client: Client
    ):
        """Test buscar logs por rango de fechas."""
        now = datetime.utcnow()
        
        # Crear log
        await audit_repository.create_audit_log(
            user_id=sample_client.id,
            user_type="client",
            action="TEST_ACTION",
            resource_type="TEST",
            ip_address="192.168.1.1"
        )
        
        # Buscar en rango que incluye el log
        logs, total = await audit_repository.find_audit_logs(
            start_date=now - timedelta(hours=1),
            end_date=now + timedelta(hours=1),
            skip=0,
            limit=10
        )
        
        assert len(logs) >= 1

    async def test_find_audit_logs_pagination(
        self,
        audit_repository: AuditRepository,
        sample_client: Client
    ):
        """Test paginación de logs."""
        # Crear múltiples logs
        for i in range(15):
            await audit_repository.create_audit_log(
                user_id=sample_client.id,
                user_type="client",
                action=f"ACTION_{i}",
                resource_type="TEST",
                ip_address="192.168.1.1"
            )
        
        # Primera página
        logs_page1, total = await audit_repository.find_audit_logs(
            user_id=sample_client.id,
            user_type="client",
            skip=0,
            limit=10
        )
        
        # Segunda página
        logs_page2, _ = await audit_repository.find_audit_logs(
            user_id=sample_client.id,
            user_type="client",
            skip=10,
            limit=10
        )
        
        assert len(logs_page1) == 10
        assert len(logs_page2) >= 5
        assert total >= 15

    async def test_find_user_activity(
        self,
        audit_repository: AuditRepository,
        sample_client: Client
    ):
        """Test buscar actividad de usuario."""
        # Crear logs
        for i in range(3):
            await audit_repository.create_audit_log(
                user_id=sample_client.id,
                user_type="client",
                action=f"ACTION_{i}",
                resource_type="TEST",
                ip_address="192.168.1.1"
            )
        
        # Buscar actividad
        logs = await audit_repository.find_user_activity(
            sample_client.id,
            "client",
            limit=10
        )
        
        assert len(logs) >= 3
        assert all(log.user_id == sample_client.id for log in logs)

    async def test_delete_old_logs(
        self,
        audit_repository: AuditRepository,
        sample_client: Client,
        db_session: AsyncSession
    ):
        """Test eliminar logs antiguos."""
        # Crear log antiguo manualmente
        old_log = AuditLog(
            user_id=sample_client.id,
            user_type="client",
            action="OLD_ACTION",
            resource_type="TEST",
            ip_address="192.168.1.1",
            created_at=datetime.utcnow() - timedelta(days=91)
        )
        db_session.add(old_log)
        
        # Crear log reciente
        await audit_repository.create_audit_log(
            user_id=sample_client.id,
            user_type="client",
            action="RECENT_ACTION",
            resource_type="TEST",
            ip_address="192.168.1.1"
        )
        
        await db_session.commit()
        
        # Eliminar logs antiguos (>90 días)
        count = await audit_repository.delete_old_logs(days=90)
        
        assert count >= 1
        
        # Verificar que el reciente sigue existiendo
        logs, _ = await audit_repository.find_audit_logs(
            action="RECENT_ACTION",
            skip=0,
            limit=10
        )
        assert len(logs) >= 1

    async def test_count_user_actions(
        self,
        audit_repository: AuditRepository,
        sample_client: Client
    ):
        """Test contar acciones de usuario."""
        # Crear múltiples logs de LOGIN
        for i in range(5):
            await audit_repository.create_audit_log(
                user_id=sample_client.id,
                user_type="client",
                action="LOGIN",
                resource_type="AUTH",
                ip_address="192.168.1.1"
            )
        
        # Contar acciones de LOGIN en las últimas 24 horas
        count = await audit_repository.count_user_actions(
            user_id=sample_client.id,
            user_type="client",
            action="LOGIN",
            hours=24
        )
        
        assert count >= 5
