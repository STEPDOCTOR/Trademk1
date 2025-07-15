"""Comprehensive API documentation with OpenAPI enhancements."""

from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.api.versioning import get_api_version_info, get_version_migration_guide
from app.config.settings import get_settings

router = APIRouter(prefix="/api/docs", tags=["documentation"])


class APIDocumentationInfo(BaseModel):
    """API documentation information."""
    title: str
    version: str
    description: str
    terms_of_service: Optional[str]
    contact: Dict[str, Any]
    license: Dict[str, Any]
    servers: List[Dict[str, str]]


class EndpointDocumentation(BaseModel):
    """Endpoint documentation."""
    path: str
    method: str
    summary: str
    description: str
    tags: List[str]
    parameters: List[Dict[str, Any]]
    request_body: Optional[Dict[str, Any]]
    responses: Dict[str, Dict[str, Any]]
    examples: List[Dict[str, Any]]


def get_enhanced_openapi_schema(app) -> Dict[str, Any]:
    """Get enhanced OpenAPI schema with additional documentation."""
    
    settings = get_settings()
    
    # Get base OpenAPI schema
    openapi_schema = get_openapi(
        title="Trademk1 Trading Platform API",
        version="1.0.0",
        description="""
# Trademk1 Trading Platform API

A comprehensive real-time trading platform for U.S. stocks and top-15 cryptocurrencies.

## Features

- **Real-time Market Data**: Live price feeds and market data streaming
- **Order Management**: Advanced order types with real-time execution
- **Portfolio Analytics**: Comprehensive performance metrics and risk analysis  
- **Strategy Framework**: Algorithmic trading strategies with backtesting
- **User Management**: Authentication, preferences, and notification system
- **WebSocket Streaming**: Real-time updates for orders, positions, and market data
- **Admin Tools**: System monitoring, performance metrics, and security management

## Authentication

The API supports multiple authentication methods:

1. **JWT Tokens**: For user authentication with refresh token support
2. **API Keys**: For programmatic access with scoped permissions
3. **Session-based**: For web application integration

## Rate Limiting

API requests are rate-limited based on user tier:

- **Free Tier**: 30 requests/minute, 1,800 requests/hour
- **Basic Tier**: 60 requests/minute, 3,600 requests/hour  
- **Premium Tier**: 120 requests/minute, 7,200 requests/hour
- **Enterprise Tier**: 300 requests/minute, 18,000 requests/hour

## WebSocket Streaming

Real-time data is available via WebSocket connections:

- **Endpoint**: `wss://api.trademk1.com/ws/stream`
- **Authentication**: JWT token as query parameter
- **Channels**: market data, orders, positions, portfolio, notifications

## Error Handling

The API uses standard HTTP status codes and returns detailed error information:

```json
{
  "error": "error_type",
  "message": "Human readable error message",
  "details": {
    "field": "Additional error details"
  },
  "request_id": "unique_request_identifier"
}
```

## Versioning

The API supports versioning through URL paths (e.g., `/api/v1/endpoint`).
Version migration guides are available in the documentation.
        """,
        routes=app.routes,
        servers=[
            {"url": "https://api.trademk1.com", "description": "Production server"},
            {"url": "https://staging-api.trademk1.com", "description": "Staging server"},
            {"url": "http://localhost:8000", "description": "Development server"}
        ]
    )
    
    # Add custom extensions
    openapi_schema["info"]["contact"] = {
        "name": "Trademk1 API Support",
        "url": "https://trademk1.com/support",
        "email": "api-support@trademk1.com"
    }
    
    openapi_schema["info"]["license"] = {
        "name": "Proprietary",
        "url": "https://trademk1.com/license"
    }
    
    openapi_schema["info"]["termsOfService"] = "https://trademk1.com/terms"
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token obtained from /api/v1/auth/login"
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key obtained from user dashboard"
        }
    }
    
    # Add global security
    openapi_schema["security"] = [
        {"BearerAuth": []},
        {"ApiKeyAuth": []}
    ]
    
    # Add custom extensions
    openapi_schema["x-api-version"] = "1.0.0"
    openapi_schema["x-rate-limits"] = {
        "free": {"requests_per_minute": 30, "requests_per_hour": 1800},
        "basic": {"requests_per_minute": 60, "requests_per_hour": 3600},
        "premium": {"requests_per_minute": 120, "requests_per_hour": 7200},
        "enterprise": {"requests_per_minute": 300, "requests_per_hour": 18000}
    }
    
    # Add example responses for common errors
    error_responses = {
        "400": {
            "description": "Bad Request",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string", "example": "validation_error"},
                            "message": {"type": "string", "example": "Invalid request data"},
                            "details": {"type": "object"}
                        }
                    }
                }
            }
        },
        "401": {
            "description": "Unauthorized",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string", "example": "unauthorized"},
                            "message": {"type": "string", "example": "Invalid or expired token"}
                        }
                    }
                }
            }
        },
        "403": {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string", "example": "forbidden"},
                            "message": {"type": "string", "example": "Insufficient permissions"}
                        }
                    }
                }
            }
        },
        "429": {
            "description": "Too Many Requests",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string", "example": "rate_limit_exceeded"},
                            "message": {"type": "string", "example": "Rate limit exceeded"},
                            "retry_after": {"type": "integer", "example": 60}
                        }
                    }
                }
            }
        },
        "500": {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string", "example": "internal_error"},
                            "message": {"type": "string", "example": "An unexpected error occurred"}
                        }
                    }
                }
            }
        }
    }
    
    # Add common error responses to all endpoints
    for path_data in openapi_schema["paths"].values():
        for operation in path_data.values():
            if isinstance(operation, dict) and "responses" in operation:
                operation["responses"].update(error_responses)
    
    return openapi_schema


@router.get("/openapi.json", response_class=JSONResponse)
async def get_openapi_json(request: Request):
    """Get OpenAPI JSON schema."""
    app = request.app
    openapi_schema = get_enhanced_openapi_schema(app)
    return JSONResponse(content=openapi_schema)


@router.get("/", response_class=HTMLResponse)
async def get_documentation():
    """Get interactive API documentation."""
    return get_swagger_ui_html(
        openapi_url="/api/docs/openapi.json",
        title="Trademk1 API Documentation",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css",
        swagger_ui_parameters={
            "deepLinking": True,
            "displayRequestDuration": True,
            "docExpansion": "none",
            "filter": True,
            "showExtensions": True,
            "showCommonExtensions": True,
            "tryItOutEnabled": True
        }
    )


@router.get("/info", response_model=APIDocumentationInfo)
async def get_api_info():
    """Get API information."""
    settings = get_settings()
    
    return APIDocumentationInfo(
        title="Trademk1 Trading Platform API",
        version="1.0.0",
        description="Comprehensive real-time trading platform API",
        terms_of_service="https://trademk1.com/terms",
        contact={
            "name": "Trademk1 API Support",
            "url": "https://trademk1.com/support",
            "email": "api-support@trademk1.com"
        },
        license={
            "name": "Proprietary",
            "url": "https://trademk1.com/license"
        },
        servers=[
            {"url": "https://api.trademk1.com", "description": "Production server"},
            {"url": "https://staging-api.trademk1.com", "description": "Staging server"},
            {"url": "http://localhost:8000", "description": "Development server"}
        ]
    )


@router.get("/versions")
async def get_version_info():
    """Get API version information."""
    return get_api_version_info()


@router.get("/migration-guide")
async def get_migration_guide():
    """Get version migration guide."""
    return get_version_migration_guide()


@router.get("/examples")
async def get_api_examples():
    """Get API usage examples."""
    
    return {
        "authentication": {
            "login": {
                "description": "Authenticate and get JWT tokens",
                "request": {
                    "method": "POST",
                    "url": "/api/v1/auth/login",
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "username": "user@example.com",
                        "password": "your_password"
                    }
                },
                "response": {
                    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                    "token_type": "bearer",
                    "expires_in": 1800
                }
            },
            "api_key": {
                "description": "Create API key for programmatic access",
                "request": {
                    "method": "POST",
                    "url": "/api/v1/api-keys",
                    "headers": {
                        "Authorization": "Bearer your_jwt_token",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "Trading Bot",
                        "scopes": ["read:market_data", "write:orders"],
                        "expires_in_days": 30
                    }
                }
            }
        },
        "market_data": {
            "latest_price": {
                "description": "Get latest price for a symbol",
                "request": {
                    "method": "GET",
                    "url": "/api/v1/market-data/latest/AAPL",
                    "headers": {"Authorization": "Bearer your_jwt_token"}
                },
                "response": {
                    "symbol": "AAPL",
                    "price": 150.25,
                    "bid": 150.20,
                    "ask": 150.30,
                    "volume": 1000000,
                    "timestamp": "2024-01-15T14:30:00Z"
                }
            },
            "websocket": {
                "description": "Connect to real-time market data stream",
                "connection": "wss://api.trademk1.com/ws/stream?token=your_jwt_token",
                "subscribe": {
                    "type": "subscribe",
                    "channel": "market:AAPL"
                },
                "message": {
                    "type": "market_data",
                    "channel": "market:AAPL",
                    "data": {
                        "symbol": "AAPL",
                        "price": 150.30,
                        "timestamp": "2024-01-15T14:30:15Z"
                    }
                }
            }
        },
        "trading": {
            "place_order": {
                "description": "Place a market order",
                "request": {
                    "method": "POST",
                    "url": "/api/v1/trading/orders",
                    "headers": {
                        "Authorization": "Bearer your_jwt_token",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "symbol": "AAPL",
                        "side": "buy",
                        "order_type": "market",
                        "quantity": 100,
                        "time_in_force": "day"
                    }
                },
                "response": {
                    "id": "order_123456",
                    "symbol": "AAPL",
                    "side": "buy",
                    "status": "pending",
                    "created_at": "2024-01-15T14:30:00Z"
                }
            }
        },
        "portfolio": {
            "summary": {
                "description": "Get portfolio summary",
                "request": {
                    "method": "GET",
                    "url": "/api/v1/portfolio/summary",
                    "headers": {"Authorization": "Bearer your_jwt_token"}
                },
                "response": {
                    "current_value": 50000.00,
                    "daily_change": 250.00,
                    "daily_change_percentage": 0.5,
                    "total_return": 5000.00,
                    "total_return_percentage": 11.11,
                    "positions_count": 5
                }
            }
        }
    }


@router.get("/status")
async def get_api_status():
    """Get API status and health information."""
    
    return {
        "status": "operational",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": "99.9%",
        "services": {
            "authentication": "operational",
            "market_data": "operational",
            "trading": "operational",
            "websocket": "operational",
            "database": "operational",
            "cache": "operational"
        },
        "rate_limits": {
            "remaining": 1000,
            "reset_time": "2024-01-15T15:00:00Z"
        }
    }


@router.get("/changelog")
async def get_api_changelog():
    """Get API changelog."""
    
    return {
        "v1.0.0": {
            "release_date": "2024-01-15",
            "changes": [
                "Initial API release",
                "Authentication with JWT tokens",
                "Market data endpoints",
                "Order management system",
                "Portfolio analytics",
                "WebSocket streaming",
                "Admin tools and monitoring"
            ]
        }
    }


# Custom HTML template for enhanced documentation
DOCUMENTATION_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Trademk1 API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css" />
    <style>
        .swagger-ui .topbar { display: none; }
        .swagger-ui .info .title { color: #2c3e50; }
        .swagger-ui .scheme-container { background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 8px; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/api/docs/openapi.json',
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.presets.standalone
            ],
            plugins: [
                SwaggerUIBundle.plugins.DownloadUrl
            ],
            layout: "StandaloneLayout",
            tryItOutEnabled: true,
            filter: true,
            showExtensions: true,
            showCommonExtensions: true,
            displayRequestDuration: true,
            docExpansion: "none"
        });
    </script>
</body>
</html>
"""


@router.get("/enhanced", response_class=HTMLResponse)
async def get_enhanced_documentation():
    """Get enhanced API documentation with custom styling."""
    return HTMLResponse(content=DOCUMENTATION_HTML)