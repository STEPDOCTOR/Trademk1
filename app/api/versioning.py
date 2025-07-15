"""API versioning and backward compatibility utilities."""

import re
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum

from fastapi import Request, HTTPException, status
from fastapi.routing import APIRoute
from pydantic import BaseModel


class APIVersion(str, Enum):
    """Supported API versions."""
    V1 = "v1"
    V2 = "v2"  # Future version


@dataclass
class VersionedEndpoint:
    """Versioned endpoint configuration."""
    path: str
    method: str
    handler: Callable
    min_version: APIVersion
    max_version: Optional[APIVersion] = None
    deprecated_in: Optional[APIVersion] = None
    removed_in: Optional[APIVersion] = None


class VersioningStrategy(str, Enum):
    """API versioning strategies."""
    URL_PATH = "url_path"  # /api/v1/endpoint
    HEADER = "header"      # X-API-Version: v1
    QUERY_PARAM = "query"  # ?version=v1
    ACCEPT_HEADER = "accept"  # Accept: application/vnd.api+json;version=1


class APIVersionManager:
    """Manages API versioning and backward compatibility."""
    
    def __init__(
        self,
        default_version: APIVersion = APIVersion.V1,
        strategy: VersioningStrategy = VersioningStrategy.URL_PATH,
        header_name: str = "X-API-Version",
        query_param_name: str = "version"
    ):
        self.default_version = default_version
        self.strategy = strategy
        self.header_name = header_name
        self.query_param_name = query_param_name
        self.endpoints: List[VersionedEndpoint] = []
        
    def extract_version_from_request(self, request: Request) -> APIVersion:
        """Extract API version from request."""
        
        if self.strategy == VersioningStrategy.URL_PATH:
            # Extract from URL path like /api/v1/endpoint
            path = request.url.path
            version_match = re.search(r'/v(\d+)/', path)
            if version_match:
                version_num = version_match.group(1)
                try:
                    return APIVersion(f"v{version_num}")
                except ValueError:
                    pass
                    
        elif self.strategy == VersioningStrategy.HEADER:
            # Extract from custom header
            version = request.headers.get(self.header_name)
            if version:
                try:
                    return APIVersion(version.lower())
                except ValueError:
                    pass
                    
        elif self.strategy == VersioningStrategy.QUERY_PARAM:
            # Extract from query parameter
            version = request.query_params.get(self.query_param_name)
            if version:
                try:
                    return APIVersion(version.lower())
                except ValueError:
                    pass
                    
        elif self.strategy == VersioningStrategy.ACCEPT_HEADER:
            # Extract from Accept header like application/vnd.api+json;version=1
            accept = request.headers.get("accept", "")
            version_match = re.search(r'version=(\d+)', accept)
            if version_match:
                version_num = version_match.group(1)
                try:
                    return APIVersion(f"v{version_num}")
                except ValueError:
                    pass
                    
        return self.default_version
        
    def is_version_supported(
        self,
        version: APIVersion,
        endpoint: VersionedEndpoint
    ) -> bool:
        """Check if version is supported for endpoint."""
        
        # Check minimum version
        if version < endpoint.min_version:
            return False
            
        # Check maximum version
        if endpoint.max_version and version > endpoint.max_version:
            return False
            
        # Check if removed
        if endpoint.removed_in and version >= endpoint.removed_in:
            return False
            
        return True
        
    def is_version_deprecated(
        self,
        version: APIVersion,
        endpoint: VersionedEndpoint
    ) -> bool:
        """Check if version is deprecated for endpoint."""
        
        return (
            endpoint.deprecated_in and 
            version >= endpoint.deprecated_in and
            (not endpoint.removed_in or version < endpoint.removed_in)
        )
        
    def get_deprecation_warning(
        self,
        version: APIVersion,
        endpoint: VersionedEndpoint
    ) -> Optional[str]:
        """Get deprecation warning message."""
        
        if not self.is_version_deprecated(version, endpoint):
            return None
            
        warning = f"API version {version} for {endpoint.method} {endpoint.path} is deprecated"
        
        if endpoint.removed_in:
            warning += f" and will be removed in version {endpoint.removed_in}"
            
        return warning


class BackwardCompatibilityManager:
    """Manages backward compatibility transformations."""
    
    def __init__(self):
        self.request_transformers: Dict[str, List[Callable]] = {}
        self.response_transformers: Dict[str, List[Callable]] = {}
        
    def add_request_transformer(
        self,
        from_version: APIVersion,
        to_version: APIVersion,
        transformer: Callable[[Dict[str, Any]], Dict[str, Any]]
    ):
        """Add request transformer for version compatibility."""
        key = f"{from_version}_to_{to_version}"
        if key not in self.request_transformers:
            self.request_transformers[key] = []
        self.request_transformers[key].append(transformer)
        
    def add_response_transformer(
        self,
        from_version: APIVersion,
        to_version: APIVersion,
        transformer: Callable[[Dict[str, Any]], Dict[str, Any]]
    ):
        """Add response transformer for version compatibility."""
        key = f"{from_version}_to_{to_version}"
        if key not in self.response_transformers:
            self.response_transformers[key] = []
        self.response_transformers[key].append(transformer)
        
    def transform_request(
        self,
        data: Dict[str, Any],
        from_version: APIVersion,
        to_version: APIVersion
    ) -> Dict[str, Any]:
        """Transform request data for compatibility."""
        key = f"{from_version}_to_{to_version}"
        transformers = self.request_transformers.get(key, [])
        
        for transformer in transformers:
            data = transformer(data)
            
        return data
        
    def transform_response(
        self,
        data: Dict[str, Any],
        from_version: APIVersion,
        to_version: APIVersion
    ) -> Dict[str, Any]:
        """Transform response data for compatibility."""
        key = f"{from_version}_to_{to_version}"
        transformers = self.response_transformers.get(key, [])
        
        for transformer in transformers:
            data = transformer(data)
            
        return data


# Global instances
version_manager = APIVersionManager()
compatibility_manager = BackwardCompatibilityManager()


# Common transformers for v1 -> v2 compatibility (examples)
def transform_user_response_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform user response from v1 to v2 format."""
    # Example: v2 adds a new field and renames another
    if "email" in data:
        data["email_address"] = data.pop("email")
    
    data["api_version"] = "v2"
    return data


def transform_order_request_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform order request from v1 to v2 format."""
    # Example: v2 uses different field names
    if "qty" in data:
        data["quantity"] = data.pop("qty")
        
    if "type" in data:
        data["order_type"] = data.pop("type")
        
    return data


# Register transformers
compatibility_manager.add_response_transformer(
    APIVersion.V1, APIVersion.V2, transform_user_response_v1_to_v2
)
compatibility_manager.add_request_transformer(
    APIVersion.V1, APIVersion.V2, transform_order_request_v1_to_v2
)


class VersionedAPIRoute(APIRoute):
    """Custom API route that handles versioning."""
    
    def __init__(
        self,
        *args,
        min_version: APIVersion = APIVersion.V1,
        max_version: Optional[APIVersion] = None,
        deprecated_in: Optional[APIVersion] = None,
        removed_in: Optional[APIVersion] = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.min_version = min_version
        self.max_version = max_version
        self.deprecated_in = deprecated_in
        self.removed_in = removed_in
        
        # Register endpoint
        version_manager.endpoints.append(VersionedEndpoint(
            path=self.path,
            method=list(self.methods)[0] if self.methods else "GET",
            handler=self.endpoint,
            min_version=min_version,
            max_version=max_version,
            deprecated_in=deprecated_in,
            removed_in=removed_in
        ))


def versioned_route(
    path: str,
    *,
    min_version: APIVersion = APIVersion.V1,
    max_version: Optional[APIVersion] = None,
    deprecated_in: Optional[APIVersion] = None,
    removed_in: Optional[APIVersion] = None,
    **kwargs
):
    """Decorator for versioned routes."""
    def decorator(func):
        return VersionedAPIRoute(
            path=path,
            endpoint=func,
            min_version=min_version,
            max_version=max_version,
            deprecated_in=deprecated_in,
            removed_in=removed_in,
            **kwargs
        )
    return decorator


# Middleware for version checking
async def check_api_version(request: Request, call_next):
    """Middleware to check API version compatibility."""
    
    # Extract version from request
    requested_version = version_manager.extract_version_from_request(request)
    
    # Store version in request state
    request.state.api_version = requested_version
    
    # Find matching endpoint
    path = request.url.path
    method = request.method
    
    matching_endpoint = None
    for endpoint in version_manager.endpoints:
        if endpoint.path in path and endpoint.method.upper() == method.upper():
            matching_endpoint = endpoint
            break
            
    if matching_endpoint:
        # Check if version is supported
        if not version_manager.is_version_supported(requested_version, matching_endpoint):
            if matching_endpoint.removed_in and requested_version >= matching_endpoint.removed_in:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail=f"API version {requested_version} is no longer supported for this endpoint"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"API version {requested_version} is not supported for this endpoint"
                )
                
        # Check for deprecation
        if version_manager.is_version_deprecated(requested_version, matching_endpoint):
            warning = version_manager.get_deprecation_warning(requested_version, matching_endpoint)
            request.state.deprecation_warning = warning
    
    # Continue with request
    response = await call_next(request)
    
    # Add version headers
    response.headers["X-API-Version"] = requested_version
    response.headers["X-Supported-Versions"] = ",".join([v.value for v in APIVersion])
    
    # Add deprecation warning if applicable
    if hasattr(request.state, "deprecation_warning"):
        response.headers["Warning"] = f'299 - "{request.state.deprecation_warning}"'
        response.headers["Sunset"] = "Sun, 01 Jan 2025 00:00:00 GMT"  # Example sunset date
    
    return response


# Utility functions for API documentation
def get_api_version_info() -> Dict[str, Any]:
    """Get API version information for documentation."""
    
    return {
        "current_version": version_manager.default_version.value,
        "supported_versions": [v.value for v in APIVersion],
        "versioning_strategy": version_manager.strategy.value,
        "endpoints": [
            {
                "path": ep.path,
                "method": ep.method,
                "min_version": ep.min_version.value,
                "max_version": ep.max_version.value if ep.max_version else None,
                "deprecated_in": ep.deprecated_in.value if ep.deprecated_in else None,
                "removed_in": ep.removed_in.value if ep.removed_in else None
            }
            for ep in version_manager.endpoints
        ]
    }


def get_version_migration_guide() -> Dict[str, Any]:
    """Get version migration guide."""
    
    return {
        "v1_to_v2": {
            "breaking_changes": [
                "User 'email' field renamed to 'email_address'",
                "Order 'qty' field renamed to 'quantity'",
                "Order 'type' field renamed to 'order_type'"
            ],
            "new_features": [
                "Enhanced portfolio analytics",
                "Real-time WebSocket streaming",
                "Advanced risk management"
            ],
            "deprecated_features": [
                "Legacy order status format",
                "Old authentication endpoints"
            ]
        }
    }