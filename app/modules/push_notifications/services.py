"""
Push notification service using Firebase Cloud Messaging (FCM).
"""
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel

from ...core.logging import get_logger
from ...core.config import get_settings
from ...models.push_token import PushToken
from ...models.notification import Notification
from ...models.user import User

logger = get_logger(__name__)
settings = get_settings()


class PushNotificationData(BaseModel):
    """Data structure for push notifications."""
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None
    image_url: Optional[str] = None
    click_action: Optional[str] = None
    sound: str = "default"
    badge: Optional[int] = None


class PushNotificationService:
    """
    Service for sending push notifications via Firebase Cloud Messaging.
    
    Handles:
    - FCM token management
    - Push notification sending
    - Batch notifications
    - Error handling and token cleanup
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._firebase_app = None
        self._initialize_firebase()

    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK."""
        try:
            # Check if Firebase is already initialized
            if firebase_admin._apps:
                self._firebase_app = firebase_admin.get_app()
                logger.info("Using existing Firebase app")
                return

            # Path to Firebase service account key
            service_account_path = Path(settings.firebase_service_account_path)
            
            if not service_account_path.exists():
                logger.info(f"Firebase service account file not found: {service_account_path}")
                logger.info("Push notifications will be disabled")
                return

            # Initialize Firebase
            cred = credentials.Certificate(str(service_account_path))
            self._firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            logger.warning("Push notifications will be disabled")

    def is_enabled(self) -> bool:
        """Check if push notifications are enabled."""
        return self._firebase_app is not None

    async def register_token(
        self,
        user_id: int,
        token: str,
        platform: str,
        device_id: Optional[str] = None
    ) -> bool:
        """
        Register or update FCM token for a user.
        
        Args:
            user_id: ID of the user
            token: FCM token
            platform: Platform (android, ios, web)
            device_id: Unique device identifier
            
        Returns:
            True if token was registered successfully
        """
        try:
            # Check if token already exists for any user
            existing_token = await self.session.scalar(
                select(PushToken).where(PushToken.token == token)
            )

            if existing_token:
                # Update existing token with new user_id and info
                await self.session.execute(
                    update(PushToken)
                    .where(PushToken.id == existing_token.id)
                    .values(
                        user_id=user_id,  # Update user_id in case token moved to different user
                        platform=platform,
                        device_id=device_id,
                        is_active=True,
                        updated_at=datetime.utcnow()
                    )
                )
                logger.info(f"Updated existing FCM token for user {user_id}")
            else:
                # Create new token
                push_token = PushToken(
                    user_id=user_id,
                    token=token,
                    platform=platform,
                    device_id=device_id,
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                self.session.add(push_token)
                logger.info(f"Registered new FCM token for user {user_id}")

            await self.session.commit()
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error registering FCM token: {str(e)}")
            return False

    async def unregister_token(self, user_id: int, token: str) -> bool:
        """
        Unregister FCM token for a user.
        
        Args:
            user_id: ID of the user
            token: FCM token to unregister
            
        Returns:
            True if token was unregistered successfully
        """
        try:
            await self.session.execute(
                update(PushToken)
                .where(
                    PushToken.user_id == user_id,
                    PushToken.token == token
                )
                .values(is_active=False, updated_at=datetime.utcnow())
            )
            
            await self.session.commit()
            logger.info(f"Unregistered FCM token for user {user_id}")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error unregistering FCM token: {str(e)}")
            return False

    async def unregister_all_user_tokens(self, user_id: int) -> bool:
        """
        Unregister all FCM tokens for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            True if tokens were unregistered successfully
        """
        try:
            await self.session.execute(
                update(PushToken)
                .where(PushToken.user_id == user_id)
                .values(is_active=False, updated_at=datetime.utcnow())
            )
            
            await self.session.commit()
            logger.info(f"Unregistered all FCM tokens for user {user_id}")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error unregistering all user tokens: {str(e)}")
            return False

    async def get_user_tokens(self, user_id: int) -> List[str]:
        """
        Get all active FCM tokens for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of active FCM tokens
        """
        try:
            tokens = await self.session.scalars(
                select(PushToken.token).where(
                    PushToken.user_id == user_id,
                    PushToken.is_active == True
                )
            )
            return list(tokens)

        except Exception as e:
            logger.error(f"Error getting user tokens: {str(e)}")
            return []

    async def send_to_user(
        self,
        user_id: int,
        notification_data: PushNotificationData,
        save_to_db: bool = True
    ) -> bool:
        """
        Send push notification to a specific user.
        
        Args:
            user_id: ID of the user
            notification_data: Notification data
            save_to_db: Whether to save notification to database
            
        Returns:
            True if notification was sent successfully
        """
        if not self.is_enabled():
            logger.warning("Push notifications are disabled")
            return False

        try:
            # Get user's FCM tokens
            tokens = await self.get_user_tokens(user_id)
            
            if not tokens:
                logger.info(f"No FCM tokens found for user {user_id}")
                return False

            # Send notification
            success = await self._send_to_tokens(tokens, notification_data)

            # Save to database if requested
            if save_to_db and success:
                await self._save_notification_to_db(user_id, notification_data)

            return success

        except Exception as e:
            logger.error(f"Error sending push notification to user {user_id}: {str(e)}")
            return False

    async def send_to_multiple_users(
        self,
        user_ids: List[int],
        notification_data: PushNotificationData,
        save_to_db: bool = True
    ) -> Dict[int, bool]:
        """
        Send push notification to multiple users.
        
        Args:
            user_ids: List of user IDs
            notification_data: Notification data
            save_to_db: Whether to save notifications to database
            
        Returns:
            Dictionary mapping user_id to success status
        """
        results = {}
        
        for user_id in user_ids:
            results[user_id] = await self.send_to_user(
                user_id, notification_data, save_to_db
            )
        
        return results

    async def _send_to_tokens(
        self,
        tokens: List[str],
        notification_data: PushNotificationData
    ) -> bool:
        """
        Send notification to specific FCM tokens.
        
        Args:
            tokens: List of FCM tokens
            notification_data: Notification data
            
        Returns:
            True if at least one notification was sent successfully
        """
        if not tokens:
            return False

        try:
            # FCM requires all data values to be strings
            str_data: dict[str, str] = {
                k: str(v) for k, v in (notification_data.data or {}).items() if v is not None
            }

            # Create FCM message
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=notification_data.title,
                    body=notification_data.body,
                    image=notification_data.image_url
                ),
                data=str_data,
                android=messaging.AndroidConfig(
                    notification=messaging.AndroidNotification(
                        sound=notification_data.sound,
                        click_action=notification_data.click_action
                    )
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound=notification_data.sound,
                            badge=notification_data.badge
                        )
                    )
                ),
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        title=notification_data.title,
                        body=notification_data.body,
                        icon='/assets/icons/icon-192x192.png',
                        badge='/assets/icons/icon-72x72.png',
                        require_interaction=True,
                    )
                    # Note: fcm_options.link removed - not needed for web push
                    # Web apps should handle navigation via service worker using notification.data
                ),
                tokens=tokens
            )

            # Send message
            response = messaging.send_each_for_multicast(message)
            
            # Log results
            logger.info(f"Push notification sent: {response.success_count}/{len(tokens)} successful")
            
            # Handle failed tokens
            if response.failure_count > 0:
                await self._handle_failed_tokens(tokens, response.responses)

            return response.success_count > 0

        except Exception as e:
            logger.error(f"Error sending FCM message: {str(e)}")
            return False

    async def _handle_failed_tokens(
        self,
        tokens: List[str],
        responses: List[messaging.SendResponse]
    ):
        """
        Handle failed FCM tokens by deactivating invalid ones.
        
        Args:
            tokens: List of FCM tokens
            responses: List of send responses
        """
        try:
            invalid_tokens = []
            
            for i, response in enumerate(responses):
                if not response.success:
                    error_code = response.exception.code if response.exception else None
                    
                    # Deactivate tokens with permanent errors
                    if error_code in ['INVALID_ARGUMENT', 'NOT_FOUND', 'UNREGISTERED']:
                        invalid_tokens.append(tokens[i])
                        logger.warning(f"Deactivating invalid FCM token: {error_code}")

            # Deactivate invalid tokens in database
            if invalid_tokens:
                await self.session.execute(
                    update(PushToken)
                    .where(PushToken.token.in_(invalid_tokens))
                    .values(is_active=False, updated_at=datetime.utcnow())
                )
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error handling failed tokens: {str(e)}")

    async def _save_notification_to_db(
        self,
        user_id: int,
        notification_data: PushNotificationData
    ):
        """
        Save notification to database for history.
        
        Args:
            user_id: ID of the user
            notification_data: Notification data
        """
        try:
            import json
            
            notification = Notification(
                user_id=user_id,
                type="push_notification",
                title=notification_data.title,
                message=notification_data.body,
                data_json=json.dumps(notification_data.data or {}),  # Convertir dict a JSON string
                created_at=datetime.utcnow()
            )
            
            self.session.add(notification)
            await self.session.commit()

        except Exception as e:
            logger.error(f"Error saving notification to database: {str(e)}")

    async def send_incident_notification(
        self,
        user_id: int,
        incident_id: int,
        notification_type: str,
        title: str,
        body: str,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send incident-related push notification.
        
        Args:
            user_id: ID of the user
            incident_id: ID of the incident
            notification_type: Type of notification
            title: Notification title
            body: Notification body
            additional_data: Additional data to include
            
        Returns:
            True if notification was sent successfully
        """
        data = {
            "type": notification_type,
            "incident_id": str(incident_id),
            "click_action": f"/incidents/{incident_id}"
        }
        
        if additional_data:
            data.update(additional_data)

        notification_data = PushNotificationData(
            title=title,
            body=body,
            data=data,
            click_action=None  # Set to None for web push (use data.click_action for mobile)
        )

        return await self.send_to_user(user_id, notification_data)

    async def cleanup_expired_tokens(self, days: int = 30) -> int:
        """
        Clean up expired or inactive tokens.
        
        Args:
            days: Number of days to consider tokens as expired
            
        Returns:
            Number of tokens cleaned up
        """
        try:
            from datetime import timedelta
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            result = await self.session.execute(
                update(PushToken)
                .where(PushToken.updated_at < cutoff_date)
                .values(is_active=False)
            )
            
            await self.session.commit()
            
            cleaned_count = result.rowcount
            logger.info(f"Cleaned up {cleaned_count} expired FCM tokens")
            
            return cleaned_count

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error cleaning up expired tokens: {str(e)}")
            return 0