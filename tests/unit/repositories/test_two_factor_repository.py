"""
Tests unitarios para TwoFactorRepository.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.two_factor.repository import TwoFactorRepository
from app.models.two_factor_auth import TwoFactorAuth
from app.models.client import Client
from app.core.security import hash_password


@pytest.fixture
async def two_factor_repository(db_session: AsyncSession):
    """Fixture para TwoFactorRepository."""
    return TwoFactorRepository(db_session)


@pytest.fixture
async def sample_client(db_session: AsyncSession):
    """Fixture para crear un cliente de prueba."""
    client = Client(
        email="2fa_test@example.com",
        password_hash=hash_password("TestPassword123!"),
        first_name="TwoFactor",
        last_name="Test",
        phone="+1234567890",
        is_active=True
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


class TestTwoFactorRepository:
    """Tests para TwoFactorRepository."""

    async def test_create_or_update_2fa_new(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client
    ):
        """Test crear nueva configuración 2FA."""
        otp_hash = "otp_hash_123"
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        
        two_fa = await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash=otp_hash,
            expires_at=expires_at
        )
        
        assert two_fa.id is not None
        assert two_fa.user_id == sample_client.id
        assert two_fa.user_type == "client"
        assert two_fa.otp_hash == otp_hash
        assert two_fa.expires_at == expires_at
        assert two_fa.is_enabled is False
        assert two_fa.failed_attempts == 0

    async def test_create_or_update_2fa_existing(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client
    ):
        """Test actualizar configuración 2FA existente."""
        # Crear inicial
        otp_hash_1 = "otp_hash_1"
        expires_at_1 = datetime.utcnow() + timedelta(minutes=5)
        
        two_fa_1 = await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash=otp_hash_1,
            expires_at=expires_at_1
        )
        
        # Actualizar
        otp_hash_2 = "otp_hash_2"
        expires_at_2 = datetime.utcnow() + timedelta(minutes=10)
        
        two_fa_2 = await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash=otp_hash_2,
            expires_at=expires_at_2
        )
        
        # Debe ser el mismo registro actualizado
        assert two_fa_2.id == two_fa_1.id
        assert two_fa_2.otp_hash == otp_hash_2
        assert two_fa_2.expires_at == expires_at_2
        assert two_fa_2.failed_attempts == 0  # Reset

    async def test_find_2fa_config(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client
    ):
        """Test buscar configuración 2FA."""
        # Crear configuración
        await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash="test_hash",
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        
        # Buscar
        found_config = await two_factor_repository.find_2fa_config(
            sample_client.id,
            "client"
        )
        
        assert found_config is not None
        assert found_config.user_id == sample_client.id
        assert found_config.user_type == "client"

    async def test_find_2fa_config_not_found(
        self,
        two_factor_repository: TwoFactorRepository
    ):
        """Test buscar configuración 2FA inexistente."""
        found_config = await two_factor_repository.find_2fa_config(
            999999,
            "client"
        )
        assert found_config is None

    async def test_enable_2fa(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client
    ):
        """Test habilitar 2FA."""
        # Crear configuración
        two_fa = await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash="test_hash",
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        
        # Habilitar
        await two_factor_repository.enable_2fa(two_fa.id)
        
        # Verificar
        updated_config = await two_factor_repository.find_2fa_config(
            sample_client.id,
            "client"
        )
        assert updated_config.is_enabled is True

    async def test_disable_2fa(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client
    ):
        """Test deshabilitar 2FA."""
        # Crear y habilitar configuración
        two_fa = await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash="test_hash",
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        await two_factor_repository.enable_2fa(two_fa.id)
        
        # Deshabilitar
        await two_factor_repository.disable_2fa(
            sample_client.id,
            "client"
        )
        
        # Verificar
        updated_config = await two_factor_repository.find_2fa_config(
            sample_client.id,
            "client"
        )
        assert updated_config.is_enabled is False

    async def test_increment_failed_attempts(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client
    ):
        """Test incrementar intentos fallidos."""
        # Crear configuración
        two_fa = await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash="test_hash",
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        
        # Incrementar intentos
        await two_factor_repository.increment_failed_attempts(two_fa.id)
        await two_factor_repository.increment_failed_attempts(two_fa.id)
        
        # Verificar
        updated_config = await two_factor_repository.find_2fa_config(
            sample_client.id,
            "client"
        )
        assert updated_config.failed_attempts == 2

    async def test_reset_failed_attempts(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client
    ):
        """Test resetear intentos fallidos."""
        # Crear configuración con intentos fallidos
        two_fa = await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash="test_hash",
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        await two_factor_repository.increment_failed_attempts(two_fa.id)
        await two_factor_repository.increment_failed_attempts(two_fa.id)
        
        # Resetear
        await two_factor_repository.reset_failed_attempts(two_fa.id)
        
        # Verificar
        updated_config = await two_factor_repository.find_2fa_config(
            sample_client.id,
            "client"
        )
        assert updated_config.failed_attempts == 0

    async def test_is_2fa_enabled(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client
    ):
        """Test verificar si 2FA está habilitado."""
        # Sin configuración
        is_enabled = await two_factor_repository.is_2fa_enabled(
            sample_client.id,
            "client"
        )
        assert is_enabled is False
        
        # Crear configuración deshabilitada
        two_fa = await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash="test_hash",
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        
        is_enabled = await two_factor_repository.is_2fa_enabled(
            sample_client.id,
            "client"
        )
        assert is_enabled is False
        
        # Habilitar
        await two_factor_repository.enable_2fa(two_fa.id)
        
        is_enabled = await two_factor_repository.is_2fa_enabled(
            sample_client.id,
            "client"
        )
        assert is_enabled is True

    async def test_delete_expired_otp(
        self,
        two_factor_repository: TwoFactorRepository,
        sample_client: Client,
        db_session: AsyncSession
    ):
        """Test eliminar OTPs expirados."""
        # Crear configuración con OTP expirado
        client2 = Client(
            email="expired_otp@example.com",
            password_hash=hash_password("TestPassword123!"),
            first_name="Expired",
            last_name="OTP",
            phone="+9876543210",
            is_active=True
        )
        db_session.add(client2)
        await db_session.commit()
        await db_session.refresh(client2)
        
        await two_factor_repository.create_or_update_2fa(
            user_id=client2.id,
            user_type="client",
            otp_hash="expired_hash",
            expires_at=datetime.utcnow() - timedelta(minutes=10)
        )
        
        # Crear configuración con OTP válido
        await two_factor_repository.create_or_update_2fa(
            user_id=sample_client.id,
            user_type="client",
            otp_hash="valid_hash",
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        
        # Eliminar expirados
        count = await two_factor_repository.delete_expired_otp()
        
        assert count >= 1
        
        # Verificar que el válido sigue existiendo
        valid_config = await two_factor_repository.find_2fa_config(
            sample_client.id,
            "client"
        )
        assert valid_config is not None
