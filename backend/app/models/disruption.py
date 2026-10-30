from sqlalchemy import Column, String, DateTime, JSON, Text
from app.db.base_class import Base


class DisruptionScenario(Base):
    __tablename__ = "disruptions"

    id = Column(String(50), primary_key=True, index=True)
    category = Column(String(50), nullable=False)
    type = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    effective_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    expected_behaviour = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<DisruptionScenario {self.id}: {self.name}>"
