from fastapi import APIRouter

from app.api.proxies.controllers import router as proxies_router
from app.api.router import TPCAPIRoute
from app.api.system.controllers import router as system_router

api_router = APIRouter(prefix="/api", route_class=TPCAPIRoute)


api_router.include_router(system_router, tags=["system"])
api_router.include_router(proxies_router, tags=["proxies"])
