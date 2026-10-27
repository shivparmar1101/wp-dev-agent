from __future__ import annotations

import threading


def test_execute_before_schema_init_does_not_deadlock():
    """`execute()` takes the write lock and then initialises the schema.

    With a non-reentrant Lock that second acquisition blocks forever, so any
    fresh process writing before init_db() would hang silently. Run the write
    on a thread so a regression fails the test instead of hanging the suite.
    """
    from backend.storage import db

    db.reset_initialized_flag()

    outcome: list[str] = []
    finished = threading.Event()

    def run() -> None:
        try:
            db.execute(
                "INSERT OR IGNORE INTO oauth_states (state, created_at, expires_at, used)"
                " VALUES (?,?,?,0)",
                ("regression-probe", "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"),
            )
            outcome.append("ok")
        except Exception as exc:  # pragma: no cover - failure path
            outcome.append(f"error: {exc}")
        finally:
            finished.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=5)

    assert finished.is_set(), "db.execute() deadlocks when the schema is not initialised"
    assert outcome == ["ok"]

    row = db.query_one(
        "SELECT state FROM oauth_states WHERE state = ?", ("regression-probe",)
    )
    assert row is not None

    db.execute("DELETE FROM oauth_states WHERE state = ?", ("regression-probe",))
    assert db._initialized is True
