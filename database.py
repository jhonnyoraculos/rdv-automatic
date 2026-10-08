from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()


class Base(DeclarativeBase):
    """Base declarativa compartilhada pelos modelos do sistema."""


def _database_url() -> str:
    configured = os.getenv("DATABASE_URL", "").strip()
    if configured:
        # Use psycopg 3 explicitly; some providers still return postgres://.
        if configured.startswith("postgres://"):
            return configured.replace("postgres://", "postgresql+psycopg://", 1)
        if configured.startswith("postgresql://"):
            return configured.replace("postgresql://", "postgresql+psycopg://", 1)
        return configured
    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'rdv.db').as_posix()}"


def _build_engine() -> Engine:
    url = _database_url()
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
_init_lock = Lock()
_initialized = False
PERIOD_RESET_EVENT = "reset_periods_and_rdvs_2026_10_08_v1"


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_periods_and_rdvs_once() -> bool:
    """Remove all period data once while preserving employees and access."""
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS app_maintenance_events (
                    event_key VARCHAR(120) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        inserted = connection.execute(
            text(
                """
                INSERT INTO app_maintenance_events (event_key)
                VALUES (:event_key)
                ON CONFLICT (event_key) DO NOTHING
                """
            ),
            {"event_key": PERIOD_RESET_EVENT},
        )
        if inserted.rowcount != 1:
            return False

        if engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "TRUNCATE TABLE rdv_entries, rdv_submissions, rdv_periods "
                    "RESTART IDENTITY CASCADE"
                )
            )
        else:
            connection.execute(text("DELETE FROM rdv_entries"))
            connection.execute(text("DELETE FROM rdv_submissions"))
            connection.execute(text("DELETE FROM rdv_periods"))
    return True


def init_db() -> None:
    global _initialized

    # Import registers every mapped class before create_all runs.
    import models  # noqa: F401

    with _init_lock:
        if _initialized:
            return
        Base.metadata.create_all(bind=engine)
        employee_columns = {
            column["name"] for column in inspect(engine).get_columns("employees")
        }
        period_columns = {
            column["name"] for column in inspect(engine).get_columns("rdv_periods")
        }
        submission_columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("rdv_submissions")
        }
        existing = set(submission_columns)
        statements = []
        false_literal = "FALSE" if engine.dialect.name == "postgresql" else "0"
        if "username" not in employee_columns:
            statements.append("ALTER TABLE employees ADD COLUMN username VARCHAR(100)")
        if "password_hash" not in employee_columns:
            statements.append(
                "ALTER TABLE employees ADD COLUMN password_hash VARCHAR(200)"
            )
        if "automatic" not in period_columns:
            statements.append(
                "ALTER TABLE rdv_periods ADD COLUMN automatic BOOLEAN NOT NULL "
                f"DEFAULT {false_literal}"
            )
        if "location" not in existing:
            statements.append(
                "ALTER TABLE rdv_submissions ADD COLUMN location VARCHAR(80) NOT NULL DEFAULT ''"
            )
        new_columns = {
            "analyst_signed_at": "TIMESTAMP",
            "analyst_username": "VARCHAR(100)",
            "manager_signed_at": "TIMESTAMP",
            "manager_username": "VARCHAR(100)",
        }
        for column_name, column_type in new_columns.items():
            if column_name not in existing:
                statements.append(
                    f"ALTER TABLE rdv_submissions ADD COLUMN {column_name} {column_type}"
                )
        status_length = getattr(
            submission_columns.get("status", {}).get("type"), "length", None
        )
        if engine.dialect.name == "postgresql" and status_length and status_length < 32:
            statements.append(
                "ALTER TABLE rdv_submissions ALTER COLUMN status TYPE VARCHAR(32)"
            )
        if statements:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_employees_username ON employees (username)"
                )
            )
        reset_periods_and_rdvs_once()
        _initialized = True
