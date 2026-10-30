import logging
import re
import time
from typing import Any, Dict, Generator
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

logger = logging.getLogger(__name__)

# Engine configuration with connection pooling and timeouts
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    connect_args={
        "connect_timeout": settings.DB_CONNECT_TIMEOUT,
    } if "postgresql" in settings.SQLALCHEMY_DATABASE_URI else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Reusable database session generator with proper lifecycle and rollback on failure."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def sanitize_error_message(err_msg: str) -> str:
    """Removes sensitive database credentials, passwords, or connection strings from error text."""
    # Mask password in URL-like strings
    sanitized = re.sub(r":([^:@\s]+)@", ":***@", err_msg)
    # Mask password= arguments in DSN strings
    sanitized = re.sub(r"password=\S+", "password=***", sanitized, flags=re.IGNORECASE)
    return sanitized


def check_db_health(custom_engine=None) -> Dict[str, Any]:
    """
    Validates database connectivity by executing a lightweight query.
    Measures latency and returns safe diagnostic metadata without leaking credentials.
    """
    target_engine = custom_engine or engine
    start_time = time.perf_counter()
    try:
        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "connected",
            "database": settings.POSTGRES_DB,
            "engine": target_engine.dialect.name,
            "latency_ms": latency_ms,
            "error": None,
        }
    except (OperationalError, SQLAlchemyError, Exception) as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        safe_error = sanitize_error_message(str(exc))
        logger.warning("Database health check failed: %s", safe_error)
        return {
            "status": "disconnected",
            "database": settings.POSTGRES_DB,
            "engine": target_engine.dialect.name if hasattr(target_engine, "dialect") else "unknown",
            "latency_ms": latency_ms,
            "error": safe_error,
        }
