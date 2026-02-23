from sqlalchemy import text

from app.db.base import Base
from app.db.session import get_engine


def init_db() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=connection)
