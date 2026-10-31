"""Version 1 of the API. main.py serves this router under /api/v1."""
from fastapi import APIRouter

from app.routers.v1 import maps, stats

router = APIRouter()
router.include_router(maps.router)
router.include_router(stats.router)
