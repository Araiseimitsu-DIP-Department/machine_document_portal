import logging
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


logger = logging.getLogger(__name__)


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when normal mode is selected without a database URL."""


class DatabaseManager:
    """Owns the PostgreSQL engine and session factory."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        if not self.settings.database_url:
            raise DatabaseNotConfiguredError("DATABASE_URL is not configured")
        if self._engine is None:
            self._engine = create_engine(
                self.settings.database_url,
                pool_pre_ping=True,
                pool_size=self.settings.db_pool_size,
                max_overflow=self.settings.db_max_overflow,
                connect_args={"connect_timeout": self.settings.db_connect_timeout},
            )
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                class_=Session,
                autoflush=False,
                expire_on_commit=False,
            )
        return self._session_factory

    def session(self) -> Session:
        return self.session_factory()

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()


@lru_cache
def get_database_manager() -> DatabaseManager:
    return DatabaseManager(get_settings())


def get_db() -> Generator[Session | None, None, None]:
    """FastAPI dependency with explicit commit/rollback boundaries."""

    settings = get_settings()
    if settings.persistence_mode != "postgresql" or settings.use_sample_data:
        yield None
        return

    try:
        session = get_database_manager().session()
    except (DatabaseNotConfiguredError, SQLAlchemyError):
        logger.exception("PostgreSQL session could not be created")
        yield None
        return
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Database transaction failed and was rolled back")
        raise
    finally:
        session.close()
