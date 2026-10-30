from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text
from app.db.base_class import Base


class SystemMetadata(Base):
    """Stores system-level operational constants, seed version, and simulation clock state."""
    __tablename__ = "system_metadata"

    key = Column(String(100), primary_key=True, index=True)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SystemMetadata key={self.key}>"
