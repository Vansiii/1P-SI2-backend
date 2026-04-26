"""
Push notification API endpoints.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from ...core.database import get_db_session
from ...shared.dependencies.auth import get_current_user
from .services import PushNotificationService, PushNotificationData
from ...models.user import User

router = APIRouter()


class RegisterTokenRequest(BaseModel):
    """Request for registering FCM token."""
    token: str = Field(..., min_length=1, description="FCM token")
    platform: str = Field(..., description="Platform: android, ios, web")
    device_id: Optional[str] = Field(None, description="Unique device identifier")


class UnregisterTokenRequest(BaseModel):
    """Request for unregistering FCM token."""
    token: str = Field(..., min_length=1, description="FCM token to unregister")


class SendNotificationRequest(BaseModel):
    """Request for sending push notification."""
    title: str = Field(..., min_length=1, max_length=100, description="Notification title")
    body: str = Field(..., min_length=1, max_length=500, description="Notification body")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional data")
    image_url: Optional[str] = Field(None, description="Image URL")
    click_action: Optional[str] = Field(None, description="Click action URL")


class TestNotificationRequest(BaseModel):
    """Request for sending test notification."""
    message: str = Field(default="Test notification from MecánicoYa", description="Test message")


@router.post("/tokens/register")
async def register_fcm_token(
    request: RegisterTokenRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Register FCM token for push notifications.
    
    This endpoint allows users to register their device tokens
    to receive push notifications.
    """
    push_service = PushNotificationService(session)
    
    success = await push_service.register_token(
        user_id=current_user.id,
        token=request.token,
        platform=request.platform,
        device_id=request.device_id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error registering FCM token"
        )
    
    return {
        "message": "FCM token registered successfully",
        "user_id": current_user.id,
        "platform": request.platform
    }


@router.delete("/tokens/unregister")
async def unregister_fcm_token(
    request: UnregisterTokenRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Unregister FCM token.
    
    This endpoint allows users to unregister their device tokens
    when they no longer want to receive push notifications.
    """
    push_service = PushNotificationService(session)
    
    success = await push_service.unregister_token(
        user_id=current_user.id,
        token=request.token
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error unregistering FCM token"
        )
    
    return {
        "message": "FCM token unregistered successfully",
        "user_id": current_user.id
    }


@router.delete("/tokens/unregister-all")
async def unregister_all_user_tokens(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Unregister all FCM tokens for current user.
    
    Useful for logout to disable all notifications for the user.
    """
    push_service = PushNotificationService(session)
    
    success = await push_service.unregister_all_user_tokens(current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error unregistering user tokens"
        )
    
    return {
        "message": "All FCM tokens unregistered successfully",
        "user_id": current_user.id
    }


@router.get("/tokens")
async def get_user_tokens(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get user's registered FCM tokens.
    
    This endpoint returns all active FCM tokens for the current user.
    """
    push_service = PushNotificationService(session)
    
    tokens = await push_service.get_user_tokens(current_user.id)
    
    return {
        "message": "FCM tokens retrieved successfully",
        "user_id": current_user.id,
        "tokens": tokens,
        "token_count": len(tokens)
    }


@router.post("/send")
async def send_push_notification(
    request: SendNotificationRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Send push notification to current user.
    
    This endpoint allows users to send test notifications to themselves.
    Useful for testing push notification functionality.
    """
    push_service = PushNotificationService(session)
    
    if not push_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not enabled"
        )
    
    notification_data = PushNotificationData(
        title=request.title,
        body=request.body,
        data=request.data,
        image_url=request.image_url,
        click_action=request.click_action
    )
    
    success = await push_service.send_to_user(
        user_id=current_user.id,
        notification_data=notification_data,
        save_to_db=True
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending push notification"
        )
    
    return {
        "message": "Push notification sent successfully",
        "user_id": current_user.id,
        "title": request.title,
        "body": request.body
    }


@router.post("/test")
async def send_test_notification(
    request: TestNotificationRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Send test push notification to current user.
    
    This endpoint sends a simple test notification to verify
    that push notifications are working correctly.
    """
    push_service = PushNotificationService(session)
    
    if not push_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not enabled"
        )
    
    notification_data = PushNotificationData(
        title="🧪 Test Notification",
        body=request.message,
        data={
            "type": "test",
            "timestamp": str(int(datetime.utcnow().timestamp()))
        }
    )
    
    success = await push_service.send_to_user(
        user_id=current_user.id,
        notification_data=notification_data,
        save_to_db=False  # Don't save test notifications
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending test notification"
        )
    
    return {
        "message": "Test notification sent successfully",
        "user_id": current_user.id,
        "test_message": request.message
    }


@router.get("/status")
async def get_push_notification_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get push notification service status.
    
    This endpoint provides information about the push notification
    service status and user's token registration.
    """
    push_service = PushNotificationService(session)
    
    tokens = await push_service.get_user_tokens(current_user.id)
    
    return {
        "service_enabled": push_service.is_enabled(),
        "user_id": current_user.id,
        "registered_tokens": len(tokens),
        "has_tokens": len(tokens) > 0,
        "firebase_initialized": push_service._firebase_app is not None
    }


@router.delete("/tokens/cleanup")
async def cleanup_expired_tokens(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Clean up expired FCM tokens.
    
    This endpoint removes expired or inactive tokens from the database.
    Only administrators should have access to this endpoint in production.
    """
    # Note: In production, this should be restricted to administrators
    # For now, allowing any authenticated user for testing
    
    push_service = PushNotificationService(session)
    
    cleaned_count = await push_service.cleanup_expired_tokens(days=30)
    
    return {
        "message": "Token cleanup completed",
        "cleaned_tokens": cleaned_count
    }