"""
Tests for user repository.
"""
import pytest
from datetime import date

from app.modules.auth.repository import UserRepository
from app.models.client import Client
from app.models.workshop import Workshop
from app.models.technician import Technician
from app.models.administrator import Administrator
from app.core.security import hash_password


class TestUserRepository:
    """Test UserRepository."""
    
    @pytest.mark.asyncio
    async def test_find_by_email_existing(self, db_session, sample_client):
        """Test finding user by existing email."""
        repo = UserRepository(db_session)
        
        user = await repo.find_by_email(sample_client.email)
        
        assert user is not None
        assert user.id == sample_client.id
        assert user.email == sample_client.email
    
    @pytest.mark.asyncio
    async def test_find_by_email_non_existing(self, db_session):
        """Test finding user by non-existing email."""
        repo = UserRepository(db_session)
        
        user = await repo.find_by_email("nonexistent@test.com")
        
        assert user is None
    
    @pytest.mark.asyncio
    async def test_find_active_by_email(self, db_session, sample_client):
        """Test finding active user by email."""
        repo = UserRepository(db_session)
        
        user = await repo.find_active_by_email(sample_client.email)
        
        assert user is not None
        assert user.is_active is True
    
    @pytest.mark.asyncio
    async def test_find_active_by_email_inactive_user(self, db_session):
        """Test finding active user when user is inactive."""
        repo = UserRepository(db_session)
        
        # Create inactive user
        inactive_user = Client(
            email="inactive@test.com",
            password_hash=hash_password("password123"),
            user_type="client",
            is_active=False,
            two_factor_enabled=False,
            direccion="Test Address",
            ci="87654321",
            fecha_nacimiento=date(1990, 1, 1),
        )
        
        db_session.add(inactive_user)
        await db_session.commit()
        
        user = await repo.find_active_by_email("inactive@test.com")
        
        assert user is None
    
    @pytest.mark.asyncio
    async def test_email_exists_true(self, db_session, sample_client):
        """Test email exists check for existing email."""
        repo = UserRepository(db_session)
        
        exists = await repo.email_exists(sample_client.email)
        
        assert exists is True
    
    @pytest.mark.asyncio
    async def test_email_exists_false(self, db_session):
        """Test email exists check for non-existing email."""
        repo = UserRepository(db_session)
        
        exists = await repo.email_exists("nonexistent@test.com")
        
        assert exists is False
    
    @pytest.mark.asyncio
    async def test_find_by_id_or_raise_existing(self, db_session, sample_client):
        """Test finding user by ID that exists."""
        repo = UserRepository(db_session)
        
        user = await repo.find_by_id_or_raise(sample_client.id)
        
        assert user is not None
        assert user.id == sample_client.id
    
    @pytest.mark.asyncio
    async def test_find_by_id_or_raise_non_existing(self, db_session):
        """Test finding user by ID that doesn't exist."""
        repo = UserRepository(db_session)
        
        with pytest.raises(Exception):  # Should raise UserNotFoundException
            await repo.find_by_id_or_raise(99999)
    
    @pytest.mark.asyncio
    async def test_update_last_login(self, db_session, sample_client):
        """Test updating user's last login timestamp."""
        repo = UserRepository(db_session)
        
        original_last_login = sample_client.last_login_at
        
        await repo.update_last_login(sample_client.id)
        await db_session.refresh(sample_client)
        
        assert sample_client.last_login_at != original_last_login
        assert sample_client.last_login_at is not None
    
    @pytest.mark.asyncio
    async def test_deactivate_user(self, db_session, sample_client):
        """Test deactivating a user."""
        repo = UserRepository(db_session)
        
        await repo.deactivate_user(sample_client.id)
        await db_session.refresh(sample_client)
        
        assert sample_client.is_active is False