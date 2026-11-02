import pytest
from datetime import datetime, timezone
from backend.logs.store import UserLogStore


def test_user_log_store_record_and_get_dates(tmp_path):
    db_file = tmp_path / "test_logs.sqlite3"
    store = UserLogStore(sqlite_path=db_file)

    today = datetime.now(timezone.utc).strftime("%d-%m-%Y")

    # Initially available dates should include today
    dates = store.get_available_dates()
    assert today in dates

    # Record a log
    log_id = store.record_log(
        user_id="emp_001",
        user_name="John Doe",
        user_role="Employee",
        query="What is the reimbursement limit?",
        answer="The travel reimbursement limit is $500 per day.",
        capability="knowledge",
    )
    assert log_id != ""

    # Fetch logs for today
    logs, total = store.get_logs(date=today)
    assert total >= 1
    matching = [l for l in logs if l.id == log_id]
    assert len(matching) == 1
    entry = matching[0]
    assert entry.user_id == "emp_001"
    assert entry.query == "What is the reimbursement limit?"
    assert "reimbursement limit is $500" in entry.answer
    assert entry.log_date == today


def test_user_log_store_search_filter(tmp_path):
    db_file = tmp_path / "test_logs_search.sqlite3"
    store = UserLogStore(sqlite_path=db_file)

    store.record_log(
        user_id="usr_sales",
        user_name="Priya Sharma",
        user_role="Supervisor",
        query="Show sales pipeline for Q3",
        answer="Q3 pipeline is currently valued at $2.4M across 14 deals.",
    )
    store.record_log(
        user_id="usr_eng",
        user_name="Rahul Verma",
        user_role="Project Engineer",
        query="Explain system deployment steps",
        answer="Deployment uses Docker containers on AWS ECS.",
    )

    # Search for "sales"
    logs, total = store.get_logs(search="sales")
    assert total == 1
    assert logs[0].user_id == "usr_sales"

    # Search for "ECS"
    logs, total = store.get_logs(search="ECS")
    assert total == 1
    assert logs[0].user_id == "usr_eng"
