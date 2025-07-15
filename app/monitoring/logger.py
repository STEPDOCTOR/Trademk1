"""Comprehensive logging configuration with structured logging and monitoring."""

import json
import logging
import logging.config
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from pythonjsonlogger import jsonlogger


class StructuredFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""
    
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp
        log_record['timestamp'] = datetime.utcnow().isoformat()
        
        # Add service info
        log_record['service'] = 'trademk1'
        log_record['version'] = '0.1.0'
        
        # Add request context if available
        if hasattr(record, 'request_id'):
            log_record['request_id'] = record.request_id
        if hasattr(record, 'user_id'):
            log_record['user_id'] = record.user_id
        if hasattr(record, 'correlation_id'):
            log_record['correlation_id'] = record.correlation_id
            
        # Add performance metrics if available
        if hasattr(record, 'duration'):
            log_record['duration'] = record.duration
        if hasattr(record, 'status_code'):
            log_record['status_code'] = record.status_code


class PerformanceLogger:
    """Logger for performance metrics."""
    
    def __init__(self, logger_name: str = "performance"):
        self.logger = logging.getLogger(logger_name)
        
    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        **extra_fields
    ):
        """Log request performance metrics."""
        extra = {
            'event_type': 'request',
            'method': method,
            'path': path,
            'status_code': status_code,
            'duration': duration,
            'user_id': user_id,
            'request_id': request_id,
            **extra_fields
        }
        
        # Determine log level based on performance
        if duration > 5.0:
            level = logging.ERROR
            message = f"Very slow request: {method} {path} took {duration:.2f}s"
        elif duration > 2.0:
            level = logging.WARNING
            message = f"Slow request: {method} {path} took {duration:.2f}s"
        elif duration > 1.0:
            level = logging.INFO
            message = f"Request: {method} {path} took {duration:.2f}s"
        else:
            level = logging.DEBUG
            message = f"Request: {method} {path} took {duration:.2f}s"
            
        self.logger.log(level, message, extra=extra)
        
    def log_database_query(
        self,
        query: str,
        duration: float,
        rows_affected: Optional[int] = None,
        **extra_fields
    ):
        """Log database query performance."""
        extra = {
            'event_type': 'database_query',
            'query': query[:200] + '...' if len(query) > 200 else query,
            'duration': duration,
            'rows_affected': rows_affected,
            **extra_fields
        }
        
        if duration > 1.0:
            level = logging.WARNING
            message = f"Slow database query took {duration:.2f}s"
        else:
            level = logging.DEBUG
            message = f"Database query took {duration:.2f}s"
            
        self.logger.log(level, message, extra=extra)
        
    def log_cache_operation(
        self,
        operation: str,
        key: str,
        hit: bool,
        duration: float,
        **extra_fields
    ):
        """Log cache operation performance."""
        extra = {
            'event_type': 'cache_operation',
            'operation': operation,
            'key': key,
            'cache_hit': hit,
            'duration': duration,
            **extra_fields
        }
        
        message = f"Cache {operation} {'hit' if hit else 'miss'} for {key} took {duration:.3f}s"
        self.logger.debug(message, extra=extra)


class SecurityLogger:
    """Logger for security events."""
    
    def __init__(self, logger_name: str = "security"):
        self.logger = logging.getLogger(logger_name)
        
    def log_authentication_attempt(
        self,
        email: str,
        success: bool,
        ip_address: str,
        user_agent: Optional[str] = None,
        **extra_fields
    ):
        """Log authentication attempts."""
        extra = {
            'event_type': 'authentication',
            'email': email,
            'success': success,
            'ip_address': ip_address,
            'user_agent': user_agent,
            **extra_fields
        }
        
        if success:
            message = f"Successful login for {email} from {ip_address}"
            level = logging.INFO
        else:
            message = f"Failed login attempt for {email} from {ip_address}"
            level = logging.WARNING
            
        self.logger.log(level, message, extra=extra)
        
    def log_rate_limit_violation(
        self,
        ip_address: str,
        path: str,
        user_id: Optional[str] = None,
        **extra_fields
    ):
        """Log rate limit violations."""
        extra = {
            'event_type': 'rate_limit_violation',
            'ip_address': ip_address,
            'path': path,
            'user_id': user_id,
            **extra_fields
        }
        
        message = f"Rate limit exceeded by {ip_address} for {path}"
        self.logger.warning(message, extra=extra)
        
    def log_security_violation(
        self,
        violation_type: str,
        ip_address: str,
        details: str,
        severity: str = "medium",
        **extra_fields
    ):
        """Log security violations."""
        extra = {
            'event_type': 'security_violation',
            'violation_type': violation_type,
            'ip_address': ip_address,
            'severity': severity,
            'details': details,
            **extra_fields
        }
        
        level_map = {
            'low': logging.INFO,
            'medium': logging.WARNING,
            'high': logging.ERROR,
            'critical': logging.CRITICAL
        }
        
        level = level_map.get(severity, logging.WARNING)
        message = f"Security violation ({violation_type}): {details}"
        self.logger.log(level, message, extra=extra)


class BusinessLogger:
    """Logger for business events."""
    
    def __init__(self, logger_name: str = "business"):
        self.logger = logging.getLogger(logger_name)
        
    def log_trade_execution(
        self,
        user_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_id: str,
        **extra_fields
    ):
        """Log trade executions."""
        extra = {
            'event_type': 'trade_execution',
            'user_id': user_id,
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'order_id': order_id,
            'trade_value': quantity * price,
            **extra_fields
        }
        
        message = f"Trade executed: {side} {quantity} {symbol} @ {price} for user {user_id}"
        self.logger.info(message, extra=extra)
        
    def log_strategy_signal(
        self,
        strategy_id: str,
        symbol: str,
        signal_type: str,
        confidence: float,
        user_id: Optional[str] = None,
        **extra_fields
    ):
        """Log strategy signals."""
        extra = {
            'event_type': 'strategy_signal',
            'strategy_id': strategy_id,
            'symbol': symbol,
            'signal_type': signal_type,
            'confidence': confidence,
            'user_id': user_id,
            **extra_fields
        }
        
        message = f"Strategy {strategy_id} generated {signal_type} signal for {symbol} (confidence: {confidence})"
        self.logger.info(message, extra=extra)
        
    def log_portfolio_update(
        self,
        user_id: str,
        total_value: float,
        cash_balance: float,
        unrealized_pnl: float,
        **extra_fields
    ):
        """Log portfolio updates."""
        extra = {
            'event_type': 'portfolio_update',
            'user_id': user_id,
            'total_value': total_value,
            'cash_balance': cash_balance,
            'unrealized_pnl': unrealized_pnl,
            **extra_fields
        }
        
        message = f"Portfolio updated for user {user_id}: total={total_value}, cash={cash_balance}, pnl={unrealized_pnl}"
        self.logger.info(message, extra=extra)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_json_logging: bool = True
) -> Dict[str, logging.Logger]:
    """Setup comprehensive logging configuration."""
    
    # Create logs directory if it doesn't exist
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Base logging configuration
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
            'json': {
                '()': StructuredFormatter,
                'format': '%(asctime)s %(name)s %(levelname)s %(message)s'
            }
        },
        'handlers': {
            'console': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'stream': sys.stdout,
                'formatter': 'json' if enable_json_logging else 'standard'
            }
        },
        'loggers': {
            '': {  # Root logger
                'handlers': ['console'],
                'level': log_level,
                'propagate': False
            },
            'uvicorn': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False
            },
            'sqlalchemy': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False
            },
            'performance': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': False
            },
            'security': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False
            },
            'business': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False
            }
        }
    }
    
    # Add file handler if log file is specified
    if log_file:
        config['handlers']['file'] = {
            'level': log_level,
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': log_file,
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'json' if enable_json_logging else 'standard'
        }
        
        # Add file handler to all loggers
        for logger_config in config['loggers'].values():
            logger_config['handlers'].append('file')
    
    # Apply configuration
    logging.config.dictConfig(config)
    
    # Create specialized loggers
    loggers = {
        'performance': PerformanceLogger(),
        'security': SecurityLogger(),
        'business': BusinessLogger(),
        'main': logging.getLogger('trademk1')
    }
    
    return loggers


# Global logger instances
_loggers = None


def get_loggers() -> Dict[str, logging.Logger]:
    """Get configured logger instances."""
    global _loggers
    if _loggers is None:
        _loggers = setup_logging()
    return _loggers


def get_performance_logger() -> PerformanceLogger:
    """Get performance logger."""
    return get_loggers()['performance']


def get_security_logger() -> SecurityLogger:
    """Get security logger."""
    return get_loggers()['security']


def get_business_logger() -> BusinessLogger:
    """Get business logger."""
    return get_loggers()['business']


def get_main_logger() -> logging.Logger:
    """Get main application logger."""
    return get_loggers()['main']