import logging
from asyncio import CancelledError, create_task
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.config import PROJECT_ROOT, get_settings
from app.database.session import get_database_manager
from app.routers import api, pages
from app.scheduling import (
    refresh_documents_at_scheduled_times,
    refresh_google_sheets_periodically,
    run_daily_scheduled_operations,
)
from app.services.google_sheets_memory_sync_service import GoogleSheetsMemorySyncService
from app.services.memory_store import get_memory_store
from app.services.monitoring import Monitoring, is_monitoring_or_static
from app.utils.logging_config import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    app.state.monitoring = Monitoring(settings)
    app.state.monitoring.payload()
    logger = logging.getLogger(__name__)
    logger.info(
        "Application started: environment=%s sample_mode=%s",
        settings.app_env,
        settings.use_sample_data,
    )
    background_tasks = []
    if settings.persistence_mode == "memory" and not settings.use_sample_data:
        result = GoogleSheetsMemorySyncService(settings, get_memory_store()).sync()
        if result.ok:
            logger.info(
                "Initial Google Sheets synchronization completed: processed=%s errors=%s",
                result.processed_count,
                result.error_count,
            )
        else:
            logger.error(
                "Initial Google Sheets synchronization failed: %s", result.message
            )
        if settings.auto_refresh_seconds > 0:
            background_tasks.append(create_task(refresh_google_sheets_periodically()))
        if settings.document_refresh_schedule:
            background_tasks.append(create_task(refresh_documents_at_scheduled_times()))
        if settings.scheduled_operations_enabled:
            background_tasks.append(create_task(run_daily_scheduled_operations()))
    yield
    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        with suppress(CancelledError):
            await task
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

    @application.get("/health", include_in_schema=False)
    @application.get("/health/", include_in_schema=False)
    async def health():
        payload = application.state.monitoring.payload()
        return JSONResponse(
            payload, status_code=200 if payload["status"] == "ok" else 503
        )

    @application.middleware("http")
    async def record_access(request, call_next):
        if is_monitoring_or_static(request.url.path):
            return await call_next(request)
        await run_in_threadpool(application.state.monitoring.increment)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            logging.getLogger(__name__).exception("Request failed")
            raise
        finally:
            logging.getLogger(__name__).info(
                '%s "%s %s" %s',
                request.client.host if request.client else "-",
                request.method,
                request.url.path,
                status_code,
            )

    return application


app = create_app()
