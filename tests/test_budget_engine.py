import sqlite3
import pytest
from datetime import datetime
from app.db import init_db, get_db_connection
from app.budget_engine import check_budget, create_approval, save_approval, respond_to_approval

def test_check_budget_under_cap():
    """
    1. A proposed cost that stays under the cap — within_budget True, overage 0.
    """
    res = check_budget(proposed_cost=150.0, current_week_spend=800.0, weekly_cap=1000.0)
    assert res["within_budget"] is True
    assert res["projected_total"] == 950.0
    assert res["overage"] == 0.0

def test_check_budget_over_cap():
    """
    2. A proposed cost that pushes over the cap — within_budget False, overage equals the exact difference.
    """
    res = check_budget(proposed_cost=250.0, current_week_spend=800.0, weekly_cap=1000.0)
    assert res["within_budget"] is False
    assert res["projected_total"] == 1050.0
    assert res["overage"] == 50.0

def test_create_approval():
    """
    3. create_approval produces a dict with all required fields and status "pending".
    """
    pattern = {
        "id": 42,
        "item_name": "milk",
        "predicted_cycle_days": 3.0,
        "last_confirmed_at": "2026-05-10T12:00:00"
    }
    proposed_cost = 50.0
    budget_check = {"within_budget": True, "projected_total": 50.0, "overage": 0.0}
    
    approval = create_approval(pattern, proposed_cost, budget_check)
    
    assert approval["pattern_id"] == 42
    assert approval["proposed_date"] == "2026-05-13"  # 2026-05-10 + 3 days
    assert approval["proposed_cost"] == 50.0
    assert approval["user_response"] == "pending"
    assert approval["responded_at"] is None

@pytest.fixture
def temp_db(tmp_path):
    """
    Creates a temporary SQLite DB, registers schema, and populates a dummy
    pattern record to satisfy foreign key constraints.
    """
    db_file = tmp_path / "test_budget.db"
    db_path = str(db_file)
    init_db(db_path)
    
    # Insert a dummy pattern so we don't violate FK on approvals
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO patterns (id, item_name, predicted_cycle_days, confidence, status)
        VALUES (42, 'milk', 3.0, 0.9, 'active');
    """)
    conn.commit()
    conn.close()
    return db_path

def test_save_and_respond_to_approval(temp_db):
    """
    4. respond_to_approval correctly updates status and responded_at in a temp SQLite DB.
    """
    approval = {
        "pattern_id": 42,
        "proposed_date": "2026-05-13",
        "proposed_cost": 50.0,
        "user_response": "pending",
        "responded_at": None
    }
    
    # Save the approval
    approval_id = save_approval(temp_db, approval)
    assert isinstance(approval_id, int)
    
    # Verify it was inserted with pending state
    conn = get_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM approvals WHERE id = ?;", (approval_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row["pattern_id"] == 42
    assert row["proposed_cost"] == 50.0
    assert row["user_response"] == "pending"
    assert row["responded_at"] is None
    conn.close()
    
    # Respond to approval
    respond_to_approval(temp_db, approval_id, "approved")
    
    # Verify updates
    conn = get_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM approvals WHERE id = ?;", (approval_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row["user_response"] == "approved"
    assert row["responded_at"] is not None
    
    # Ensure responded_at parses as ISO8601 string successfully
    try:
        datetime.fromisoformat(row["responded_at"])
    except ValueError:
        pytest.fail("responded_at timestamp is not in valid ISO8601 format.")
    
    conn.close()
