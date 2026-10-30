from typing import Any
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    id: Any
    __name__: str

    # Automatically generate __tablename__ based on class name (in snake_case) if not provided
    @declared_attr.directive
    def __tablename__(cls) -> str:
        name = cls.__name__
        # Convert CamelCase to snake_case
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
