"""
Tests para AuditService.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import AuditService
from app.modules.audit.schemas import AuditLogFilter
from app.models.audit_log import AuditLog
from app.shared.enums.common import AuditAction, ResourceType


@pytest.fixture
def mock_db():
    """Mock de sesión de base de datos."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def audit_service(mock_db):
    """Fixture del servicio de auditoría."""
    return AuditService(mock_db)


@pytest.mark.asyncio
class TestAuditService:
    """Tests para AuditService."""

    async def test_log_action_success(self, audit_service, mock_db):
        """Test de registro exitoso de acción."""
        # Arrange
        user_id = 1
        user_type = "client"
        action = AuditAction.LOGIN
        resource_type = ResourceType.USER
        resource_id = 1
        ip_address = "192.168.1.1"
        user_agent = "Mozilla/5.0"
        details = {"method": "email"}
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.create.return_value = AuditLog(
            id=1,
            user_id=user_id,
            user_type=user_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            timestamp=datetime.utcnow()
        )
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result = await audit_service.log_action(
                user_id=user_id,
                user_type=user_type,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details
            )
            
            # Assert
            assert result.user_id == user_id
            assert result.action == action
            mock_audit_repo.create.assert_called_once()

    async def test_log_action_from_request(self, audit_service, mock_db):
        """Test de registro de acción desde request."""
        # Arrange
        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers.get.return_value = "Mozilla/5.0"
        
        user_id = 1
        user_type = "client"
        action = AuditAction.UPDATE_PROFILE
        resource_type = ResourceType.USER
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.create.return_value = AuditLog(
            id=1,
            user_id=user_id,
            user_type=user_type,
            action=action,
            resource_type=resource_type
        )
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result = await audit_service.log_action_from_request(
                request=mock_request,
                user_id=user_id,
                user_type=user_type,
                action=action,
                resource_type=resource_type
            )
            
            # Assert
            assert result.user_id == user_id
            mock_audit_repo.create.assert_called_once()

    async def test_get_audit_logs_with_filters(self, audit_service, mock_db):
        """Test de obtención de logs con filtros."""
        # Arrange
        filters = AuditLogFilter(
            user_id=1,
            action=AuditAction.LOGIN,
            start_date=datetime.utcnow() - timedelta(days=7),
            end_date=datetime.utcnow()
        )
        
        mock_logs = [
            AuditLog(
                id=1,
                user_id=1,
                user_type="client",
                action=AuditAction.LOGIN,
                timestamp=datetime.utcnow()
            ),
            AuditLog(
                id=2,
                user_id=1,
                user_type="client",
                action=AuditAction.LOGIN,
                timestamp=datetime.utcnow() - timedelta(days=1)
            )
        ]
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.find_with_filters.return_value = (mock_logs, 2)
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result, total = await audit_service.get_audit_logs(filters, skip=0, limit=10)
            
            # Assert
            assert len(result) == 2
            assert total == 2
            mock_audit_repo.find_with_filters.assert_called_once()

    async def test_get_audit_logs_pagination(self, audit_service, mock_db):
        """Test de paginación de logs."""
        # Arrange
        filters = AuditLogFilter()
        
        mock_logs = [AuditLog(id=i, user_id=1, action=AuditAction.LOGIN) for i in range(10)]
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.find_with_filters.return_value = (mock_logs, 100)
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result, total = await audit_service.get_audit_logs(filters, skip=20, limit=10)
            
            # Assert
            assert len(result) == 10
            assert total == 100
            call_args = mock_audit_repo.find_with_filters.call_args
            assert call_args[1]['skip'] == 20
            assert call_args[1]['limit'] == 10

    async def test_get_user_activity(self, audit_service, mock_db):
        """Test de obtención de actividad de usuario."""
        # Arrange
        user_id = 1
        user_type = "client"
        
        mock_logs = [
            AuditLog(
                id=1,
                user_id=user_id,
                user_type=user_type,
                action=AuditAction.LOGIN,
                timestamp=datetime.utcnow()
            ),
            AuditLog(
                id=2,
                user_id=user_id,
                user_type=user_type,
                action=AuditAction.UPDATE_PROFILE,
                timestamp=datetime.utcnow() - timedelta(hours=1)
            )
        ]
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.find_by_user.return_value = (mock_logs, 2)
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result, total = await audit_service.get_user_activity(user_id, user_type, skip=0, limit=10)
            
            # Assert
            assert len(result) == 2
            assert total == 2
            assert all(log.user_id == user_id for log in result)

    async def test_get_audit_actions(self, audit_service, mock_db):
        """Test de obtención de acciones disponibles."""
        # Act
        result = await audit_service.get_audit_actions()
        
        # Assert
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(action, str) for action in result)

    async def test_get_resource_types(self, audit_service, mock_db):
        """Test de obtención de tipos de recursos."""
        # Act
        result = await audit_service.get_resource_types()
        
        # Assert
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(resource, str) for resource in result)

    async def test_cleanup_old_logs(self, audit_service, mock_db):
        """Test de limpieza de logs antiguos."""
        # Arrange
        days_to_keep = 90
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.delete_older_than.return_value = 150  # 150 logs eliminados
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            deleted_count = await audit_service.cleanup_old_logs(days_to_keep)
            
            # Assert
            assert deleted_count == 150
            mock_audit_repo.delete_older_than.assert_called_once()

    async def test_get_audit_logs_by_action(self, audit_service, mock_db):
        """Test de obtención de logs por acción específica."""
        # Arrange
        action = AuditAction.LOGIN
        
        mock_logs = [
            AuditLog(id=1, action=action, user_id=1),
            AuditLog(id=2, action=action, user_id=2)
        ]
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.find_by_action.return_value = (mock_logs, 2)
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result, total = await audit_service.get_audit_logs_by_action(action, skip=0, limit=10)
            
            # Assert
            assert len(result) == 2
            assert all(log.action == action for log in result)

    async def test_get_audit_logs_by_resource(self, audit_service, mock_db):
        """Test de obtención de logs por recurso."""
        # Arrange
        resource_type = ResourceType.USER
        resource_id = 1
        
        mock_logs = [
            AuditLog(id=1, resource_type=resource_type, resource_id=resource_id),
            AuditLog(id=2, resource_type=resource_type, resource_id=resource_id)
        ]
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.find_by_resource.return_value = (mock_logs, 2)
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result, total = await audit_service.get_audit_logs_by_resource(
                resource_type, resource_id, skip=0, limit=10
            )
            
            # Assert
            assert len(result) == 2
            assert all(log.resource_id == resource_id for log in result)

    async def test_log_action_handles_missing_optional_fields(self, audit_service, mock_db):
        """Test de registro con campos opcionales faltantes."""
        # Arrange
        user_id = 1
        user_type = "client"
        action = AuditAction.LOGIN
        resource_type = ResourceType.USER
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.create.return_value = AuditLog(
            id=1,
            user_id=user_id,
            user_type=user_type,
            action=action,
            resource_type=resource_type
        )
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result = await audit_service.log_action(
                user_id=user_id,
                user_type=user_type,
                action=action,
                resource_type=resource_type
                # Sin ip_address, user_agent, details
            )
            
            # Assert
            assert result.user_id == user_id
            mock_audit_repo.create.assert_called_once()

    async def test_get_audit_logs_empty_result(self, audit_service, mock_db):
        """Test de obtención de logs sin resultados."""
        # Arrange
        filters = AuditLogFilter(user_id=999)  # Usuario inexistente
        
        mock_audit_repo = AsyncMock()
        mock_audit_repo.find_with_filters.return_value = ([], 0)
        
        with patch.object(audit_service, '_audit_repo', mock_audit_repo):
            # Act
            result, total = await audit_service.get_audit_logs(filters, skip=0, limit=10)
            
            # Assert
            assert len(result) == 0
            assert total == 0
