from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import Settings

engine = create_engine(Settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
