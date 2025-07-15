"""API Key management endpoints."""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, AuthUser
from app.auth.security import generate_api_key, get_password_hash, verify_api_key_format
from app.db.postgres import get_db
from app.models.api_key import APIKey
from app.services.audit_logger import AuditLogger

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


# Request/Response models
class APIKeyCreate(BaseModel):
    """API key creation request."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    scopes: List[str] = Field(default=["read:market_data"])
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=600)
    rate_limit_per_hour: int = Field(default=3600, ge=1, le=36000)
    allowed_ips: Optional[List[str]] = None


class APIKeyResponse(BaseModel):
    """API key response (without sensitive data)."""
    id: str
    name: str
    description: Optional[str]
    scopes: List[str]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    allowed_ips: Optional[List[str]]


class APIKeyCreateResponse(BaseModel):
    """API key creation response (includes key only once)."""
    api_key: str
    key_info: APIKeyResponse


class APIKeyUpdate(BaseModel):
    """API key update request."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=600)
    rate_limit_per_hour: Optional[int] = Field(None, ge=1, le=36000)
    allowed_ips: Optional[List[str]] = None


# Available scopes
AVAILABLE_SCOPES = [
    "read:market_data",
    "read:portfolio",
    "read:orders",
    "write:orders",
    "read:strategies",
    "write:strategies",
    "manage:api_keys"
]

audit_logger = AuditLogger()


@router.post("/", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: APIKeyCreate,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new API key."""
    # Validate scopes
    invalid_scopes = [s for s in key_data.scopes if s not in AVAILABLE_SCOPES]
    if invalid_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scopes: {', '.join(invalid_scopes)}"
        )
    
    # Generate API key
    api_key = generate_api_key()
    
    # Calculate expiration
    expires_at = None
    if key_data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=key_data.expires_in_days)
    
    # Create API key record
    api_key_record = APIKey(
        id=uuid4(),
        user_id=current_user.user_id,
        name=key_data.name,
        key_hash=get_password_hash(api_key),  # Hash the API key like a password
        scopes=",".join(key_data.scopes),
        description=key_data.description,
        expires_at=expires_at,
        rate_limit_per_minute=str(key_data.rate_limit_per_minute),
        rate_limit_per_hour=str(key_data.rate_limit_per_hour),
        allowed_ips=",".join(key_data.allowed_ips) if key_data.allowed_ips else None,
        is_active=True
    )
    
    db.add(api_key_record)
    await db.commit()
    await db.refresh(api_key_record)
    
    # Log API key creation
    await audit_logger.log_api_key_event(
        db=db,
        user_id=current_user.user_id,
        api_key_id=str(api_key_record.id),
        action="create",
        description=f"Created API key: {key_data.name}",
        request=request
    )
    await db.commit()
    
    # Return the API key (only shown once)
    return APIKeyCreateResponse(
        api_key=api_key,
        key_info=APIKeyResponse(
            id=str(api_key_record.id),
            name=api_key_record.name,
            description=api_key_record.description,
            scopes=api_key_record.scopes.split(","),
            is_active=api_key_record.is_active,
            created_at=api_key_record.created_at,
            last_used_at=api_key_record.last_used_at,
            expires_at=api_key_record.expires_at,
            rate_limit_per_minute=int(api_key_record.rate_limit_per_minute),
            rate_limit_per_hour=int(api_key_record.rate_limit_per_hour),
            allowed_ips=api_key_record.allowed_ips.split(",") if api_key_record.allowed_ips else None
        )
    )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all API keys for the current user."""
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == current_user.user_id)
    )
    api_keys = result.scalars().all()
    
    return [
        APIKeyResponse(
            id=str(key.id),
            name=key.name,
            description=key.description,
            scopes=key.scopes.split(","),
            is_active=key.is_active,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            expires_at=key.expires_at,
            rate_limit_per_minute=int(key.rate_limit_per_minute),
            rate_limit_per_hour=int(key.rate_limit_per_hour),
            allowed_ips=key.allowed_ips.split(",") if key.allowed_ips else None
        )
        for key in api_keys
    ]


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific API key."""
    result = await db.execute(
        select(APIKey).where(
            and_(
                APIKey.id == key_id,
                APIKey.user_id == current_user.user_id
            )
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return APIKeyResponse(
        id=str(api_key.id),
        name=api_key.name,
        description=api_key.description,
        scopes=api_key.scopes.split(","),
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
        rate_limit_per_minute=int(api_key.rate_limit_per_minute),
        rate_limit_per_hour=int(api_key.rate_limit_per_hour),
        allowed_ips=api_key.allowed_ips.split(",") if api_key.allowed_ips else None
    )


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: str,
    update_data: APIKeyUpdate,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an API key."""
    result = await db.execute(
        select(APIKey).where(
            and_(
                APIKey.id == key_id,
                APIKey.user_id == current_user.user_id
            )
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Update fields
    if update_data.name is not None:
        api_key.name = update_data.name
    if update_data.description is not None:
        api_key.description = update_data.description
    if update_data.is_active is not None:
        api_key.is_active = update_data.is_active
    if update_data.rate_limit_per_minute is not None:
        api_key.rate_limit_per_minute = str(update_data.rate_limit_per_minute)
    if update_data.rate_limit_per_hour is not None:
        api_key.rate_limit_per_hour = str(update_data.rate_limit_per_hour)
    if update_data.allowed_ips is not None:
        api_key.allowed_ips = ",".join(update_data.allowed_ips) if update_data.allowed_ips else None
    
    await db.commit()
    await db.refresh(api_key)
    
    # Log update
    await audit_logger.log_api_key_event(
        db=db,
        user_id=current_user.user_id,
        api_key_id=str(api_key.id),
        action="update",
        description=f"Updated API key: {api_key.name}",
        request=request
    )
    await db.commit()
    
    return APIKeyResponse(
        id=str(api_key.id),
        name=api_key.name,
        description=api_key.description,
        scopes=api_key.scopes.split(","),
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
        rate_limit_per_minute=int(api_key.rate_limit_per_minute),
        rate_limit_per_hour=int(api_key.rate_limit_per_hour),
        allowed_ips=api_key.allowed_ips.split(",") if api_key.allowed_ips else None
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: str,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an API key."""
    result = await db.execute(
        select(APIKey).where(
            and_(
                APIKey.id == key_id,
                APIKey.user_id == current_user.user_id
            )
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Log deletion
    await audit_logger.log_api_key_event(
        db=db,
        user_id=current_user.user_id,
        api_key_id=str(api_key.id),
        action="delete",
        description=f"Deleted API key: {api_key.name}",
        request=request
    )
    
    await db.delete(api_key)
    await db.commit()