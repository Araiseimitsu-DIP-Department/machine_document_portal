from app.config import Settings
from app.database import session as session_module


def test_memory_mode_does_not_create_database_manager(monkeypatch) -> None:
    settings = Settings(
        persistence_mode="memory",
        use_sample_data=False,
        database_url="postgresql+psycopg://unused.invalid/database",
    )
    monkeypatch.setattr(session_module, "get_settings", lambda: settings)

    def unexpected_database_access():
        raise AssertionError("database manager must not be used in memory mode")

    monkeypatch.setattr(
        session_module, "get_database_manager", unexpected_database_access
    )
    dependency = session_module.get_db()
    assert next(dependency) is None
