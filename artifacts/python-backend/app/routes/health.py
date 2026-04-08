from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("/healthz")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z", "service": "python-backend"}
