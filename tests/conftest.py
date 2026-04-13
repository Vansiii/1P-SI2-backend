"""
Pytest configuration and shared fixtures.
"""
import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import get_db_session, get_settings
from app.core.config import Settings
from app.main import app
from app.models.base import Base
from app.models.user import User
from app.models.client import Client
from app.models.workshop import Workshop
from app.models.technician import Technician
from app.models.administrator import Administrator


# Test settings
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test settings with in-memory database."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        jwt_secret_key="test-secret-key-for-testing-only",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
        cors_origins=["http://localhost:3000"],
        app_name="1P-SI2 Backend Test",
        app_version="0.1.0-test",
    )


# Database fixtures
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def async_engine(test_settings: Settings):
    """Create async engine for testing."""
    engine = create_async_engine(
        test_settings.database_url,
        echo=False,
        poolclass=StaticPool,
        connect_args={
            "check_same_thread": False,
        },
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Clean up
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    async_session = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def client(db_session: AsyncSession, test_settings: Settings) -> TestClient:
    """Create a test client with dependency overrides."""
    
    def override_get_db_session():
        return db_session
    
    def override_get_settings():
        return test_settings
    
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_settings] = override_get_settings
    
    with TestClient(app) as test_client:
        yield test_client
    
    # Clean up overrides
    app.dependency_overrides.clear()


# User fixtures
@pytest_asyncio.fixture
async def sample_client(db_session: AsyncSession) -> Client:
    """Create a sample client for testing."""
    from datetime import date
    from app.core.security import hash_password
    
    client = Client(
        email="client@test.com",
        password_hash=hash_password("testpassword123"),
        user_type="client",
        is_active=True,
        two_factor_enabled=False,
        direccion="Test Address 123",
        ci="12345678",
        fecha_nacimiento=date(1990, 1, 1),
    )
    
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    
    return client


@pytest_asyncio.fixture
async def sample_workshop(db_session: AsyncSession) -> Workshop:
    """Create a sample workshop for testing."""
    from app.core.security import hash_password
    
    workshop = Workshop(
        email="workshop@test.com",
        password_hash=hash_password("testpassword123"),
        user_type="workshop",
        is_active=True,
        two_factor_enabled=False,
        workshop_name="Test Workshop",
        owner_name="Test Owner",
        latitude=-17.7833,
        longitude=-63.1821,
        coverage_radius_km=10.0,
    )
    
    db_session.add(workshop)
    await db_session.commit()
    await db_session.refresh(workshop)
    
    return workshop


@pytest_asyncio.fixture
async def sample_technician(db_session: AsyncSession, sample_workshop: Workshop) -> Technician:
    """Create a sample technician for testing."""
    from app.core.security import hash_password
    
    technician = Technician(
        email="technician@test.com",
        password_hash=hash_password("testpassword123"),
        user_type="technician",
        is_active=True,
        two_factor_enabled=False,
        workshop_id=sample_workshop.id,
        current_latitude=-17.7833,
        current_longitude=-63.1821,
        is_available=True,
    )
    
    db_session.add(technician)
    await db_session.commit()
    await db_session.refresh(technician)
    
    return technician


@pytest_asyncio.fixture
async def sample_admin(db_session: AsyncSession) -> Administrator:
    """Create a sample administrator for testing."""
    from app.core.security import hash_password
    
    admin = Administrator(
        email="admin@test.com",
        password_hash=hash_password("testpassword123"),
        user_type="administrator",
        is_active=True,
        two_factor_enabled=False,
        role_level=1,
    )
    
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    return admin


@pytest.fixture
def auth_headers(sample_client: Client) -> dict[str, str]:
    """Create authentication headers for testing."""
    from app.core.security import create_access_token
    
    access_token, _, _ = create_access_token(
        subject=str(sample_client.id),
        email=sample_client.email,
        user_type=sample_client.user_type,
    )
    
    return {"Authorization": f"Bearer {access_token}"}


# Utility fixtures
@pytest.fixture
def mock_email_service():
    """Mock email service for testing."""
    from unittest.mock import AsyncMock
    
    mock_service = AsyncMock()
    mock_service.send_welcome_email.return_value = True
    mock_service.send_password_reset_email.return_value = True
    mock_service.send_otp_email.return_value = True
    mock_service.send_password_changed_email.return_value = True
    mock_service.send_account_locked_email.return_value = True
    mock_service.send_account_unlocked_email.return_value = True
    mock_service.send_security_notification_email.return_value = True
    
    return mock_service