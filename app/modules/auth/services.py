"""
Consolidated authentication services with repository pattern.
"""
from datetime import datetime, UTC, timedelta
import math
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import (
    AccountLockedException,
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    get_settings,
    UserNotFoundException,
    WeakPasswordException,
    create_access_token,
    create_refresh_token,
    get_logger,
    hash_password,
    validate_password_strength,
    verify_password,
)
from ...core.constants import UserType
from ...models.administrator import Administrator
from ...models.client import Client
from ...models.login_attempt import LoginAttempt
from ...models.refresh_token import RefreshToken
from ...models.technician import Technician
from ...models.user import User
from ...models.workshop import Workshop
from ...modules.notifications.service import NotificationService
from ...modules.tokens.repository import RefreshTokenRepository
from .repository import (
    AdministratorRepository,
    ClientRepository,
    TechnicianRepository,
    UserRepository,
    WorkshopRepository,
)
from .schemas import (
    AdministratorRegistrationRequest,
    ClientRegistrationRequest,
    LoginRequest,
    TechnicianRegistrationRequest,
    TokenResponse,
    UnifiedTokenResponse,
    UpdateProfileRequest,
    WorkshopRegistrationRequest,
)

logger = get_logger(__name__)


class RegistrationService:
    """Service for user registration with consolidated logic."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.client_repo = ClientRepository(session)
        self.workshop_repo = WorkshopRepository(session)
        self.technician_repo = TechnicianRepository(session)
        self.admin_repo = AdministratorRepository(session)
        self.token_repo = RefreshTokenRepository(session)
    
    async def _register_user_base(
        self,
        email: str,
        password: str,
        user_type: str,
        additional_data: dict[str, Any] | None = None,
    ) -> tuple[User, str, str]:
        """
        Base registration logic shared by all user types.
        
        Args:
            email: User email
            password: User password
            user_type: Type of user
            additional_data: Additional user-specific data
            
        Returns:
            Tuple of (user, access_token, refresh_token)
            
        Raises:
            EmailAlreadyExistsException: If email already exists
            WeakPasswordException: If password is weak
        """
        # Validate password strength
        is_valid, error_message = validate_password_strength(password)
        if not is_valid:
            raise WeakPasswordException(error_message)
        
        # Check if email already exists
        if await self.user_repo.email_exists(email):
            logger.warning("Registration attempt with existing email", email=email)
            raise EmailAlreadyExistsException(email)
        
        # Hash password
        password_hash = hash_password(password)
        
        # Prepare user data
        user_data = {
            "email": email.lower(),
            "password_hash": password_hash,
            "user_type": user_type,
            "is_active": True,
            "two_factor_enabled": False,
        }
        
        # Add additional data if provided
        if additional_data:
            user_data.update(additional_data)
        
        # Create user based on type
        if user_type == UserType.CLIENT:
            user = Client(**user_data)
        elif user_type == UserType.WORKSHOP:
            user = Workshop(**user_data)
        elif user_type == UserType.TECHNICIAN:
            user = Technician(**user_data)
        elif user_type == UserType.ADMINISTRATOR:
            user = Administrator(**user_data)
        else:
            raise ValueError(f"Invalid user type: {user_type}")
        
        # Save user
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        
        # Generate tokens
        access_token, expires_at, jti = create_access_token(
            subject=str(user.id),
            email=user.email,
            user_type=user.user_type,
        )
        
        refresh_token, refresh_token_hash = create_refresh_token()
        
        # Save refresh token
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        
        self.session.add(refresh_token_record)
        await self.session.commit()
        
        logger.info(
            "User registered successfully",
            user_id=user.id,
            email=email,
            user_type=user_type,
        )
        
        # Send welcome email
        await self._send_welcome_email(user, user_type)
        
        return user, access_token, refresh_token
    
    async def _send_welcome_email(self, user: User, user_type: str) -> None:
        """
        Send welcome email to newly registered user.
        
        Args:
            user: The newly created user
            user_type: Type of user (CLIENT, WORKSHOP, TECHNICIAN, ADMINISTRATOR)
        """
        try:
            notification_service = NotificationService()
            
            # Get user display name based on user type
            user_name = user.email.split('@')[0]  # Default fallback
            
            if user_type == UserType.CLIENT:
                if hasattr(user, 'first_name') and user.first_name:
                    user_name = user.first_name
            elif user_type == UserType.WORKSHOP:
                if hasattr(user, 'workshop_name') and user.workshop_name:
                    user_name = user.workshop_name
                elif hasattr(user, 'owner_name') and user.owner_name:
                    user_name = user.owner_name
            elif user_type == UserType.TECHNICIAN:
                if hasattr(user, 'first_name') and user.first_name:
                    user_name = user.first_name
            elif user_type == UserType.ADMINISTRATOR:
                if hasattr(user, 'first_name') and user.first_name:
                    user_name = user.first_name
            
            # Map user_type to friendly Spanish name
            user_type_names = {
                UserType.CLIENT: "Cliente",
                UserType.WORKSHOP: "Taller",
                UserType.TECHNICIAN: "Técnico",
                UserType.ADMINISTRATOR: "Administrador",
            }
            
            friendly_user_type = user_type_names.get(user_type, user_type)
            
            # Send welcome email
            await notification_service.send_welcome_email(
                to_email=user.email,
                user_name=user_name,
                user_type=friendly_user_type
            )
            
            logger.info("Welcome email sent", user_id=user.id, email=user.email)
            
        except Exception as e:
            # Don't fail registration if email fails
            logger.error(
                "Error sending welcome email",
                user_id=user.id,
                email=user.email,
                error=str(e)
            )
    
    async def register_client(
        self, 
        request: ClientRegistrationRequest
    ) -> tuple[Client, TokenResponse]:
        """
        Register a new client.
        
        Args:
            request: Client registration data
            
        Returns:
            Tuple of (client, token_response)
        """
        additional_data = {
            "first_name": request.first_name,
            "last_name": request.last_name,
            "phone": request.phone,
            "direccion": request.direccion,
            "ci": request.ci,
            "fecha_nacimiento": request.fecha_nacimiento,
        }
        
        user, access_token, refresh_token = await self._register_user_base(
            email=request.email,
            password=request.password,
            user_type=UserType.CLIENT,
            additional_data=additional_data,
        )
        
        token_response = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=30 * 60,  # 30 minutes
        )
        
        return user, token_response
    
    async def register_workshop(
        self, 
        request: WorkshopRegistrationRequest
    ) -> tuple[Workshop, TokenResponse]:
        """
        Register a new workshop.
        
        Args:
            request: Workshop registration data
            
        Returns:
            Tuple of (workshop, token_response)
        """
        additional_data = {
            "first_name": request.first_name,
            "last_name": request.last_name,
            "phone": request.phone,
            "workshop_name": request.workshop_name,
            "owner_name": request.owner_name,
            "address": request.address,
            "latitude": request.latitude,
            "longitude": request.longitude,
            "coverage_radius_km": request.coverage_radius_km,
            "is_verified": True,  # Auto-verify workshops on registration
            "is_available": True,  # Make workshop available by default
        }
        
        user, access_token, refresh_token = await self._register_user_base(
            email=request.email,
            password=request.password,
            user_type=UserType.WORKSHOP,
            additional_data=additional_data,
        )
        
        token_response = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=30 * 60,  # 30 minutes
        )
        
        return user, token_response
    
    async def register_technician(
        self, 
        request: TechnicianRegistrationRequest
    ) -> tuple[Technician, TokenResponse]:
        """
        Register a new technician with optional specialties.
        
        Args:
            request: Technician registration data
            
        Returns:
            Tuple of (technician, token_response)
            
        Raises:
            UserNotFoundException: If workshop or specialties don't exist
            EmailAlreadyExistsException: If email already exists
            WeakPasswordException: If password is weak
        """
        # Verify workshop exists
        workshop = await self.workshop_repo.find_by_id(request.workshop_id)
        if not workshop:
            logger.error("Workshop not found during technician registration", workshop_id=request.workshop_id)
            raise UserNotFoundException(f"Taller con ID {request.workshop_id} no encontrado")
        
        # Verify workshop is active
        if not workshop.is_active:
            logger.error("Inactive workshop during technician registration", workshop_id=request.workshop_id)
            raise ValueError(f"El taller {workshop.business_name} no está activo")
        
        # Verify specialties exist if provided
        if request.specialty_ids:
            from sqlalchemy import select
            from ...models.especialidad import Especialidad
            
            existing_specialties = await self.session.scalars(
                select(Especialidad.id).where(Especialidad.id.in_(request.specialty_ids))
            )
            existing_ids = set(existing_specialties.all())
            missing_ids = set(request.specialty_ids) - existing_ids
            
            if missing_ids:
                logger.error("Invalid specialty IDs during technician registration", 
                           missing_ids=list(missing_ids), provided_ids=request.specialty_ids)
                raise ValueError(f"Especialidades no encontradas: {list(missing_ids)}")
        
        additional_data = {
            "first_name": request.first_name,
            "last_name": request.last_name,
            "phone": request.phone,
            "workshop_id": request.workshop_id,
            "current_latitude": request.current_latitude,
            "current_longitude": request.current_longitude,
            "is_available": request.is_available,
        }
        
        try:
            user, access_token, refresh_token = await self._register_user_base(
                email=request.email,
                password=request.password,
                user_type=UserType.TECHNICIAN,
                additional_data=additional_data,
            )
            
            # Assign specialties if provided
            if request.specialty_ids:
                from ...models.technician_especialidad import TechnicianEspecialidad
                for specialty_id in request.specialty_ids:
                    assignment = TechnicianEspecialidad(
                        technician_id=user.id,
                        especialidad_id=specialty_id
                    )
                    self.session.add(assignment)
                await self.session.commit()
                
                logger.info("Technician specialties assigned", 
                          technician_id=user.id, specialty_ids=request.specialty_ids)
            
            token_response = TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=30 * 60,  # 30 minutes
            )
            
            logger.info("Technician registered successfully", 
                       technician_id=user.id, workshop_id=request.workshop_id)
            
            return user, token_response
            
        except Exception as e:
            logger.error("Error during technician registration", 
                        error=str(e), workshop_id=request.workshop_id, email=request.email)
            await self.session.rollback()
            raise
    
    async def register_administrator(
        self, 
        request: AdministratorRegistrationRequest
    ) -> tuple[Administrator, TokenResponse]:
        """
        Register a new administrator.
        
        Args:
            request: Administrator registration data
            
        Returns:
            Tuple of (administrator, token_response)
        """
        additional_data = {
            "first_name": request.first_name,
            "last_name": request.last_name,
            "phone": request.phone,
            "role_level": str(request.role_level),  # Convert to string for database
        }
        
        user, access_token, refresh_token = await self._register_user_base(
            email=request.email,
            password=request.password,
            user_type=UserType.ADMINISTRATOR,
            additional_data=additional_data,
        )
        
        token_response = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=30 * 60,  # 30 minutes
        )
        
        return user, token_response


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.token_repo = RefreshTokenRepository(session)
        self.settings = get_settings()

    async def _count_recent_failed_password_attempts(self, email: str) -> int:
        """Count recent failed attempts caused by incorrect password."""
        window_start = datetime.now(UTC) - timedelta(minutes=self.settings.lockout_duration_minutes)
        result = await self.session.execute(
            select(func.count(LoginAttempt.id)).where(
                LoginAttempt.email == email,
                LoginAttempt.success == False,
                LoginAttempt.failure_reason == "invalid_password",
                LoginAttempt.attempted_at >= window_start,
            )
        )
        return int(result.scalar() or 0)

    async def _clear_failed_login_attempts(self, email: str) -> None:
        """
        Clear/mark as resolved recent failed login attempts after successful login.
        This resets the counter so the user gets fresh attempts on next failure.
        
        We update the attempted_at timestamp of recent failed attempts to be older
        than the lockout window, effectively removing them from the count.
        """
        from sqlalchemy import update
        
        window_start = datetime.now(UTC) - timedelta(minutes=self.settings.lockout_duration_minutes)
        
        # Update failed attempts to be outside the counting window
        # Set their timestamp to be older than the lockout window
        old_timestamp = datetime.now(UTC) - timedelta(minutes=self.settings.lockout_duration_minutes + 1)
        
        await self.session.execute(
            update(LoginAttempt)
            .where(
                LoginAttempt.email == email,
                LoginAttempt.success == False,
                LoginAttempt.failure_reason == "invalid_password",
                LoginAttempt.attempted_at >= window_start,
            )
            .values(attempted_at=old_timestamp)
        )
        
        logger.info("Failed login attempts reset after successful login", email=email)

    async def _record_login_attempt(
        self,
        *,
        email: str,
        success: bool,
        ip_address: str,
        user_agent: str | None,
        user_id: int | None,
        failure_reason: str | None,
        locked_applied: bool = False,
    ) -> None:
        """Persist login attempt audit entry."""
        self.session.add(
            LoginAttempt(
                email=email,
                ip_address=ip_address,
                success=success,
                user_agent=(user_agent or "")[:500] or None,
                user_id=user_id,
                failure_reason=failure_reason,
                locked_applied=locked_applied,
            )
        )

    @staticmethod
    def _remaining_seconds(until: datetime) -> int:
        return max(0, math.ceil((until - datetime.now(UTC)).total_seconds()))
    
    async def login(
        self,
        request: LoginRequest,
        *,
        ip_address: str = "unknown",
        user_agent: str | None = None,
    ) -> tuple[User, UnifiedTokenResponse]:
        """
        Authenticate user and return tokens.
        
        Args:
            request: Login request data
            
        Returns:
            Tuple of (user, token_response)
            
        Raises:
            InvalidCredentialsException: If credentials are invalid
            UserNotFoundException: If user doesn't exist
        """
        email = request.email.strip().lower()

        # Find user by email
        user = await self.user_repo.find_active_by_email(email)
        if not user:
            logger.warning("Login attempt with non-existent email", email=email)
            raise InvalidCredentialsException("El email no existe. Verifica tu correo electrónico.")

        now = datetime.now(UTC)
        if user.blocked_until and user.blocked_until > now:
            remaining_seconds = self._remaining_seconds(user.blocked_until)
            raise AccountLockedException(
                unlock_time=user.blocked_until.isoformat(),
                retry_after=remaining_seconds,
                details={
                    "lockout_until": user.blocked_until.isoformat(),
                    "remaining_seconds": remaining_seconds,
                    "max_attempts": self.settings.max_login_attempts,
                },
            )

        if user.blocked_until and user.blocked_until <= now:
            user.blocked_until = None
        
        # Verify password
        if not verify_password(request.password, user.password_hash):
            await self._record_login_attempt(
                email=email,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                user_id=user.id,
                failure_reason="invalid_password",
            )

            failed_attempts = await self._count_recent_failed_password_attempts(email)
            remaining_attempts = max(self.settings.max_login_attempts - failed_attempts, 0)

            if remaining_attempts <= 0:
                lockout_until = datetime.now(UTC) + timedelta(minutes=self.settings.lockout_duration_minutes)
                user.blocked_until = lockout_until

                await self._record_login_attempt(
                    email=email,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    user_id=user.id,
                    failure_reason="account_locked",
                    locked_applied=True,
                )

                await self.session.commit()

                remaining_seconds = self._remaining_seconds(lockout_until)
                raise AccountLockedException(
                    unlock_time=lockout_until.isoformat(),
                    retry_after=remaining_seconds,
                    details={
                        "lockout_until": lockout_until.isoformat(),
                        "remaining_seconds": remaining_seconds,
                        "max_attempts": self.settings.max_login_attempts,
                        "remaining_attempts": 0,
                    },
                )

            await self.session.commit()

            logger.warning("Login attempt with invalid password", user_id=user.id, email=email)
            raise InvalidCredentialsException(
                message=f"Contraseña incorrecta. Te quedan {remaining_attempts} intentos.",
                details={
                    "remaining_attempts": remaining_attempts,
                    "max_attempts": self.settings.max_login_attempts,
                },
            )

        # Successful login clears stale block marker and records attempt.
        await self._record_login_attempt(
            email=email,
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
            user_id=user.id,
            failure_reason=None,
        )
        
        # Clear failed login attempts counter after successful login
        await self._clear_failed_login_attempts(email)
        
        # Check if 2FA is enabled
        if user.two_factor_enabled:
            # Generate and send OTP code for login
            from ...modules.two_factor.service import TwoFactorService
            two_factor_service = TwoFactorService(self.session)
            await two_factor_service.generate_login_otp(user.email)
            
            # Return partial response indicating 2FA is required
            return user, UnifiedTokenResponse(
                access_token="",
                refresh_token="",
                expires_in=0,
                user_type=user.user_type,
                requires_2fa=True,
            )
        
        # Generate tokens
        access_token, expires_at, jti = create_access_token(
            subject=str(user.id),
            email=user.email,
            user_type=user.user_type,
        )
        
        refresh_token, refresh_token_hash = create_refresh_token()
        
        # Save refresh token
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        
        self.session.add(refresh_token_record)
        await self.session.commit()
        
        # Update last login
        await self.user_repo.update_last_login(user.id)
        
        # If user is a technician, update online status and broadcast
        if user.user_type == UserType.TECHNICIAN:
            try:
                from ..real_time.services import RealTimeService
                from sqlalchemy import update as sql_update
                
                # Update technician online status
                await self.session.execute(
                    sql_update(Technician)
                    .where(Technician.id == user.id)
                    .values(
                        is_online=True,
                        last_seen_at=datetime.now(UTC)
                    )
                )
                await self.session.commit()
                
                # Broadcast online status to workshop
                real_time_service = RealTimeService(self.session)
                await real_time_service.broadcast_technician_status_change(
                    technician_id=user.id,
                    is_online=True,
                    last_seen_at=datetime.now(UTC)
                )
            except Exception as e:
                logger.error(f"Error broadcasting technician online status: {str(e)}")
        
        logger.info("User logged in successfully", user_id=user.id, email=email)
        
        token_response = UnifiedTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=30 * 60,  # 30 minutes
            user_type=user.user_type,
            requires_2fa=False,
        )
        
        return user, token_response
    
    async def complete_2fa_login(self, email: str) -> tuple[User, UnifiedTokenResponse]:
        """
        Complete login after 2FA verification.
        
        Args:
            email: User email
            
        Returns:
            Tuple of (user, token_response)
            
        Raises:
            UserNotFoundException: If user doesn't exist
        """
        # Find user by email
        user = await self.user_repo.find_active_by_email(email)
        if not user:
            raise UserNotFoundException(f"Usuario con email {email}")
        
        # Generate tokens
        access_token, expires_at, jti = create_access_token(
            subject=str(user.id),
            email=user.email,
            user_type=user.user_type,
        )
        
        refresh_token, refresh_token_hash = create_refresh_token()
        
        # Save refresh token
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        
        self.session.add(refresh_token_record)
        await self.session.commit()
        
        # Update last login
        await self.user_repo.update_last_login(user.id)
        
        # Clear failed login attempts counter after successful 2FA login
        await self._clear_failed_login_attempts(email)
        
        # If user is a technician, update online status and broadcast
        if user.user_type == UserType.TECHNICIAN:
            try:
                from ..real_time.services import RealTimeService
                from sqlalchemy import update as sql_update
                
                # Update technician online status
                await self.session.execute(
                    sql_update(Technician)
                    .where(Technician.id == user.id)
                    .values(
                        is_online=True,
                        last_seen_at=datetime.now(UTC)
                    )
                )
                await self.session.commit()
                
                # Broadcast online status to workshop
                real_time_service = RealTimeService(self.session)
                await real_time_service.broadcast_technician_status_change(
                    technician_id=user.id,
                    is_online=True,
                    last_seen_at=datetime.now(UTC)
                )
            except Exception as e:
                logger.error(f"Error broadcasting technician online status: {str(e)}")
        
        logger.info("User logged in successfully with 2FA", user_id=user.id, email=email)
        
        token_response = UnifiedTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=30 * 60,  # 30 minutes
            user_type=user.user_type,
            requires_2fa=False,
        )
        
        return user, token_response
    
    async def logout(self, user_id: int, refresh_token: str | None = None) -> None:
        """
        Logout user by revoking tokens.
        
        Args:
            user_id: User ID
            refresh_token: Refresh token to revoke (optional, revokes all if None)
        """
        if refresh_token:
            # Revoke specific refresh token
            # This would need to be implemented in the token repository
            pass
        else:
            # Revoke all user tokens
            await self.token_repo.revoke_all_user_tokens(user_id)
        
        logger.info("User logged out", user_id=user_id)


class ProfileService:
    """Service for user profile management."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
    
    async def get_profile(self, user_id: int) -> User:
        """
        Get user profile.
        
        Args:
            user_id: User ID
            
        Returns:
            User profile
        """
        return await self.user_repo.find_by_id_or_raise(user_id)
    
    async def update_profile(
        self, 
        user_id: int, 
        request: UpdateProfileRequest
    ) -> User:
        """
        Update user profile.
        
        Args:
            user_id: User ID
            request: Update request data
            
        Returns:
            Updated user
        """
        from sqlalchemy import select
        from ...models.client import Client
        from ...models.workshop import Workshop
        from ...models.technician import Technician
        
        # Get current user
        user = await self.user_repo.find_by_id_or_raise(user_id)
        
        # Update common fields on User table
        user_update_data = {}
        if request.first_name is not None:
            user_update_data["first_name"] = request.first_name
        if request.last_name is not None:
            user_update_data["last_name"] = request.last_name
        if request.phone is not None:
            user_update_data["phone"] = request.phone
        
        # Update user common fields
        if user_update_data:
            for key, value in user_update_data.items():
                setattr(user, key, value)
        
        # Update type-specific fields
        if user.user_type == UserType.CLIENT:
            result = await self.session.execute(select(Client).where(Client.id == user_id))
            client = result.scalar_one_or_none()
            if client:
                if request.direccion is not None:
                    client.direccion = request.direccion
                if request.ci is not None:
                    client.ci = request.ci
                if request.fecha_nacimiento is not None:
                    client.fecha_nacimiento = request.fecha_nacimiento
        
        elif user.user_type == UserType.WORKSHOP:
            result = await self.session.execute(select(Workshop).where(Workshop.id == user_id))
            workshop = result.scalar_one_or_none()
            if workshop:
                if request.workshop_name is not None:
                    workshop.workshop_name = request.workshop_name
                if request.owner_name is not None:
                    workshop.owner_name = request.owner_name
                if request.latitude is not None:
                    workshop.latitude = request.latitude
                if request.longitude is not None:
                    workshop.longitude = request.longitude
                if request.coverage_radius_km is not None:
                    workshop.coverage_radius_km = request.coverage_radius_km
        
        elif user.user_type == UserType.TECHNICIAN:
            result = await self.session.execute(select(Technician).where(Technician.id == user_id))
            technician = result.scalar_one_or_none()
            if technician:
                if request.current_latitude is not None:
                    technician.current_latitude = request.current_latitude
                if request.current_longitude is not None:
                    technician.current_longitude = request.current_longitude
                if request.is_available is not None:
                    technician.is_available = request.is_available
        
        # Commit changes
        await self.session.commit()
        await self.session.refresh(user)
        
        logger.info("User profile updated", user_id=user_id)
        return user
    
    async def delete_account(self, user_id: int, password: str) -> None:
        """
        Delete user account after password verification.
        
        Args:
            user_id: User ID
            password: Current password for verification
            
        Raises:
            InvalidCredentialsException: If password is incorrect
        """
        # Get user
        user = await self.user_repo.find_by_id_or_raise(user_id)
        
        # Verify password
        if not verify_password(password, user.password_hash):
            logger.warning("Account deletion attempt with invalid password", user_id=user_id)
            raise InvalidCredentialsException()
        
        # Deactivate account (soft delete)
        await self.user_repo.deactivate_user(user_id)
        
        # Revoke all tokens
        await self.token_repo.revoke_all_user_tokens(user_id)
        
        logger.info("User account deleted", user_id=user_id, email=user.email)