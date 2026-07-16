import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, get_settings
from app.database.session import get_database_manager
from app.routers import api, pages
from app.utils.logging_config import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    logger = logging.getLogger(__name__)
    logger.info(
        "Application started: environment=%s sample_mode=%s",
        settings.app_env,
        settings.use_sample_data,
    )
    yield
    if settings.persistence_mode == "postgresql":
        get_database_manager().dispose()
    logger.info("Application stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.mount(
        "/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static"
    )
    design_assets = PROJECT_ROOT / "docs" / "DESIGN"
    if design_assets.exists():
        application.mount(
            "/design-assets", StaticFiles(directory=design_assets), name="design-assets"
        )
    application.include_router(pages.router)
    application.include_router(api.router)
    return application


app = create_app()
