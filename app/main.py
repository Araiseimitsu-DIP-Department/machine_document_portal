import logging
from asyncio import CancelledError, create_task, sleep, to_thread
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, get_settings
from app.database.session import get_database_manager
from app.routers import api, pages
from app.services.google_sheets_memory_sync_service import GoogleSheetsMemorySyncService
from app.services.memory_store import get_memory_store
from app.utils.logging_config import configure_logging


async def refresh_google_sheets_periodically() -> None:
    """Run the external refresh once per server interval, not once per browser."""

    settings = get_settings()
    if (
        settings.persistence_mode != "memory"
        or settings.use_sample_data
        or settings.auto_refresh_seconds == 0
    ):
        return
    logger = logging.getLogger(__name__)
    while True:
        await sleep(settings.auto_refresh_seconds)
        result = await to_thread(
            GoogleSheetsMemorySyncService(settings, get_memory_store()).sync
        )
        if result.ok:
            logger.info(
                "Scheduled Google Sheets synchronization completed: processed=%s",
                result.processed_count,
            )
        else:
            logger.error("Scheduled Google Sheets synchronization failed: %s", result.message)


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
    refresh_task = None
    if settings.persistence_mode == "memory" and not settings.use_sample_data:
        result = GoogleSheetsMemorySyncService(settings, get_memory_store()).sync()
        if result.ok:
            logger.info(
                "Initial Google Sheets synchronization completed: processed=%s errors=%s",
                result.processed_count,
                result.error_count,
            )
        else:
            logger.error("Initial Google Sheets synchronization failed: %s", result.message)
        if settings.auto_refresh_seconds > 0:
            refresh_task = create_task(refresh_google_sheets_periodically())
    yield
    if refresh_task:
        refresh_task.cancel()
        with suppress(CancelledError):
            await refresh_task
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
