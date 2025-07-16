"""Authentication API endpoints."""
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, AuthUser
from app.auth.security import (
    verify_password, get_password_hash, create_access_token,
    create_refresh_token, decode_token, create_email_verification_token,
    verify_email_verification_token, create_password_reset_token,
    verify_password_reset_token
)
from app.db.postgres import get_db
from app.models.user import User
from app.models.user_portfolio import UserPortfolio, UserPreferences
from app.services.audit_logger import AuditLogger

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


# Request/Response models
class UserCreate(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=50)
    
    @validator('password')
    def validate_password(cls, v):
        """Ensure password meets security requirements."""
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        return v


class UserResponse(BaseModel):
    """User response model."""
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime
    last_login_at: Optional[datetime]


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # 30 minutes


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str


class PasswordResetRequest(BaseModel):
    """Password reset request."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)


# Audit logger
audit_logger = AuditLogger()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    user = User(
        id=uuid4(),
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        phone_number=user_data.phone_number,
        is_active=True,
        is_verified=False,
        is_superuser=False
    )
    db.add(user)
    
    # Create user portfolio
    portfolio = UserPortfolio(
        id=uuid4(),
        user_id=user.id,
        total_value=0.0,
        cash_balance=0.0,
        positions_value=0.0,
        strategy_allocations={}
    )
    db.add(portfolio)
    
    # Create user preferences
    preferences = UserPreferences(
        id=uuid4(),
        user_id=user.id,
        default_order_type="market",
        default_time_in_force="day",
        risk_level="medium",
        email_notifications=True,
        theme="light",
        timezone="UTC",
        language="en",
        currency="USD"
    )
    db.add(preferences)
    
    await db.commit()
    await db.refresh(user)
    
    # Log registration
    await audit_logger.log_event(
        db=db,
        user_id=user.id,
        event_type="user_registered",
        event_category="auth",
        action="create",
        resource_type="user",
        resource_id=str(user.id),
        description=f"New user registered: {user.email}",
        request=request
    )
    
    # TODO: Send verification email
    # verification_token = create_email_verification_token(user.email)
    # await send_verification_email(user.email, verification_token)
    
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        last_login_at=user.last_login_at
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password."""
    # Find user
    result = await db.execute(
        select(User).where(User.email == form_data.username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        await audit_logger.log_event(
            db=db,
            user_id=None,
            event_type="login_failed",
            event_category="auth",
            event_severity="warning",
            action="authenticate",
            description=f"Failed login attempt for: {form_data.username}",
            request=request
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    await db.commit()
    
    # Create tokens
    access_token = create_access_token(
        subject=str(user.id),
        additional_claims={
            "email": user.email,
            "is_superuser": user.is_superuser
        }
    )
    refresh_token = create_refresh_token(subject=str(user.id))
    
    # Log successful login
    await audit_logger.log_event(
        db=db,
        user_id=user.id,
        event_type="login_success",
        event_category="auth",
        action="authenticate",
        resource_type="user",
        resource_id=str(user.id),
        description=f"User logged in: {user.email}",
        request=request
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    token_request: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token."""
    try:
        payload = decode_token(token_request.refresh_token)
        
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")
            
        user_id = payload.get("sub")
        
        # Get user
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise ValueError("Invalid user")
            
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Create new tokens
    access_token = create_access_token(
        subject=str(user.id),
        additional_claims={
            "email": user.email,
            "is_superuser": user.is_superuser
        }
    )
    new_refresh_token = create_refresh_token(subject=str(user.id))
    
    # Log token refresh
    await audit_logger.log_event(
        db=db,
        user_id=user.id,
        event_type="token_refreshed",
        event_category="auth",
        action="refresh",
        description="Access token refreshed",
        request=request
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user information."""
    result = await db.execute(
        select(User).where(User.id == current_user.user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        last_login_at=user.last_login_at
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Logout current user."""
    # In a real implementation, we might want to:
    # 1. Add the token to a blacklist in Redis
    # 2. Clear any server-side sessions
    
    await audit_logger.log_event(
        db=db,
        user_id=current_user.user_id,
        event_type="logout",
        event_category="auth",
        action="logout",
        description="User logged out",
        request=request
    )
    
    return MessageResponse(message="Successfully logged out")


@router.post("/verify-email/{token}", response_model=MessageResponse)
async def verify_email(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Verify email address using verification token."""
    email = verify_email_verification_token(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    # Update user
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_verified:
        return MessageResponse(message="Email already verified")
    
    user.is_verified = True
    user.verified_at = datetime.utcnow()
    await db.commit()
    
    await audit_logger.log_event(
        db=db,
        user_id=user.id,
        event_type="email_verified",
        event_category="auth",
        action="verify",
        description=f"Email verified for: {user.email}",
        request=request
    )
    
    return MessageResponse(message="Email verified successfully")


@router.post("/request-password-reset", response_model=MessageResponse)
async def request_password_reset(
    email: EmailStr,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Request password reset email."""
    # Check if user exists
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    
    # Always return success to prevent email enumeration
    if user:
        reset_token = create_password_reset_token(email)
        # TODO: Send password reset email
        # await send_password_reset_email(email, reset_token)
        
        await audit_logger.log_event(
            db=db,
            user_id=user.id,
            event_type="password_reset_requested",
            event_category="auth",
            action="request",
            description=f"Password reset requested for: {email}",
            request=request
        )
    
    return MessageResponse(
        message="If the email exists, a password reset link has been sent"
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: Request,
    reset_data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reset password using reset token."""
    email = verify_password_reset_token(reset_data.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Update password
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.password_hash = get_password_hash(reset_data.new_password)
    await db.commit()
    
    await audit_logger.log_event(
        db=db,
        user_id=user.id,
        event_type="password_reset",
        event_category="auth",
        event_severity="warning",
        action="update",
        description="Password reset successfully",
        request=request
    )
    
    return MessageResponse(message="Password reset successfully")