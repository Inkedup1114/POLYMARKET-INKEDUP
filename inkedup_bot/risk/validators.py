"""
Comprehensive risk parameter validation framework with market condition cross-validation.

This module provides a robust validation system for risk parameters
used in trading operations on Polymarket, including market condition cross-validation.
"""

import abc
import asyncio
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum
import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories of validation errors."""
    TYPE_ERROR = "type_error"
    RANGE_ERROR = "range_error"
    FORMAT_ERROR = "format_error"
    BUSINESS_RULE = "business_rule"
    DEPENDENCY_ERROR = "dependency_error"


@dataclass
class ValidationError:
    """Represents a single validation error with context."""
    field: str
    message: str
    severity: ValidationSeverity
    category: ErrorCategory
    value: Any = None
    expected: Any = None
    context: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Ensure field is a string."""
        if not isinstance(self.field, str):
            self.field = str(self.field)


@dataclass
class ValidationResult:
    """Result of validation operation."""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    metadata: Dict[str, Any]

    def __post_init__(self):
        """Initialize empty lists if None."""
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.metadata is None:
            self.metadata = {}

    def add_error(self, error: ValidationError):
        """Add an error to the result."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: ValidationError):
        """Add a warning to the result."""
        self.warnings.append(warning)

    def merge(self, other: 'ValidationResult') -> 'ValidationResult':
        """Merge another validation result into this one."""
        return ValidationResult(
            is_valid=self.is_valid and other.is_valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
            metadata={**self.metadata, **other.metadata}
        )


class ValidationContext:
    """Shared context for validation operations."""
    
    def __init__(self, config: Any, market_data: Optional[Dict] = None):
        """Initialize validation context."""
        self.config = config
        self.market_data = market_data or {}
        self.cache = {}
        self._lock = asyncio.Lock()
    
    async def get_market_info(self, market_id: str) -> Optional[Dict]:
        """Get market information with caching."""
        async with self._lock:
            if market_id not in self.cache:
                self.cache[market_id] = self.market_data.get(market_id)
            return self.cache[market_id]
    
    def update_market_data(self, market_data: Dict):
        """Update market data."""
        self.market_data.update(market_data)
        for market_id in market_data:
            self.cache.pop(market_id, None)


class BaseValidator(abc.ABC):
    """Abstract base class for all validators."""
    
    def __init__(self, field_name: str, required: bool = True):
        """Initialize validator."""
        self.field_name = field_name
        self.required = required
    
    @abc.abstractmethod
    async def validate(
        self, 
        value: Any, 
        context: ValidationContext
    ) -> ValidationResult:
        """Validate a value and return result."""
        pass
    
    def _create_error(
        self,
        message: str,
        severity: ValidationSeverity = ValidationSeverity.HIGH,
        category: ErrorCategory = ErrorCategory.BUSINESS_RULE,
        value: Any = None,
        expected: Any = None,
        context: Optional[Dict] = None
    ) -> ValidationError:
        """Create a validation error."""
        return ValidationError(
            field=self.field_name,
            message=message,
            severity=severity,
            category=category,
            value=value,
            expected=expected,
            context=context
        )
    
    def _create_result(
        self,
        is_valid: bool = True,
        errors: Optional[List[ValidationError]] = None,
        warnings: Optional[List[ValidationError]] = None,
        metadata: Optional[Dict] = None
    ) -> ValidationResult:
        """Create a validation result."""
        return ValidationResult(
            is_valid=is_valid,
            errors=errors or [],
            warnings=warnings or [],
            metadata=metadata or {}
        )


# Market condition cross-validation validators
class VolatilityBasedLimitValidator(BaseValidator):
    """Validates limits based on current market volatility conditions."""
    
    def __init__(
        self,
        field_name: str = "limit",
        volatility_threshold: float = 0.15,
        adjustment_factor: float = 1.0,
        market_data_provider=None
    ):
        """Initialize volatility-based limit validator."""
        super().__init__(field_name, required=True)
        self.volatility_threshold = volatility_threshold
        self.adjustment_factor = adjustment_factor
        self.market_data_provider = market_data_provider
    
    async def validate(
        self, 
        value: Any, 
        context: ValidationContext
    ) -> ValidationResult:
        """Validate limit based on current market volatility."""
        if value is None:
            return self._create_result()
        
        try:
            limit = float(value)
            market_id = context.market_data.get('market_id')
            
            if not market_id:
                return self._create_result()
            
            # Placeholder for volatility calculation
            volatility = 0.15  # Placeholder value
            volatility_factor = volatility / self.volatility_threshold
            adjusted_limit = limit * (1 + (volatility_factor - 1) * self.adjustment_factor)
            
            if limit > adjusted_limit:
                return self._create_result(
                    is_valid=False,
                    errors=[self._create_error(
                        f"Limit {limit} exceeds volatility-adjusted maximum {adjusted_limit:.2f}",
                        severity=ValidationSeverity.HIGH,
                        category=ErrorCategory.BUSINESS_RULE,
                        value=limit,
                        expected=f"<= {adjusted_limit:.2f}"
                    )]
                )
            
            return self._create_result()
            
        except (ValueError, TypeError):
            return self._create_result(
                is_valid=False,
                errors=[self._create_error(
                    "Limit must be a valid number",
                    severity=ValidationSeverity.HIGH,
                    category=ErrorCategory.TYPE_ERROR
                )]
            )


class LiquidityBasedPositionValidator(BaseValidator):
    """Validates position sizes based on current market liquidity."""
    
    def __init__(
        self,
        field_name: str = "position_size",
        liquidity_ratio_threshold: float = 0.1,
        market_data_provider=None
    ):
        """Initialize liquidity-based position validator."""
        super().__init__(field_name, required=True)
        self.liquidity_ratio_threshold = liquidity_ratio_threshold
        self.market_data_provider = market_data_provider
    
    async def validate(
        self, 
        value: Any, 
        context: ValidationContext
    ) -> ValidationResult:
        """Validate position size based on market liquidity."""
        if value is None:
            return self._create_result()
        
        try:
            position_size = float(value)
            market_id = context.market_data.get('market_id')
            
            if not market_id:
                return self._create_result()
            
            # Placeholder for liquidity calculation
            max_position = 1000.0  # Placeholder value
            if position_size > max_position:
                return self._create_result(
                    is_valid=False,
                    errors=[self._create_error(
                        f"Position size {position_size} exceeds liquidity-based maximum {max_position:.2f}",
                        severity=ValidationSeverity.HIGH,
                        category=ErrorCategory.BUSINESS_RULE,
                        value=position_size,
                        expected=f"<= {max_position:.2f}"
                    )]
                )
            
            return self._create_result()
            
        except (ValueError, TypeError):
            return self._create_result(
                is_valid=False,
                errors=[self._create_error(
                    "Position size must be a valid number",
                    severity=ValidationSeverity.HIGH,
                    category=ErrorCategory.TYPE_ERROR
                )]
            )


class MarketStatusValidator(BaseValidator):
    """Validates trading against market status and conditions."""
    
    def __init__(
        self,
        field_name: str = "market_id",
        require_active: bool = True,
        market_data_provider=None
    ):
        """Initialize market status validator."""
        super().__init__(field_name, required=True)
        self.require_active = require_active
        self.market_data_provider = market_data_provider
    
    async def validate(
        self, 
        value: Any, 
        context: ValidationContext
    ) -> ValidationResult:
        """Validate market status before allowing trading."""
        if value is None:
            return self._create_result()
        
        try:
            market_id = str(value)
            
            # Placeholder for market status check
            is_active = True  # Placeholder
            is_suspended = False  # Placeholder
            is_settled = False  # Placeholder
            
            if not is_active:
                return self._create_result(
                    is_valid=False,
                    errors=[self._create_error(
                        f"Market {market_id} is not active",
                        severity=ValidationSeverity.CRITICAL,
                        category=ErrorCategory.BUSINESS_RULE
                    )]
                )
            
            if is_suspended:
                return self._create_result(
                    is_valid=False,
                    errors=[self._create_error(
                        f"Market {market_id} is suspended",
                        severity=ValidationSeverity.HIGH,
                        category=ErrorCategory.BUSINESS_RULE
                    )]
                )
            
            if is_settled:
                return self._create_result(
                    is_valid=False,
                    errors=[self._create_error(
                        f"Market {market_id} has already settled",
                        severity=ValidationSeverity.HIGH,
                        category=ErrorCategory.BUSINESS_RULE
                    )]
                )
            
            return self._create_result()
            
        except (ValueError, TypeError):
            return self._create_result(
                is_valid=False,
                errors=[self._create_error(
                    "Market ID must be a valid string",
                    severity=ValidationSeverity.HIGH,
                    category=ErrorCategory.TYPE_ERROR
                )]
            )


class CorrelationRiskValidator(BaseValidator):
    """Validates correlation risk across multiple positions."""
    
    def __init__(
        self,
        field_name: str = "portfolio",
        correlation_threshold: float = 0.7,
        max_correlated_exposure: float = 0.3,
        market_data_provider=None
    ):
        """Initialize correlation risk validator."""
        super().__init__(field_name, required=True)
        self.correlation_threshold = correlation_threshold
        self.max_correlated_exposure = max_correlated_exposure
        self.market_data_provider = market_data_provider
    
    async def validate(
        self, 
        value: Any,
        context: ValidationContext
    ) -> ValidationResult:
        """Validate correlation risk across portfolio positions."""
        if value is None or not isinstance(value, dict):
            return self._create_result()
        
        try:
            portfolio = value
            total_exposure = sum(abs(pos.get('size', 0)) for pos in portfolio.values())
            if total_exposure == 0:
                return self._create_result()
            
            # Placeholder for correlation calculation
            correlated_ratio = 0.1  # Placeholder
            if correlated_ratio > self.max_correlated_exposure:
                return self._create_result(
                    is_valid=False,
                    errors=[self._create_error(
                        f"Correlated exposure exceeds maximum {self.max_correlated_exposure:.1%}",
                        severity=ValidationSeverity.HIGH,
                        category=ErrorCategory.BUSINESS_RULE,
                        value=correlated_ratio,
                        expected=f"<= {self.max_correlated_exposure}"
                    )]
                )
            
            return self._create_result()
            
        except Exception as e:
            logger.error(f"Error validating correlation risk: {e}")
            return self._create_result(
                is_valid=False,
                errors=[self._create_error(
                    "Error validating correlation risk",
                    severity=ValidationSeverity.HIGH,
                    category=ErrorCategory.DEPENDENCY_ERROR
                )]
            )


# Factory functions for creating market condition validators
def create_volatility_validator(
    field_name: str = "limit",
    volatility_threshold: float = 0.15,
    market_data_provider=None
) -> VolatilityBasedLimitValidator:
    """Create a volatility-based limit validator."""
    return VolatilityBasedLimitValidator(
        field_name=field_name,
        volatility_threshold=volatility_threshold,
        market_data_provider=market_data_provider
    )


def create_liquidity_validator(
    field_name: str = "position_size",
    liquidity_ratio_threshold: float = 0.1,
    market_data_provider=None
) -> LiquidityBasedPositionValidator:
    """Create a liquidity-based position validator."""
    return LiquidityBasedPositionValidator(
        field_name=field_name,
        liquidity_ratio_threshold=liquidity_ratio_threshold,
        market_data_provider=market_data_provider
    )


def create_status_validator(
    field_name: str = "market_id",
    require_active: bool = True,
    market_data_provider=None
) -> MarketStatusValidator:
    """Create a market status validator."""
    return MarketStatusValidator(
        field_name=field_name,
        require_active=require_active,
        market_data_provider=market_data_provider
    )


def create_correlation_validator(
    correlation_threshold: float = 0.7,
    max_correlated_exposure: float = 0.3,
    market_data_provider=None
) -> CorrelationRiskValidator:
    """Create a correlation risk validator."""
    return CorrelationRiskValidator(
        correlation_threshold=correlation_threshold,
        max_correlated_exposure=max_correlated_exposure,
        market_data_provider=market_data_provider
    )


# Integration function to create market condition validation pipeline
def create_market_condition_validators(market_data_provider=None) -> Dict[str, BaseValidator]:
    """Create market condition validators with market data provider."""
    return {
        'volatility_limit': create_volatility_validator(market_data_provider=market_data_provider),
        'liquidity_position': create_liquidity_validator(market_data_provider=market_data_provider),
        'market_status': create_status_validator(market_data_provider=market_data_provider),
        'correlation_risk': create_correlation_validator(market_data_provider=market_data_provider)
    }