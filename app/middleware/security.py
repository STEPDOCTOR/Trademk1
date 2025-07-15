"""Security middleware for IP filtering, DDoS protection, and request validation."""

import asyncio
import logging
import time
from typing import Set, Optional, List, Dict, Any
from datetime import datetime, timedelta
from ipaddress import ip_address, ip_network, AddressValueError

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.cache import cache_service

logger = logging.getLogger(__name__)


class SecurityConfig:
    """Security configuration."""
    
    def __init__(self):
        # IP filtering
        self.blocked_ips: Set[str] = set()
        self.allowed_ips: Set[str] = set()  # If not empty, only these IPs are allowed
        self.blocked_networks: List[str] = []
        
        # DDoS protection
        self.max_requests_per_second = 10
        self.max_concurrent_requests_per_ip = 5
        self.ddos_detection_window = 60  # seconds
        self.ddos_threshold = 100  # requests per window
        self.ddos_ban_duration = 300  # seconds
        
        # Request validation
        self.max_request_size = 10 * 1024 * 1024  # 10MB
        self.max_header_size = 8192  # 8KB
        self.max_url_length = 2048
        
        # Security headers
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }


class IPFilter:
    """IP address filtering and blocking."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        
    def is_ip_allowed(self, ip: str) -> bool:
        """Check if IP is allowed."""
        try:
            client_ip = ip_address(ip)
            
            # Check if IP is explicitly blocked
            if ip in self.config.blocked_ips:
                return False
                
            # Check blocked networks
            for network in self.config.blocked_networks:
                try:
                    if client_ip in ip_network(network, strict=False):
                        return False
                except AddressValueError:
                    continue
                    
            # If allow list is configured, only allow those IPs
            if self.config.allowed_ips:
                return ip in self.config.allowed_ips
                
            return True
            
        except AddressValueError:
            # Invalid IP address
            return False
            
    async def is_ip_banned(self, ip: str) -> bool:
        """Check if IP is temporarily banned."""
        try:
            await cache_service.connect()
            ban_key = f"security:banned_ip:{ip}"
            return await cache_service.exists(ban_key)
        except Exception:
            return False
            
    async def ban_ip(self, ip: str, duration: int = 300, reason: str = "DDoS"):
        """Temporarily ban an IP address."""
        try:
            await cache_service.connect()
            ban_key = f"security:banned_ip:{ip}"
            await cache_service.set(ban_key, reason, expire=duration)
            logger.warning(f"IP {ip} banned for {duration}s: {reason}")
        except Exception as e:
            logger.error(f"Failed to ban IP {ip}: {e}")


class DDoSProtection:
    """DDoS detection and protection."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.ip_filter = IPFilter(config)
        
    async def check_request_rate(self, ip: str) -> bool:
        """Check if request rate is suspicious."""
        try:
            await cache_service.connect()
            
            current_time = int(time.time())
            window_start = current_time - self.config.ddos_detection_window
            
            # Track requests in sliding window
            rate_key = f"security:ddos_rate:{ip}"
            
            # Remove old entries
            await cache_service.client.zremrangebyscore(rate_key, 0, window_start)
            
            # Count current requests
            request_count = await cache_service.client.zcard(rate_key)
            
            if request_count >= self.config.ddos_threshold:
                # Ban the IP
                await self.ip_filter.ban_ip(
                    ip, 
                    self.config.ddos_ban_duration, 
                    f"DDoS: {request_count} requests in {self.config.ddos_detection_window}s"
                )
                return False
                
            # Add current request
            await cache_service.client.zadd(rate_key, {str(current_time): current_time})
            await cache_service.client.expire(rate_key, self.config.ddos_detection_window)
            
            return True
            
        except Exception as e:
            logger.error(f"DDoS check failed for {ip}: {e}")
            return True  # Fail open
            
    async def check_concurrent_requests(self, ip: str) -> bool:
        """Check concurrent requests from IP."""
        try:
            await cache_service.connect()
            
            concurrent_key = f"security:concurrent:{ip}"
            current_count = await cache_service.get(concurrent_key) or 0
            
            if isinstance(current_count, str):
                current_count = int(current_count)
                
            return current_count < self.config.max_concurrent_requests_per_ip
            
        except Exception as e:
            logger.error(f"Concurrent request check failed for {ip}: {e}")
            return True  # Fail open
            
    async def increment_concurrent_requests(self, ip: str):
        """Increment concurrent request counter."""
        try:
            await cache_service.connect()
            concurrent_key = f"security:concurrent:{ip}"
            await cache_service.increment(concurrent_key)
            await cache_service.expire(concurrent_key, 30)  # 30 second timeout
        except Exception as e:
            logger.error(f"Failed to increment concurrent requests for {ip}: {e}")
            
    async def decrement_concurrent_requests(self, ip: str):
        """Decrement concurrent request counter."""
        try:
            await cache_service.connect()
            concurrent_key = f"security:concurrent:{ip}"
            current = await cache_service.get(concurrent_key)
            if current and int(current) > 0:
                await cache_service.decrement(concurrent_key)
        except Exception as e:
            logger.error(f"Failed to decrement concurrent requests for {ip}: {e}")


class RequestValidator:
    """Validate incoming requests for security issues."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        
    def validate_request_size(self, request: Request) -> bool:
        """Validate request size."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                return size <= self.config.max_request_size
            except ValueError:
                return False
        return True
        
    def validate_headers(self, request: Request) -> bool:
        """Validate request headers."""
        # Check total header size
        total_header_size = sum(
            len(f"{k}: {v}") for k, v in request.headers.items()
        )
        
        if total_header_size > self.config.max_header_size:
            return False
            
        # Check for suspicious headers
        suspicious_patterns = [
            "script",
            "javascript:",
            "vbscript:",
            "onload=",
            "onerror=",
            "<script",
            "</script>",
        ]
        
        for header_value in request.headers.values():
            header_lower = header_value.lower()
            if any(pattern in header_lower for pattern in suspicious_patterns):
                return False
                
        return True
        
    def validate_url(self, request: Request) -> bool:
        """Validate URL length and content."""
        url = str(request.url)
        
        # Check URL length
        if len(url) > self.config.max_url_length:
            return False
            
        # Check for path traversal attempts
        suspicious_patterns = [
            "../",
            "..\\",
            "%2e%2e%2f",
            "%2e%2e%5c",
            "..%2f",
            "..%5c",
        ]
        
        url_lower = url.lower()
        if any(pattern in url_lower for pattern in suspicious_patterns):
            return False
            
        return True


class SecurityMiddleware(BaseHTTPMiddleware):
    """Comprehensive security middleware."""
    
    def __init__(self, app, config: Optional[SecurityConfig] = None):
        super().__init__(app)
        self.config = config or SecurityConfig()
        self.ip_filter = IPFilter(self.config)
        self.ddos_protection = DDoSProtection(self.config)
        self.request_validator = RequestValidator(self.config)
        
    async def dispatch(self, request: Request, call_next):
        """Process request with security checks."""
        client_ip = self._get_client_ip(request)
        
        # Store IP in request state for other middleware
        request.state.client_ip = client_ip
        
        try:
            # IP filtering
            if not self.ip_filter.is_ip_allowed(client_ip):
                logger.warning(f"Blocked IP access: {client_ip}")
                return self._security_error("Access denied")
                
            # Check if IP is banned
            if await self.ip_filter.is_ip_banned(client_ip):
                logger.warning(f"Banned IP access attempt: {client_ip}")
                return self._security_error("Access temporarily blocked")
                
            # DDoS protection
            if not await self.ddos_protection.check_request_rate(client_ip):
                return self._security_error("Request rate exceeded")
                
            if not await self.ddos_protection.check_concurrent_requests(client_ip):
                logger.warning(f"Too many concurrent requests from {client_ip}")
                return self._security_error("Too many concurrent requests")
                
            # Request validation
            if not self.request_validator.validate_request_size(request):
                logger.warning(f"Request too large from {client_ip}")
                return self._security_error("Request too large")
                
            if not self.request_validator.validate_headers(request):
                logger.warning(f"Suspicious headers from {client_ip}")
                return self._security_error("Invalid request headers")
                
            if not self.request_validator.validate_url(request):
                logger.warning(f"Suspicious URL from {client_ip}")
                return self._security_error("Invalid request URL")
                
            # Increment concurrent request counter
            await self.ddos_protection.increment_concurrent_requests(client_ip)
            
            # Process request
            response = await call_next(request)
            
            # Add security headers
            for header, value in self.config.security_headers.items():
                response.headers[header] = value
                
            return response
            
        except Exception as e:
            logger.error(f"Security middleware error for {client_ip}: {e}")
            return self._security_error("Internal security error")
            
        finally:
            # Decrement concurrent request counter
            await self.ddos_protection.decrement_concurrent_requests(client_ip)
            
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address."""
        # Check for forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
            
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
            
        # Fall back to client host
        return request.client.host if request.client else "unknown"
        
    def _security_error(self, message: str) -> JSONResponse:
        """Return security error response."""
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Security violation", "message": message}
        )


# Utility functions for manual IP management
class SecurityManager:
    """Manage security settings and IP lists."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.ip_filter = IPFilter(config)
        
    async def block_ip(self, ip: str, permanent: bool = False, reason: str = "Manual block"):
        """Block an IP address."""
        if permanent:
            self.config.blocked_ips.add(ip)
            logger.info(f"Permanently blocked IP: {ip} - {reason}")
        else:
            await self.ip_filter.ban_ip(ip, duration=3600, reason=reason)
            logger.info(f"Temporarily blocked IP: {ip} - {reason}")
            
    async def unblock_ip(self, ip: str):
        """Unblock an IP address."""
        # Remove from permanent block list
        self.config.blocked_ips.discard(ip)
        
        # Remove from temporary ban
        try:
            await cache_service.connect()
            ban_key = f"security:banned_ip:{ip}"
            await cache_service.delete(ban_key)
            logger.info(f"Unblocked IP: {ip}")
        except Exception as e:
            logger.error(f"Failed to unblock IP {ip}: {e}")
            
    def allow_ip(self, ip: str):
        """Add IP to allow list."""
        self.config.allowed_ips.add(ip)
        logger.info(f"Added IP to allow list: {ip}")
        
    def remove_allowed_ip(self, ip: str):
        """Remove IP from allow list."""
        self.config.allowed_ips.discard(ip)
        logger.info(f"Removed IP from allow list: {ip}")
        
    async def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics."""
        try:
            await cache_service.connect()
            
            # Count banned IPs
            banned_ips = []
            cursor = 0
            while True:
                cursor, keys = await cache_service.client.scan(
                    cursor, match="security:banned_ip:*", count=100
                )
                banned_ips.extend(keys)
                if cursor == 0:
                    break
                    
            return {
                "blocked_ips_count": len(self.config.blocked_ips),
                "allowed_ips_count": len(self.config.allowed_ips),
                "temporarily_banned_count": len(banned_ips),
                "blocked_networks_count": len(self.config.blocked_networks),
                "blocked_ips": list(self.config.blocked_ips),
                "allowed_ips": list(self.config.allowed_ips),
                "temporarily_banned": [key.split(":")[-1] for key in banned_ips]
            }
            
        except Exception as e:
            logger.error(f"Failed to get security stats: {e}")
            return {}