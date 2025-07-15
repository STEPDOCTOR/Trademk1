"""Authentication dependencies for FastAPI."""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_token
from app.db.postgres import get_db
from app.models.user import User

# Security schemes
bearer_scheme = HTTPBearer()


class AuthUser:
    """Authenticated user information."""
    def __init__(
        self,
        user_id: UUID,
        email: str,
        is_active: bool,
        is_superuser: bool,
        roles: List[str],
        permissions: List[str]
    ):
        self.user_id = user_id
        self.email = email
        self.is_active = is_active
        self.is_superuser = is_superuser
        self.roles = roles
        self.permissions = permissions
        
    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission."""
        return self.is_superuser or permission in self.permissions
        
    def has_role(self, role: str) -> bool:
        """Check if user has specific role."""
        return self.is_superuser or role in self.roles


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db)
) -> AuthUser:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    
    try:
        payload = decode_token(token)
        
        # Check token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Get user from database
    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
        
    # Get user roles and permissions (simplified for now)
    roles = ["user"]
    permissions = ["read:own_data", "write:own_data"]
    
    if user.is_superuser:
        roles.append("admin")
        permissions.extend(["read:all_data", "write:all_data", "manage:users"])
        
    return AuthUser(
        user_id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        roles=roles,
        permissions=permissions
    )


async def get_current_active_user(
    current_user: AuthUser = Depends(get_current_user)
) -> AuthUser:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_superuser(
    current_user: AuthUser = Depends(get_current_active_user)
) -> AuthUser:
    """Get current superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions"
        )
    return current_user


class RoleChecker:
    """Dependency to check user roles."""
    
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles
        
    async def __call__(
        self,
        user: AuthUser = Depends(get_current_active_user)
    ) -> AuthUser:
        if not any(user.has_role(role) for role in self.allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role privileges"
            )
        return user


class PermissionChecker:
    """Dependency to check user permissions."""
    
    def __init__(self, required_permissions: List[str]):
        self.required_permissions = required_permissions
        
    async def __call__(
        self,
        user: AuthUser = Depends(get_current_active_user)
    ) -> AuthUser:
        for permission in self.required_permissions:
            if not user.has_permission(permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {permission}"
                )
        return user


# Convenience dependencies
require_admin = RoleChecker(["admin"])
require_trader = RoleChecker(["trader", "admin"])


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> Optional[AuthUser]:
    """Get current user if authenticated, otherwise None."""
    if not credentials:
        return None
        
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None