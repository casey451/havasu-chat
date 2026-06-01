"""Master-spec v1 API routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.v1.routes.admin import router as admin_router
from app.v1.routes.admin_contrib import router as admin_contrib_router
from app.v1.routes.admin_crud import router as admin_crud_router
from app.v1.routes.seo import router as seo_router
from app.v1.routes.businesses import router as businesses_router
from app.v1.routes.categories import router as categories_router
from app.v1.routes.chat import router as chat_router
from app.v1.routes.contribute import router as contribute_router
from app.v1.routes.events import router as events_router
from app.v1.routes.feed import router as feed_router

router = APIRouter(tags=["v1-master-spec"])
router.include_router(feed_router)
router.include_router(businesses_router)
router.include_router(events_router)
router.include_router(categories_router)
router.include_router(chat_router)
router.include_router(contribute_router)
router.include_router(admin_router)
router.include_router(admin_crud_router)
router.include_router(admin_contrib_router)
router.include_router(seo_router)
