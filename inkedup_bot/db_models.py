"""
SQLAlchemy models for database schema management and migrations.
Defines the complete database schema using SQLAlchemy ORM.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()


class Order(Base):
    """Orders table - tracks all trading orders."""

    __tablename__ = "orders"

    id = Column(String, primary_key=True, nullable=False)
    token_id = Column(String, nullable=False, index=True)
    market_slug = Column(String, index=True)
    side = Column(String, nullable=False)  # BUY/SELL
    price = Column(Numeric(20, 8), nullable=False)
    size = Column(Numeric(20, 8), nullable=False)
    status = Column(String, nullable=False, index=True)  # OPEN/FILLED/CANCELLED etc.
    created_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    filled_at = Column(DateTime)
    notional_value = Column(Numeric(20, 8))
    outcome_type = Column(String)  # YES/NO

    # Relationship to trades
    trades = relationship("Trade", back_populates="order")


class Position(Base):
    """Positions table - tracks current positions."""

    __tablename__ = "positions"

    token_id = Column(String, primary_key=True, nullable=False)
    market_slug = Column(String, index=True)
    outcome_type = Column(String)
    size = Column(Numeric(20, 8), nullable=False)
    notional_value = Column(Numeric(20, 8), nullable=False)
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class Trade(Base):
    """Trades table - execution records."""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    token_id = Column(String, nullable=False, index=True)
    market_slug = Column(String)
    side = Column(String, nullable=False)
    price = Column(Numeric(20, 8), nullable=False)
    size = Column(Numeric(20, 8), nullable=False)
    notional_value = Column(Numeric(20, 8), nullable=False)
    outcome_type = Column(String)
    executed_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    # Relationship to order
    order = relationship("Order", back_populates="trades")


class MarketSnapshot(Base):
    """Market snapshots for historical data."""

    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_slug = Column(String, nullable=False)
    token_id = Column(String, nullable=False, index=True)
    bid = Column(Numeric(20, 8))
    ask = Column(Numeric(20, 8))
    spread_bps = Column(Numeric(10, 2))
    volume_24h = Column(Numeric(20, 8))
    liquidity = Column(Numeric(20, 8))
    snapshot_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class RiskEvent(Base):
    """Risk events and alerts."""

    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False)
    token_id = Column(String, index=True)
    market_slug = Column(String)
    outcome_type = Column(String)
    current_exposure = Column(Numeric(20, 8))
    limit_value = Column(Numeric(20, 8))
    intended_notional = Column(Numeric(20, 8))
    description = Column(Text)
    occurred_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class OutcomeExposure(Base):
    """Detailed outcome exposure tracking."""

    __tablename__ = "outcome_exposures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_slug = Column(String, nullable=False, index=True)
    outcome_id = Column(String, nullable=False, index=True)
    outcome_name = Column(String, nullable=False)
    position_size = Column(Numeric(20, 8), nullable=False)
    notional_value = Column(Numeric(20, 8), nullable=False)
    average_price = Column(Numeric(20, 8), nullable=False)
    current_price = Column(Numeric(20, 8), nullable=False)
    unrealized_pnl = Column(Numeric(20, 8), nullable=False)
    realized_pnl = Column(Numeric(20, 8), nullable=False)
    correlation_coefficient = Column(Numeric(10, 8), server_default="0.0")
    risk_score = Column(Numeric(10, 8), server_default="0.0")
    last_updated = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("market_slug", "outcome_id", name="_market_outcome_uc"),
    )


class OutcomeCorrelation(Base):
    """Outcome correlation tracking."""

    __tablename__ = "outcome_correlations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    outcome_a = Column(String, nullable=False)
    outcome_b = Column(String, nullable=False)
    correlation = Column(Numeric(10, 8), nullable=False)
    covariance = Column(Numeric(20, 8), nullable=False)
    last_calculated = Column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        UniqueConstraint("outcome_a", "outcome_b", name="_outcome_pair_uc"),
    )


class OutcomeExposureHistory(Base):
    """Historical outcome exposure snapshots."""

    __tablename__ = "outcome_exposure_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_slug = Column(String, nullable=False)
    outcome_id = Column(String, nullable=False)
    outcome_name = Column(String, nullable=False)
    position_size = Column(Numeric(20, 8), nullable=False)
    notional_value = Column(Numeric(20, 8), nullable=False)
    unrealized_pnl = Column(Numeric(20, 8), nullable=False)
    risk_score = Column(Numeric(10, 8), nullable=False)
    snapshot_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )

    # Composite index for efficient queries
    __table_args__ = (
        # Index for market + outcome queries
        # Index for time-based queries handled by individual column index above
    )


class ExposureAlert(Base):
    """Exposure alerts and notifications."""

    __tablename__ = "exposure_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_type = Column(String, nullable=False, index=True)
    market_slug = Column(String)
    outcome_id = Column(String)
    threshold_value = Column(Numeric(20, 8))
    current_value = Column(Numeric(20, 8))
    alert_message = Column(Text)
    triggered_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    acknowledged = Column(Boolean, server_default="false", index=True)

    # Composite index for alert management
    __table_args__ = (
        # Index on alert_type + acknowledged for efficient alert queries
    )


class MigrationVersion(Base):
    """Migration version tracking - managed by Alembic."""

    __tablename__ = "alembic_version"

    version_num = Column(String(32), primary_key=True, nullable=False)


# Database configuration and utilities
def get_database_url(config_database_url: str) -> str:
    """Get properly formatted database URL for SQLAlchemy."""
    if config_database_url.startswith("sqlite:"):
        return config_database_url
    elif config_database_url.startswith(("postgresql:", "postgres:")):
        return config_database_url
    else:
        # Default to SQLite if no scheme specified
        return f"sqlite:///{config_database_url}"


def create_engine_for_url(database_url: str, **kwargs):
    """Create SQLAlchemy engine for the given database URL."""
    if database_url.startswith("sqlite:"):
        # SQLite-specific configuration
        return create_engine(
            database_url,
            echo=kwargs.get("echo", False),
            connect_args=(
                {"check_same_thread": False} if ":memory:" not in database_url else {}
            ),
            **{k: v for k, v in kwargs.items() if k != "echo"},
        )
    else:
        # PostgreSQL configuration
        return create_engine(
            database_url,
            echo=kwargs.get("echo", False),
            pool_size=kwargs.get("pool_size", 10),
            max_overflow=kwargs.get("max_overflow", 20),
            **{
                k: v
                for k, v in kwargs.items()
                if k not in ("echo", "pool_size", "max_overflow")
            },
        )


def get_session_factory(engine):
    """Create session factory for the given engine."""
    return sessionmaker(bind=engine)
