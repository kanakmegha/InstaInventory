import json
from datetime import date, datetime
from typing import Any
from app.db import get_db_connection

def build_persona_snapshot(week_of: date, order_history: list[dict[str, Any]], approvals: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Computes avg_weekly_spend, top_items (top 5 by frequency), bulk_acceptance_rate,
    and approval_rate. Matches the persona_snapshots schema from Phase 1.
    """
    # 1. Compute avg_weekly_spend
    total_spend = sum(float(o.get("price", 0.0)) for o in order_history)
    if not order_history:
        avg_weekly_spend = 0.0
    else:
        def parse_date(date_val: Any) -> date:
            if isinstance(date_val, datetime):
                return date_val.date()
            if isinstance(date_val, date):
                return date_val
            # Extract date part of ISO8601 string
            cleaned_str = str(date_val).split("T")[0]
            return date.fromisoformat(cleaned_str)
            
        dates = []
        for o in order_history:
            try:
                dates.append(parse_date(o["ordered_at"]))
            except Exception:
                pass
                
        if not dates:
            avg_weekly_spend = 0.0
        else:
            min_date = min(dates)
            max_date = max(dates)
            delta_days = (max_date - min_date).days
            # Default to at least 1 week
            weeks = max(1.0, delta_days / 7.0)
            avg_weekly_spend = round(total_spend / weeks, 2)
            
    # 2. Compute top_items (top 5 by frequency, secondary sort alphabetically)
    from collections import Counter
    item_counts = Counter(o.get("item_name") for o in order_history if o.get("item_name"))
    
    # Sort by frequency count (descending), then alphabetically by name (ascending)
    sorted_items = sorted(item_counts.items(), key=lambda x: (-x[1], x[0]))
    top_items = [name for name, count in sorted_items[:5]]
    top_items_json = json.dumps(top_items)
    
    # 3. Compute bulk_acceptance_rate and general approval_rate
    bulk_approvals = []
    for a in approvals:
        # Determine if this is a bulk/pack-size suggestion.
        # Default to True if indicators are not specified.
        is_bulk = True
        if "suggestion_type" in a:
            is_bulk = (a["suggestion_type"] == "pack_size")
        elif "is_bulk" in a:
            is_bulk = bool(a["is_bulk"])
            
        if is_bulk:
            bulk_approvals.append(a)
            
    approved_bulk = sum(1 for a in bulk_approvals if a.get("user_response") == "approved")
    bulk_acceptance_rate = round(approved_bulk / len(bulk_approvals), 4) if bulk_approvals else 0.0
    
    approved_all = sum(1 for a in approvals if a.get("user_response") == "approved")
    approval_rate = round(approved_all / len(approvals), 4) if approvals else 0.0
    
    # Format week_of to string
    week_of_str = week_of.isoformat() if hasattr(week_of, "isoformat") else str(week_of)
    
    return {
        "week_of": week_of_str,
        "avg_weekly_spend": avg_weekly_spend,
        "top_items_json": top_items_json,
        "bulk_acceptance_rate": bulk_acceptance_rate,
        "approval_rate": approval_rate,
        "notes": None
    }

def save_persona_snapshot(db_path: str, snapshot: dict[str, Any]) -> None:
    """
    Saves the computed persona snapshot into the persona_snapshots SQLite table.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO persona_snapshots (week_of, avg_weekly_spend, top_items_json, bulk_acceptance_rate, approval_rate, notes)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (
        snapshot.get("week_of"),
        snapshot.get("avg_weekly_spend", 0.0),
        snapshot.get("top_items_json", "[]"),
        snapshot.get("bulk_acceptance_rate", 0.0),
        snapshot.get("approval_rate", 0.0),
        snapshot.get("notes")
    ))
    conn.commit()
    conn.close()
