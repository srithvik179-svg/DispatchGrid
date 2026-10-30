import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text
from app.core.config import Settings, settings
from app.db.session import check_db_health, get_db, sanitize_error_message


def test_safe_database_uri_masks_credentials():
    """Verify that SAFE_DATABASE_URI masks password and prevents credential exposure."""
    custom_settings = Settings(
        POSTGRES_USER="my_user",
        POSTGRES_PASSWORD="SuperSecretPassword999",
        POSTGRES_SERVER="db.example.com",
        POSTGRES_DB="custom_grid",
    )
    safe_uri = custom_settings.SAFE_DATABASE_URI
    assert ":***@" in safe_uri
    assert "SuperSecretPassword999" not in safe_uri
    assert "my_user" in safe_uri


def test_sanitize_error_message_removes_passwords():
    """Verify error sanitizer strips passwords from connection errors."""
    raw_error = "FATAL: password authentication failed for user 'postgres' at postgresql://postgres:superSecretPass@localhost:5432/dispatchgrid"
    cleaned = sanitize_error_message(raw_error)
    assert "superSecretPass" not in cleaned
    assert ":***@" in cleaned


def test_database_health_check_success():
    """Verify check_db_health successfully queries database and returns latency."""
    health = check_db_health()
    assert health["status"] == "connected"
    assert health["database"] == settings.POSTGRES_DB
    assert health["engine"] == "postgresql"
    assert health["latency_ms"] is not None
    assert health["latency_ms"] > 0
    assert health["error"] is None


def test_database_health_check_invalid_connection_handling():
    """Verify that an unreachable database returns structured degraded status without leaking secrets."""
    bad_engine = create_engine(
        "postgresql+psycopg2://postgres:secretPass@localhost:5433/dispatchgrid_nonexistent",
        connect_args={"connect_timeout": 1},
    )
    health = check_db_health(custom_engine=bad_engine)
    assert health["status"] == "disconnected"
    assert health["error"] is not None
    assert "secretPass" not in health["error"]


def test_get_db_session_lifecycle():
    """Verify reusable get_db generator yields active session and manages lifecycle."""
    db_gen = get_db()
    session = next(db_gen)
    try:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@pytest.mark.asyncio
async def test_api_health_includes_database_status(client: AsyncClient):
    """Verify GET /health includes database health block with connection status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert data["database"]["status"] == "connected"
    assert data["database"]["database"] == "dispatchgrid"
    assert data["database"]["engine"] == "postgresql"
    assert data["database"]["latency_ms"] is not None


@pytest.mark.asyncio
async def test_api_health_db_dedicated_endpoint(client: AsyncClient):
    """Verify GET /api/v1/health/db returns detailed database connection health."""
    response = await client.get("/api/v1/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert data["database"] == "dispatchgrid"
    assert data["latency_ms"] is not None
