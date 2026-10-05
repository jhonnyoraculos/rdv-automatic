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
    engine.dispose()
