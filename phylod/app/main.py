from contextlib import asynccontextmanager
from fastapi import FastAPI
import os

from .config import Settings
from .db import engine, SessionLocal
from .models import Base, Version
from .routes import sync, versions, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create tables
    Base.metadata.create_all(bind=engine)

    # 2. Scan versions directory, register in DB
    versions_dir = Settings.VERSIONS_DIR
    db = SessionLocal()
    try:
        for entry in os.listdir(versions_dir):
            if os.path.isdir(os.path.join(versions_dir, entry)):
                existing = db.query(Version).filter_by(version_tag=entry).first()
                if not existing:
                    db.add(Version(version_tag=entry, is_released=False, is_broken=False))
        db.commit()
    finally:
        db.close()

    yield


app = FastAPI(lifespan=lifespan)
app.include_router(sync.router)
app.include_router(versions.router)
app.include_router(admin.router)
