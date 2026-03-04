from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from ..config import Settings

router = APIRouter()


@router.get("/api/v1/versions/{version_tag}/binary")
def get_binary(version_tag: str):
    file_path = os.path.join(Settings.VERSIONS_DIR, version_tag, "agent.py")
    if not os.path.exists(file_path):
        raise HTTPException(404, f"Binary not found for version {version_tag}")
    return FileResponse(file_path, filename="agent.py")
