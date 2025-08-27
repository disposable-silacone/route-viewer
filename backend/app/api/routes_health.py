from fastapi import APIRouter
import os


router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "graphhopper": os.getenv("GRAPHOPPER_BASE_URL", "http://localhost:8989")}


