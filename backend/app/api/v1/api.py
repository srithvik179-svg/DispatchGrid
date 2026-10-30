from fastapi import APIRouter
from app.api.v1.endpoints import health, overview, jobs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(overview.router)
api_router.include_router(jobs.router)
