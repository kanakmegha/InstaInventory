import os
import pytest
from fastapi.testclient import TestClient

# We patch environment variables before importing app to isolate the DB
@pytest.fixture(autouse=True)
def setup_api_test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_api.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("USE_MOCK_DATA", "True")
    
    # Import main and set values on startup
    import app.main
    app.main.DB_PATH = str(db_file)
    app.main.on_startup()
    yield

from app.main import app
client = TestClient(app)

def test_get_root_serves_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "InstaInventory" in response.text

def test_get_patterns():
    response = client.get("/patterns")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "item_name" in data[0]
    assert "predicted_cycle_days" in data[0]

def test_confirm_pattern_success_and_error():
    # Success
    response = client.post("/patterns/1/confirm")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Failure (404)
    response = client.post("/patterns/99999/confirm")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_reject_pattern_success_and_error():
    # Success
    response = client.post("/patterns/1/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Failure (404)
    response = client.post("/patterns/99999/reject")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_edit_cycle_success_and_error():
    # Success
    response = client.post("/patterns/1/edit-cycle", json={"predicted_cycle_days": 14.5})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Failure (404)
    response = client.post("/patterns/99999/edit-cycle", json={"predicted_cycle_days": 14.5})
    assert response.status_code == 404
    
    # Failure (validation error)
    response = client.post("/patterns/1/edit-cycle", json={"predicted_cycle_days": "not-a-number"})
    assert response.status_code == 422

def test_get_approvals():
    response = client.get("/approvals")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "proposed_cost" in data[0]
    assert "type" in data[0]

def test_approve_approval_success_and_error():
    # Fetch approvals to get the calculated suggested frequency days for milk
    approvals_resp = client.get("/approvals").json()
    milk_approval = next(a for a in approvals_resp if a["item_name"] == "milk")
    expected_cycle = milk_approval["suggested_frequency_days"]

    # Fetch initial budget spend
    start_budget = client.get("/budget").json()
    start_spend = start_budget["current_week_spend"]
    
    # Query database directly for starting count of milk orders
    import sqlite3
    import app.main
    conn = sqlite3.connect(app.main.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM order_history WHERE item_name = 'milk';")
    start_count = cursor.fetchone()[0]
    conn.close()
    
    # Success: Approve Milk suggestion (which will hit the pack suggestion branch)
    response = client.post("/approvals/1/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "placed successfully" in response.json()["message"].lower()
    
    # Verify budget spend increased by the option price (₹40.0)
    end_budget = client.get("/budget").json()
    end_spend = end_budget["current_week_spend"]
    assert abs((end_spend - start_spend) - 40.0) < 0.01
    
    # Verify order_history has one more milk row
    conn = sqlite3.connect(app.main.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM order_history WHERE item_name = 'milk';")
    end_count = cursor.fetchone()[0]
    
    # Verify the pattern's predicted_cycle_days was automatically updated to expected_cycle
    cursor.execute("SELECT predicted_cycle_days FROM patterns WHERE item_name = 'milk';")
    new_cycle = cursor.fetchone()[0]
    conn.close()
    
    assert end_count == start_count + 1
    assert abs(new_cycle - expected_cycle) < 0.01
    
    # Failure (404)
    response = client.post("/approvals/99999/approve")
    assert response.status_code == 404

def test_decline_approval_success_and_error():
    # Success
    response = client.post("/approvals/3/decline")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Failure (404)
    response = client.post("/approvals/99999/decline")
    assert response.status_code == 404

def test_get_budget():
    response = client.get("/budget")
    assert response.status_code == 200
    data = response.json()
    assert "current_week_spend" in data
    assert "weekly_cap" in data
    assert "remaining" in data
    assert "overage" in data
    assert "weekly_items" in data
    
    weekly_items = data["weekly_items"]
    assert isinstance(weekly_items, list)
    
    items_sum = sum(item["total_cost"] for item in weekly_items)
    assert abs(items_sum - data["current_week_spend"]) < 0.01

def test_update_budget_cap():
    # Success
    response = client.post("/budget/cap", json={"weekly_cap": 3000.0})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Validation Failure
    response = client.post("/budget/cap", json={"weekly_cap": "invalid"})
    assert response.status_code == 422

def test_get_persona():
    response = client.get("/persona")
    assert response.status_code == 200
    data = response.json()
    assert "latest" in data
    assert "timeline" in data
    assert data["latest"] is not None
    assert "avg_weekly_spend" in data["latest"]
    
    latest = data["latest"]
    assert "top_items" in latest
    assert "top_items_json" in latest
    assert isinstance(latest["top_items"], list)
    assert len(latest["top_items"]) > 0
    import json
    assert latest["top_items"] == json.loads(latest["top_items_json"])

def test_get_approvals_optimization_calculation():
    """
    Asserts that current_total_cost - suggested_total_cost == savings (within rounding)
    for a known seeded item returned in GET /approvals.
    """
    response = client.get("/approvals")
    assert response.status_code == 200
    data = response.json()
    
    # Filter pack size suggestion approvals
    pack_suggestions = [x for x in data if x.get("type") == "pack_size_suggestion"]
    
    # Expect at least one pack size suggestion in the seeded DB
    assert len(pack_suggestions) > 0, f"Expected at least one pack suggestion, got: {data}"
    
    for sug in pack_suggestions:
        current = sug["current_total_cost"]
        suggested = sug["suggested_total_cost"]
        savings = sug["savings"]
        # Allow small floating point rounding error (1e-2 since we round to 2 decimals)
        assert abs((current - suggested) - savings) < 0.01

def test_persona_recalculation_upon_approvals():
    """
    Approve two items, call GET /persona, and assert approval_rate reflects
    the real approved/total ratio rather than the stale 0% from before.
    """
    # 1. Fetch pending approvals list
    response = client.get("/approvals")
    assert response.status_code == 200
    approvals = response.json()
    assert len(approvals) >= 2, f"Expected at least 2 approvals for test, got: {approvals}"
    
    # 2. Approve two items
    app1 = approvals[0]
    app2 = approvals[1]
    
    resp1 = client.post(f"/approvals/{app1['id']}/approve")
    assert resp1.status_code == 200
    
    resp2 = client.post(f"/approvals/{app2['id']}/approve")
    assert resp2.status_code == 200
    
    # 3. Call GET /persona and verify it recalculates approval_rate
    persona_resp = client.get("/persona")
    assert persona_resp.status_code == 200
    persona_data = persona_resp.json()
    
    latest = persona_data["latest"]
    assert latest is not None
    
    # Check that approval rate is updated and greater than 0
    assert latest["approval_rate"] > 0.0
    
    # Check that the timeline contains this latest snapshot
    assert len(persona_data["timeline"]) > 0
    assert persona_data["timeline"][0]["approval_rate"] == latest["approval_rate"]

def test_approval_mutates_state_fully():
    # 1. Fetch initial budget spend
    start_budget = client.get("/budget").json()
    start_spend = start_budget["current_week_spend"]
    
    # Find a pending approval
    approvals_resp = client.get("/approvals").json()
    milk_approval = next(a for a in approvals_resp if a["item_name"] == "milk")
    
    # 2. Approve and get full state response payload in one go
    response = client.post(f"/approvals/{milk_approval['id']}/approve")
    assert response.status_code == 200
    state = response.json()
    
    # 3. Assert it has all main state keys
    assert "patterns" in state
    assert "approvals" in state
    assert "budget" in state
    assert "persona" in state
    assert "copy" in state
    
    # 4. Verify budget spend in that same response payload reflects the new spend
    end_spend = state["budget"]["current_week_spend"]
    assert abs((end_spend - start_spend) - 40.0) < 0.01

def test_state_equivalence_with_individual_endpoints():
    # 1. Fetch from /state
    state_resp = client.get("/state")
    assert state_resp.status_code == 200
    state = state_resp.json()
    
    # 2. Fetch individual endpoints
    patterns = client.get("/patterns").json()
    approvals = client.get("/approvals").json()
    budget = client.get("/budget").json()
    persona = client.get("/persona").json()
    
    # 3. Compare them directly
    assert state["patterns"] == patterns
    assert state["approvals"] == approvals
    assert state["budget"] == budget
    assert state["persona"] == persona

@pytest.mark.parametrize("item_name,bulk_unit,bulk_price,predicted_cycle", [
    ("eggs", "12-pack", 120.0, 10.0),
    ("oil", "5-litre", 600.0, 20.0),
])
def test_generic_bulk_switch_budget_note(item_name, bulk_unit, bulk_price, predicted_cycle):
    # 1. Prepare DB state (Sandbox by clearing existing rows first)
    import sqlite3
    import app.main
    import datetime
    
    conn = sqlite3.connect(app.main.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM order_history;")
    cursor.execute("DELETE FROM patterns;")
    cursor.execute("DELETE FROM approvals;")
    conn.commit()
    conn.close()
    
    conn = sqlite3.connect(app.main.DB_PATH)
    cursor = conn.cursor()
    # Check if item exists in items table
    cursor.execute("SELECT id FROM items WHERE canonical_name = ?;", (item_name,))
    item_row = cursor.fetchone()
    assert item_row is not None
    item_id = item_row[0]
    
    # Insert a pattern for the item
    cursor.execute("""
        INSERT INTO patterns (item_name, predicted_cycle_days, confidence, status, item_id)
        VALUES (?, ?, ?, ?, ?);
    """, (item_name, predicted_cycle, 0.9, "active", item_id))
    conn.commit()
    conn.close()
    
    # 2. Mock order placement that simulates a bulk switch
    # First, seed an order with a standard unit (e.g. "500ml" or "pc")
    # Second, seed a bulk switch order with a different unit (e.g. bulk_unit)
    # Let's place it this week
    now_str = datetime.datetime.now().isoformat()
    
    conn = sqlite3.connect(app.main.DB_PATH)
    cursor = conn.cursor()
    
    # Normal order
    cursor.execute("""
        INSERT INTO order_history (item_name, quantity, unit, price, ordered_at, order_source, item_id)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (item_name, 1.0, "normal-unit", 50.0, now_str, "reorder", item_id))
    
    # Bulk switch order (placed slightly later to be the most recent one)
    later_str = (datetime.datetime.now() + datetime.timedelta(seconds=1)).isoformat()
    cursor.execute("""
        INSERT INTO order_history (item_name, quantity, unit, price, ordered_at, order_source, item_id)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (item_name, 1.0, bulk_unit, bulk_price, later_str, "bulk_switch", item_id))
    conn.commit()
    conn.close()
    
    # 3. Call GET /budget
    response = client.get("/budget")
    assert response.status_code == 200
    data = response.json()
    
    weekly_items = data["weekly_items"]
    
    # Find entries for this item
    entries = [item for item in weekly_items if item["item_name"] == item_name]
    
    # We grouped by (item_name, unit), so we expect exactly two entries!
    assert len(entries) == 2
    
    # Find the bulk switch entry
    bulk_entry = next(e for e in entries if e["unit"] == bulk_unit)
    assert bulk_entry["total_cost"] == bulk_price
    assert bulk_entry["note"] is not None
    assert f"won't need to reorder for about {int(round(predicted_cycle))} days" in bulk_entry["note"]
    
    # Find the normal entry
    normal_entry = next(e for e in entries if e["unit"] == "normal-unit")
    assert normal_entry["total_cost"] == 50.0
    assert normal_entry["note"] is None
    
    # Assert (a) order_source gets saved correctly
    conn = sqlite3.connect(app.main.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT order_source FROM order_history WHERE item_name = ? AND unit = ?;", (item_name, bulk_unit))
    val = cursor.fetchone()[0]
    conn.close()
    assert val == "bulk_switch"

def test_all_panels_display_name_consistency():
    # 1. Fetch `/state`
    response = client.get("/state")
    assert response.status_code == 200
    state = response.json()
    
    # 2. Get the display name map from items table
    import sqlite3
    import app.main
    conn = sqlite3.connect(app.main.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, display_name FROM items;")
    display_names_map = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    
    # 3. Check patterns list
    for p in state["patterns"]:
        item_id = p.get("item_id")
        if item_id in display_names_map:
            assert p["display_name"] == display_names_map[item_id]
            
    # 4. Check approvals list
    for a in state["approvals"]:
        item_id = a.get("item_id")
        if item_id in display_names_map:
            assert a["display_name"] == display_names_map[item_id]
            
    # 5. Check budget weekly_items breakdown
    for item in state["budget"]["weekly_items"]:
        item_id = item.get("item_id")
        if item_id in display_names_map:
            assert item["display_name"] == display_names_map[item_id]
            
    # 6. Check persona top_items
    for top_item in state["persona"]["latest"]["top_items"]:
        assert top_item in display_names_map.values()
