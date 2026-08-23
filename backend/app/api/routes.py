from fastapi import APIRouter

from app.api.proxies.controllers import router as proxies_router
from app.api.proxies_sources.controllers import router as proxies_sources_router
from app.api.router import TPCAPIRoute
from app.api.system.controllers import router as system_router

api_router = APIRouter(prefix="/api", route_class=TPCAPIRoute)


api_router.include_router(system_router, tags=["system"])
# Источники подключаются раньше проксей: иначе `/proxies/sources` перехватил бы
# `/proxies/{proxy_id}`, который объявлен в роутере проксей.
api_router.include_router(proxies_sources_router, tags=["proxies_sources"])
api_router.include_router(proxies_router, tags=["proxies"])
