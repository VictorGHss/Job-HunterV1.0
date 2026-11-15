import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app


def resolve_test_database_url(tmp_path: Path) -> str:
    env_url = os.environ.get("TEST_DATABASE_URL")
    if env_url:
        parsed = make_url(env_url)
        db_name = (parsed.database or "").lower()
        if "test" not in db_name:
            raise RuntimeError(
                f"TEST_DATABASE_URL ('{db_name}') deve apontar exclusivamente para um banco de testes."
            )
        return env_url

    db_file = tmp_path / "test_jobhunter.sqlite3"
    return f"sqlite:///{db_file}"


@pytest.fixture()
def db_engine(tmp_path: Path):
    test_db_url = resolve_test_database_url(tmp_path)
    connect_args = {"check_same_thread": False} if test_db_url.startswith("sqlite") else {}
    engine = create_engine(test_db_url, connect_args=connect_args, future=True)

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")

    yield engine

    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.downgrade(alembic_cfg, "base")

    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def make_client(db_engine):
    TestingSessionLocal = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    clients: list[TestClient] = []

    def _factory(client: tuple[str, int] = ("testclient", 50000)) -> TestClient:
        c = TestClient(app, client=client)
        clients.append(c)
        return c

    yield _factory

    for c in clients:
        c.close()
    app.dependency_overrides.clear()
