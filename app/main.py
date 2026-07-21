import logging
from asyncio import CancelledError, create_task, sleep, to_thread
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, get_settings
from app.database.session import get_database_manager
from app.routers import api, pages
from app.services.google_sheets_memory_sync_service import GoogleSheetsMemorySyncService
from app.services.memory_store import get_memory_store
from app.services.scheduled_operations_service import ScheduledOperationsService
from app.utils.logging_config import configure_logging


JST = ZoneInfo("Asia/Tokyo")


async def refresh_google_sheets_periodically() -> None:
    """Refresh Google data and documents for changed part numbers only."""

    settings = get_settings()
    if (
        settings.persistence_mode != "memory"
        or settings.use_sample_data
        or settings.auto_refresh_seconds == 0
    ):
        return
    logger = logging.getLogger(__name__)
    service = GoogleSheetsMemorySyncService(settings, get_memory_store())
    while True:
        await sleep(settings.auto_refresh_seconds)
        result = await to_thread(service.sync_changed)
        if result.ok:
            logger.info(
                "Scheduled Google Sheets synchronization completed: processed=%s",
                result.processed_count,
            )
        else:
            logger.error("Scheduled Google Sheets synchronization failed: %s", result.message)


def next_document_refresh_at(
    now: datetime,
    schedule: tuple[time, ...],
) -> datetime:
    """Return the next configured document-refresh time in Japan time."""

    candidates = [
        datetime.combine(now.date(), scheduled_time, tzinfo=JST)
        for scheduled_time in schedule
    ]
    future = [candidate for candidate in candidates if candidate > now]
    if future:
        return min(future)
    return datetime.combine(
        now.date() + timedelta(days=1),
        min(schedule),
        tzinfo=JST,
    )


async def refresh_documents_at_scheduled_times() -> None:
    """Fully refresh SharePoint and NAS at configured Japan-time clock times."""

    settings = get_settings()
    schedule = settings.document_refresh_schedule
    if (
        settings.persistence_mode != "memory"
        or settings.use_sample_data
        or not schedule
    ):
        return
    logger = logging.getLogger(__name__)
    service = GoogleSheetsMemorySyncService(settings, get_memory_store())
    while True:
        next_run = next_document_refresh_at(datetime.now(JST), schedule)
        delay = max((next_run - datetime.now(JST)).total_seconds(), 0)
        await sleep(delay)
        try:
            result = await to_thread(service.refresh_documents)
        except Exception:
            logger.exception("Scheduled SharePoint/NAS refresh failed unexpectedly")
            continue
        if result.ok:
            logger.info(
                "Scheduled SharePoint/NAS refresh completed: processed=%s",
                result.processed_count,
            )
        else:
            logger.error("Scheduled SharePoint/NAS refresh failed: %s", result.message)


async def run_daily_scheduled_operations() -> None:
    """Run the 13:00 notification and 15:00 printing once per calendar day."""

    settings = get_settings()
    if (
        not settings.scheduled_operations_enabled
        or settings.persistence_mode != "memory"
        or settings.use_sample_data
    ):
        return
    logger = logging.getLogger(__name__)
    service = ScheduledOperationsService(settings)
    triggered: set[tuple[str, str]] = set()
    while True:
        now = datetime.now(JST)
        run_date = now.date()
        jobs = (
            ("next-day-check", time(13, 0), service.check_and_notify),
            ("drawing-print", time(15, 0), service.print_drawings),
        )
        for job_name, scheduled_time, operation in jobs:
            trigger_key = (run_date.isoformat(), job_name)
            if now.time() < scheduled_time or trigger_key in triggered:
                continue
            triggered.add(trigger_key)
            try:
                result = await to_thread(operation, run_date)
            except Exception:
                logger.exception("Daily scheduled operation failed: job=%s", job_name)
            else:
                logger.info(
                    "Daily scheduled operation finished: job=%s status=%s message=%s",
                    job_name,
                    result.status,
                    result.message,
                )
        cutoff = run_date.isoformat()
        triggered = {key for key in triggered if key[0] == cutoff}
        await sleep(30)


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
            logger.error("Initial Google Sheets synchronization failed: %s", result.message)
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
    return application


app = create_app()
