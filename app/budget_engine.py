import datetime
from typing import Any
from app.db import get_db_connection

def check_budget(proposed_cost: float, current_week_spend: float, weekly_cap: float) -> dict[str, Any]:
    """
    Checks if a proposed cost fits within the weekly budget cap, taking current week spend into account.
    Returns: {within_budget: bool, projected_total: float, overage: float}
    overage is 0 if within_budget is True.
    """
    projected_total = current_week_spend + proposed_cost
    within_budget = projected_total <= weekly_cap
    overage = 0.0 if within_budget else round(projected_total - weekly_cap, 2)
    
    return {
        "within_budget": within_budget,
        "projected_total": round(projected_total, 2),
        "overage": overage
    }

def create_approval(pattern: dict[str, Any], proposed_cost: float, budget_check: dict[str, Any]) -> dict[str, Any]:
    """
    Builds a pure approval record dict matching the approvals database schema with status "pending".
    Does not write to the DB.
    """
    base_date = datetime.date.today()
    if pattern.get("last_confirmed_at"):
        try:
            lc = pattern["last_confirmed_at"]
            if "T" in lc:
                base_date = datetime.datetime.fromisoformat(lc.replace("Z", "+00:00")).date()
            else:
                base_date = datetime.date.fromisoformat(lc)
        except Exception:
            pass
            
    cycle_days = pattern.get("predicted_cycle_days", 0)
    proposed_date_obj = base_date + datetime.timedelta(days=cycle_days)
    proposed_date_str = proposed_date_obj.isoformat()
    
    return {
        "pattern_id": pattern.get("id"),
        "proposed_date": proposed_date_str,
        "proposed_cost": proposed_cost,
        "user_response": "pending",
        "responded_at": None
    }

def save_approval(db_path: str, approval: dict[str, Any]) -> int:
    """
    Persists a created approval dictionary record into the approvals SQLite table.
    Returns the primary key ID of the inserted row.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO approvals (pattern_id, proposed_date, proposed_cost, user_response, responded_at)
        VALUES (?, ?, ?, ?, ?);
    """, (
        approval.get("pattern_id"),
        approval.get("proposed_date"),
        approval.get("proposed_cost"),
        approval.get("user_response"),
        approval.get("responded_at")
    ))
    inserted_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    if inserted_id is None:
        raise RuntimeError("Failed to insert approval record; lastrowid is None")
    return inserted_id

def respond_to_approval(db_path: str, approval_id: int, response: str) -> None:
    """
    Updates the approval row in the database with the user's response
    ("approved" or "declined") and the current ISO8601 responded_at timestamp.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    responded_at = datetime.datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE approvals
        SET user_response = ?, responded_at = ?
        WHERE id = ?;
    """, (response, responded_at, approval_id))
    
    conn.commit()
    conn.close()
