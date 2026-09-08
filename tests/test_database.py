from sqlalchemy import create_engine, inspect, text

import database


def test_init_db_adds_signature_columns_to_existing_database(
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

    columns = {
        column["name"] for column in inspect(engine).get_columns("rdv_submissions")
    }
    assert {"location", "signed_date", "signature_data"} <= columns
    engine.dispose()
