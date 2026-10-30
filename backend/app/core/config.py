import re
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "DispatchGrid Backend Engine"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # Simulation Defaults
    SIMULATION_CLOCK_DEFAULT: str = "2026-11-02T10:00:00+05:30"
    
    # PostgreSQL Configuration
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "dispatchgrid"
    DATABASE_URL: Optional[str] = None

    # Connection Pool Settings
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_CONNECT_TIMEOUT: int = 5

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            # Normalize postgres:// to postgresql:// if needed
            uri = self.DATABASE_URL
            if uri.startswith("postgres://"):
                uri = uri.replace("postgres://", "postgresql+psycopg2://", 1)
            elif uri.startswith("postgresql://") and not uri.startswith("postgresql+"):
                uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)
            return uri
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SAFE_DATABASE_URI(self) -> str:
        """Returns database URI with password masked to prevent accidental credential leakage."""
        uri = self.SQLALCHEMY_DATABASE_URI
        return re.sub(r":([^:@]+)@", ":***@", uri)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
