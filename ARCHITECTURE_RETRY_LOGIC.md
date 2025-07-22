# Resilient Retry Logic Architecture

## Overview
This document outlines the comprehensive retry logic architecture with exponential backoff, idempotency keys, circuit breaker patterns, and error classification systems.

## 1. Error Classification System

### Error Categories
```python
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass

class ErrorCategory(Enum):
    """Classification of errors for retry decision making."""
    
    # Retryable errors
    NETWORK_ERROR = "network_error"  # Connection issues, timeouts
    RATE_LIMIT = "rate_limit"  # API rate limiting
    SERVICE_UNAVAILABLE = "service_unavailable"  # 503, 504 responses
    TRANSIENT_ERROR = "transient_error"  # Temporary server issues
    
    # Non-retryable errors
    VALIDATION_ERROR = "validation_error"  # Invalid parameters
    AUTHENTICATION_ERROR = "authentication_error"  # Auth failures
    PERMISSION_DENIED = "permission_denied"  # Insufficient permissions
    NOT_FOUND = "not_found"  # Resource not found
    INSUFFICIENT_FUNDS = "insufficient_funds"  # Balance issues
    
    # Circuit breaker errors
    CIRCUIT_OPEN = "circuit_open"  # Circuit breaker is open
    TIMEOUT = "timeout"  # Operation timeout

@dataclass
class ErrorContext:
    """Context information for error handling decisions."""
    
    error_type: ErrorCategory
    error_message: str
    http_status: Optional[int] = None
    retry_after: Optional[int] = None  # Seconds to wait (from headers)
    error_details: Optional[Dict[str, Any]] = None
    
    @property
    def is_retryable(self) -> bool:
        """Determine if this error should trigger a retry."""
        retryable_types = {
            ErrorCategory.NETWORK_ERROR,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.SERVICE_UNAVAILABLE,
            ErrorCategory.TRANSIENT_ERROR,
        }
        return self.error_type in retryable_types
    
    @property
    def should_circuit_break(self) -> bool:
        """Determine if this error should count towards circuit breaker."""
        circuit_break_types = {
            ErrorCategory.NETWORK_ERROR,
            ErrorCategory.SERVICE_UNAVAILABLE,
            ErrorCategory.TIMEOUT,
        }
        return self.error_type in circuit_break_types
```

### Error Classifier Service
```python
class ErrorClassifier:
    """Service for classifying errors into retry categories."""
    
    def __init__(self):
        self.error_patterns = {
            # Network errors
            "ConnectionError": ErrorCategory.NETWORK_ERROR,
            "TimeoutError": ErrorCategory.NETWORK_ERROR,
            "ConnectionResetError": ErrorCategory.NETWORK_ERROR,
            
            # Rate limiting
            "429": ErrorCategory.RATE_LIMIT,
            "Rate limit exceeded": ErrorCategory.RATE_LIMIT,
            
            # Service unavailable
            "503": ErrorCategory.SERVICE_UNAVAILABLE,
            "504": ErrorCategory.SERVICE_UNAVAILABLE,
            "Service Unavailable": ErrorCategory.SERVICE_UNAVAILABLE,
            
            # Validation errors
            "400": ErrorCategory.VALIDATION_ERROR,
            "Invalid": ErrorCategory.VALIDATION_ERROR,
            
            # Authentication
            "401": ErrorCategory.AUTHENTICATION_ERROR,
            "403": ErrorCategory.PERMISSION_DENIED,
            
            # Not found
            "404": ErrorCategory.NOT_FOUND,
        }
    
    def classify(self, exception: Exception, response_data: Optional[Dict] = None) -> ErrorContext:
        """Classify an exception into an error context."""
        
        error_message = str(exception)
        http_status = None
        retry_after = None
        
        # Extract HTTP status from response
        if response_data and "status" in response_data:
            http_status = response_data["status"]
        
        # Determine error type
        error_type = self._determine_error_type(exception, error_message, http_status)
        
        # Extract retry-after header if available
        if response_data and "headers" in response_data:
            retry_after = response_data["headers"].get("Retry-After")
        
        return ErrorContext(
            error_type=error_type,
            error_message=error_message,
            http_status=http_status,
            retry_after=retry_after,
            error_details=response_data
        )
    
    def _determine_error_type(self, exception: Exception, message: str, status: Optional[int]) -> ErrorCategory:
        """Determine the specific error type based on exception and message."""
        
        # Check HTTP status codes
        if status:
            status_str = str(status)
            if status_str in self.error_patterns:
                return self.error_patterns[status_str]
        
        # Check exception type
        exception_name = exception.__class__.__name__
        if exception_name in self.error_patterns:
            return self.error_patterns[exception_name]
        
        # Check error message patterns
        for pattern, error_type in self.error_patterns.items():
            if pattern.lower() in message.lower():
                return error_type
        
        # Default to transient error for unknown cases
        return ErrorCategory.TRANSIENT_ERROR
```

## 2. Idempotency Key System

### Idempotency Key Generator
```python
import uuid
import hashlib
from typing import Dict, Any
from datetime import datetime, timedelta

class IdempotencyKeyGenerator:
    """Generates and manages idempotency keys for operations."""
    
    @staticmethod
    def generate_for_order(
        token_id: str,
        side: str,
        price: float,
        size: float,
        client_id: Optional[str] = None
    ) -> str:
        """Generate idempotency key for order placement."""
        
        # Create deterministic key based on order parameters
        key_data = f"{token_id}:{side}:{price}:{size}:{client_id or ''}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    @staticmethod
    def generate_for_operation(operation_type: str, **kwargs) -> str:
        """Generate idempotency key for any operation."""
        
        # Sort kwargs for consistent hashing
        sorted_kwargs = sorted(kwargs.items())
        key_data = f"{operation_type}:{sorted_kwargs}"
        return hashlib.md5(key_data.encode()).hexdigest()

@dataclass
class IdempotencyRecord:
    """Record of an idempotent operation."""
    
    key: str
    operation_type: str
    request_data: Dict[str, Any]
    response_data: Dict[str, Any]
    status: str  # 'pending', 'completed', 'failed'
    created_at: datetime
    expires_at: datetime
```

### Idempotency Storage
```python
class IdempotencyStore:
    """Storage layer for idempotency keys with TTL management."""
    
    def __init__(self, ttl_hours: int = 24):
        self.ttl_hours = ttl_hours
        
    async def store(self, record: IdempotencyRecord) -> None:
        """Store an idempotency record."""
        async with self.connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO idempotency_keys (
                    key, operation_type, request_data, response_data,
                    status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.key,
                    record.operation_type,
                    json.dumps(record.request_data),
                    json.dumps(record.response_data),
                    record.status,
                    record.created_at,
                    record.expires_at
                )
            )
    
    async def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Retrieve an idempotency record."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT * FROM idempotency_keys WHERE key = ? AND expires_at > ?",
                (key, datetime.utcnow())
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return IdempotencyRecord(
                        key=row["key"],
                        operation_type=row["operation_type"],
                        request_data=json.loads(row["request_data"]),
                        response_data=json.loads(row["response_data"]),
                        status=row["status"],
                        created_at=row["created_at"],
                        expires_at=row["expires_at"]
                    )
        return None
    
    async def cleanup_expired(self) -> None:
        """Clean up expired idempotency records."""
        async with self.connection() as db:
            await db.execute(
                "DELETE FROM idempotency_keys WHERE expires_at <= ?",
                (datetime.utcnow(),)
            )
```

### Idempotency Database Schema
```sql
CREATE TABLE idempotency_keys (
    key TEXT PRIMARY KEY,
    operation_type TEXT NOT NULL,
    request_data JSON NOT NULL,
    response_data JSON,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);
CREATE INDEX idx_idempotency_type ON idempotency_keys(operation_type);
```

## 3. Circuit Breaker Pattern

### Circuit Breaker States
```python
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional

class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    
    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: int = 60  # Seconds before attempting recovery
    half_open_max_calls: int = 3  # Max calls in half-open state
    success_threshold: int = 2  # Successes before closing
    
    # Sliding window configuration
    sliding_window_size: int = 100  # Number of calls to track
    sliding_window_type: str = "count"  # "count" or "time"
```

### Circuit Breaker Implementation
```python
class CircuitBreaker:
    """Circuit breaker implementation with sliding window metrics."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
        
        # Metrics tracking
        self.metrics = CircuitMetrics()
        
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        
        # Check circuit state
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
            else:
                raise CircuitOpenError(f"Circuit {self.name} is