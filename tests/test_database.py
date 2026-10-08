from sqlalchemy import create_engine, inspect, text

import database


def test_init_db_adds_access_and_automatic_period_columns(
    tmp_path, monkeypatch
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE rdv_submissions (id INTEGER PRIMARY KEY)")
        )
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_initialized", False)

    database.init_db()

    submission_columns = {
        column["name"] for column in inspect(engine).get_columns("rdv_submissions")
    }
    employee_columns = {
        column["name"] for column in inspect(engine).get_columns("employees")
    }
    period_columns = {
        column["name"] for column in inspect(engine).get_columns("rdv_periods")
    }
    assert {"location", "analyst_signed_at", "manager_signed_at"} <= submission_columns
    assert {"username", "password_hash"} <= employee_columns
    assert "automatic" in period_columns
    assert "employee_sessions" in inspect(engine).get_table_names()
    engine.dispose()


def test_period_reset_runs_once_and_preserves_future_data(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'reset.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE rdv_periods (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text("CREATE TABLE rdv_submissions (id INTEGER PRIMARY KEY)")
        )
        connection.execute(text("CREATE TABLE rdv_entries (id INTEGER PRIMARY KEY)"))
        for table in ("rdv_periods", "rdv_submissions", "rdv_entries"):
            connection.execute(text(f"INSERT INTO {table} (id) VALUES (1)"))

    monkeypatch.setattr(database, "engine", engine)
    assert database.reset_periods_and_rdvs_once() is True

    with engine.begin() as connection:
        for table in ("rdv_periods", "rdv_submissions", "rdv_entries"):
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0
        connection.execute(text("INSERT INTO rdv_periods (id) VALUES (2)"))

    assert database.reset_periods_and_rdvs_once() is False
    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM rdv_periods")).scalar() == 1
    engine.dispose()
