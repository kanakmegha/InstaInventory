import json
from datetime import date
from app.persona import build_persona_snapshot

def test_build_persona_snapshot_exact_fields():
    """
    1. Feed a fixed set of orders and approvals, assert every computed field
       matches a hand-calculated expected value exactly.
    """
    # 3 orders spanning exactly 14 days (2.0 weeks)
    # Total spend = 28 + 56 + 60 = 144
    # Expected weekly spend = 144 / 2.0 = 72.0
    # Counts: milk = 2, tomato = 1. Top items sorted by count (desc), name (asc): ["milk", "tomato"]
    order_history = [
        {"item_name": "milk", "quantity": 1.0, "price": 28.0, "ordered_at": "2026-05-10T08:00:00"},
        {"item_name": "milk", "quantity": 2.0, "price": 56.0, "ordered_at": "2026-05-17T08:00:00"},
        {"item_name": "tomato", "quantity": 1.5, "price": 60.0, "ordered_at": "2026-05-24T08:00:00"}
    ]
    
    # 4 approvals: 3 pack_size suggestions (2 approved, 1 declined), 1 delivery_time suggestion (approved)
    # Bulk acceptance rate = 2 / 3 = 0.6667
    # Overall approval rate = 3 / 4 = 0.75
    approvals = [
        {"suggestion_type": "pack_size", "user_response": "approved"},
        {"suggestion_type": "pack_size", "user_response": "declined"},
        {"suggestion_type": "delivery_time", "user_response": "approved"},
        {"suggestion_type": "pack_size", "user_response": "approved"}
    ]
    
    week_of = date(2026, 5, 24)
    snapshot = build_persona_snapshot(week_of, order_history, approvals)
    
    assert snapshot["week_of"] == "2026-05-24"
    assert snapshot["avg_weekly_spend"] == 72.0
    assert snapshot["bulk_acceptance_rate"] == 0.6667
    assert snapshot["approval_rate"] == 0.75
    
    top_items = json.loads(snapshot["top_items_json"])
    assert top_items == ["milk", "tomato"]

def test_build_persona_snapshot_empty_approvals():
    """
    2. Feed an empty approvals list — assert rates default sensibly (0, not a division-by-zero crash).
    """
    order_history = [
        {"item_name": "milk", "quantity": 1.0, "price": 28.0, "ordered_at": "2026-05-10T08:00:00"}
    ]
    approvals = []
    
    week_of = date(2026, 5, 10)
    snapshot = build_persona_snapshot(week_of, order_history, approvals)
    
    assert snapshot["week_of"] == "2026-05-10"
    assert snapshot["avg_weekly_spend"] == 28.0  # 1 order, delta_days = 0, weeks = max(1.0, 0) = 1.0 -> 28 / 1 = 28.0
    assert snapshot["bulk_acceptance_rate"] == 0.0
    assert snapshot["approval_rate"] == 0.0
    
    top_items = json.loads(snapshot["top_items_json"])
    assert top_items == ["milk"]
