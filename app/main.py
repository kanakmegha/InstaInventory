import os
import datetime
import json
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Any, Optional

from app.db import get_db_connection, init_db
from app.seed import seed_mock_orders
from app.pattern_detection import detect_patterns
from app.budget_engine import check_budget, create_approval, save_approval, respond_to_approval
from app.instamart_client import get_order_history, find_pack_size_options, build_cart, place_order
from app.pack_optimizer import suggest_pack_size
from app.persona import build_persona_snapshot, save_persona_snapshot
from app.copy import (
    COPY_DICT,
    get_confirm_pattern_msg,
    get_reject_pattern_msg,
    get_edit_cycle_msg,
    get_approve_approval_msg,
    get_decline_approval_msg,
    get_update_budget_cap_msg,
    get_reorder_explanation,
    get_drift_explanation,
    get_bulk_explanation,
    get_display_name,
    ERROR_PATTERN_NOT_FOUND,
    ERROR_APPROVAL_NOT_FOUND,
    ERROR_CHECKOUT_FAILED
)

# Define FastAPI application
app = FastAPI(title="InstaInventory API")

# Ensure database is initialized at startup
DB_PATH = os.getenv("DB_PATH", "test.db")

@app.on_event("startup")
def on_startup():
    """
    On startup, initialize and seed database if empty.
    """
    init_db(DB_PATH)
    # Check if we should seed orders
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM order_history;")
    count = cursor.fetchone()[0]
    if count == 0:
        seed_mock_orders(DB_PATH)
        
    # Pre-populate some patterns if empty
    cursor.execute("SELECT COUNT(*) FROM patterns;")
    pat_count = cursor.fetchone()[0]
    if pat_count == 0:
        orders = get_order_history()
        detected = detect_patterns(orders)
        for p in detected:
            cursor.execute("SELECT id FROM items WHERE canonical_name = ?;", (p["item_name"],))
            item_row = cursor.fetchone()
            item_id = item_row["id"] if item_row else None
            
            cursor.execute("""
                INSERT INTO patterns (item_name, predicted_cycle_days, confidence, status, last_confirmed_at, item_id)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (p["item_name"], p["predicted_cycle_days"], p["confidence"], "active", None, item_id))
            
    # Pre-populate some approvals if empty
    cursor.execute("SELECT COUNT(*) FROM approvals WHERE user_response = 'pending';")
    app_count = cursor.fetchone()[0]
    if app_count == 0:
        # Pre-seed typical reorder, pack-size suggestion, and check-in approvals
        # 1. Milk reorder
        cursor.execute("SELECT id, item_id FROM patterns WHERE item_name = 'milk' LIMIT 1;")
        milk_row = cursor.fetchone()
        if milk_row:
            cursor.execute("""
                INSERT INTO approvals (pattern_id, proposed_date, proposed_cost, user_response, responded_at, item_id)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (milk_row["id"], (datetime.date.today() + datetime.timedelta(days=1)).isoformat(), 54.0, "pending", None, milk_row["item_id"]))
            
        # 2. Tomato pack-size suggestion
        cursor.execute("SELECT id, item_id FROM patterns WHERE item_name = 'tomato' LIMIT 1;")
        tomato_row = cursor.fetchone()
        if tomato_row:
            cursor.execute("""
                INSERT INTO approvals (pattern_id, proposed_date, proposed_cost, user_response, responded_at, item_id)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (tomato_row["id"], (datetime.date.today() + datetime.timedelta(days=3)).isoformat(), 45.0, "pending", None, tomato_row["item_id"]))
            
        # 3. Onion check-in (drifted status)
        cursor.execute("SELECT id, item_id FROM patterns WHERE item_name = 'onion' LIMIT 1;")
        onion_row = cursor.fetchone()
        if onion_row:
            cursor.execute("UPDATE patterns SET status = 'drifted' WHERE id = ?;", (onion_row["id"],))
            cursor.execute("""
                INSERT INTO approvals (pattern_id, proposed_date, proposed_cost, user_response, responded_at, item_id)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (onion_row["id"], (datetime.date.today() + datetime.timedelta(days=5)).isoformat(), 35.0, "pending", None, onion_row["item_id"]))
            
    conn.commit()
    conn.close()

# Pydantic schemas for request validation
class EditCycleSchema(BaseModel):
    predicted_cycle_days: float

class UpdateCapSchema(BaseModel):
    weekly_cap: float

# Routes

@app.get("/", response_class=HTMLResponse)
def read_root():
    """
    Serves the static instainventory_demo.html dashboard frontend.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "instainventory_demo.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="instainventory_demo.html not found.")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/state")
def get_state_endpoint():
    """
    Returns the full state payload containing patterns, approvals, budget, persona, and copy.
    """
    return {
        "patterns": get_patterns_endpoint(),
        "approvals": get_approvals_endpoint(),
        "budget": get_budget_endpoint(),
        "persona": get_persona_endpoint(),
        "copy": COPY_DICT
    }

def get_state_payload(status: str = "success", message: str = ""):
    state = get_state_endpoint()
    state["status"] = status
    state["message"] = message
    return state

@app.get("/patterns")
def get_patterns_endpoint():
    """
    Returns all detected grocery patterns with their current statuses.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.item_name, p.predicted_cycle_days, p.confidence, p.status, p.last_confirmed_at, p.item_id, i.display_name
        FROM patterns p
        LEFT JOIN items i ON p.item_id = i.id;
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/patterns/{pattern_id}/confirm")
def confirm_pattern_endpoint(pattern_id: int):
    """
    Confirms a detected restocking pattern. Sets status to 'active' and updates last_confirmed_at.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patterns WHERE id = ?;", (pattern_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Pattern with ID {pattern_id} not found.")
        
    now_str = datetime.datetime.now().isoformat()
    cursor.execute("UPDATE patterns SET status = 'active', last_confirmed_at = ? WHERE id = ?;", (now_str, pattern_id))
    conn.commit()
    conn.close()
    payload = get_state_payload(status="success", message=get_confirm_pattern_msg(pattern_id))
    payload["last_confirmed_at"] = now_str
    return payload

@app.post("/patterns/{pattern_id}/reject")
def reject_pattern_endpoint(pattern_id: int):
    """
    Rejects a detected restocking pattern. Sets status to 'dismissed'.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patterns WHERE id = ?;", (pattern_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=ERROR_PATTERN_NOT_FOUND)
        
    cursor.execute("UPDATE patterns SET status = 'dismissed' WHERE id = ?;", (pattern_id,))
    conn.commit()
    conn.close()
    return get_state_payload(status="success", message=get_reject_pattern_msg(pattern_id))

@app.post("/patterns/{pattern_id}/edit-cycle")
def edit_cycle_endpoint(pattern_id: int, body: EditCycleSchema):
    """
    Edits the cycle frequency in days for a pattern.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patterns WHERE id = ?;", (pattern_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=ERROR_PATTERN_NOT_FOUND)
        
    cursor.execute("UPDATE patterns SET predicted_cycle_days = ? WHERE id = ?;", (body.predicted_cycle_days, pattern_id))
    conn.commit()
    conn.close()
    return get_state_payload(status="success", message=get_edit_cycle_msg(pattern_id, body.predicted_cycle_days))

@app.get("/approvals")
def get_approvals_endpoint():
    """
    Lists pending approvals (reorders, pack-size suggestions, or check-ins).
    Classifies type dynamically based on pattern status and cost differences.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.pattern_id, p.item_name, p.status as pattern_status, 
               p.predicted_cycle_days, p.confidence, a.proposed_date, a.proposed_cost,
               a.item_id, i.display_name
        FROM approvals a
        JOIN patterns p ON a.pattern_id = p.id
        LEFT JOIN items i ON a.item_id = i.id
        WHERE a.user_response = 'pending';
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    
    # Classify type dynamically
    results = []
    for item in rows:
        item_name = item["item_name"]
        display_name = item["display_name"] or get_display_name(item_name)
        
        # 1. Check if pattern drifted -> check_in
        if item["pattern_status"] == "drifted":
            app_type = "check_in"
            # Recompute using detect_patterns() logic against the most recent gaps between orders
            cursor.execute("SELECT item_name, quantity, unit, price, ordered_at FROM order_history WHERE item_name = ? ORDER BY ordered_at DESC LIMIT 5;", (item_name,))
            recent_orders_drift = [dict(r) for r in cursor.fetchall()]
            recent_orders_drift.reverse()
            
            gaps = []
            for i in range(len(recent_orders_drift) - 1):
                from datetime import datetime
                def parse_dt(v):
                    if isinstance(v, datetime):
                        return v
                    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                dt1 = parse_dt(recent_orders_drift[i]["ordered_at"])
                dt2 = parse_dt(recent_orders_drift[i + 1]["ordered_at"])
                gaps.append((dt2 - dt1).total_seconds() / 86400.0)
            if gaps:
                item["suggested_cycle_days"] = round(sum(gaps) / len(gaps), 1)
            else:
                item["suggested_cycle_days"] = round(item["predicted_cycle_days"], 1)
                
            item["explanation"] = get_drift_explanation(display_name, int(round(item["suggested_cycle_days"])))
        else:
            # 2. Check if it has a pack-size suggestion savings
            # Query recent order history
            cursor.execute("SELECT item_name, quantity, unit, price, ordered_at FROM order_history WHERE item_name = ?;", (item_name,))
            recent_orders = [dict(r) for r in cursor.fetchall()]
            
            # Fetch pack options
            pack_options = find_pack_size_options(item_name)
            
            # Suggest pack size
            suggestion = suggest_pack_size(item_name, recent_orders, pack_options)
            if suggestion:
                app_type = "pack_size_suggestion"
                item["suggested_pack"] = suggestion["suggested_pack"]
                item["savings"] = suggestion["savings"]
                item["current_total_cost"] = suggestion["current_monthly_cost"]
                item["suggested_total_cost"] = suggestion["suggested_monthly_cost"]
                item["current_frequency_days"] = suggestion["current_frequency_days"]
                item["suggested_frequency_days"] = suggestion["suggested_frequency_days"]
                item["usual_order_price"] = suggestion["current_price_per_pack"]
                item["usual_order_desc"] = suggestion["current_pack_desc"]
                
                # Derive total packs bought
                if suggestion["current_price_per_pack"] > 0:
                    total_packs = int(round(suggestion["current_monthly_cost"] / suggestion["current_price_per_pack"]))
                else:
                    total_packs = 1
                item["explanation"] = get_bulk_explanation(
                    item_name=display_name,
                    total_packs=total_packs,
                    usual_unit=suggestion["current_pack_desc"],
                    suggested_pack_size=suggestion["suggested_pack"].get("pack_size", "")
                )
            else:
                app_type = "reorder"
                item["explanation"] = get_reorder_explanation(display_name, int(round(item["predicted_cycle_days"])))
                
        item["type"] = app_type
        # Strip internal flag before returning
        item.pop("pattern_status", None)
        results.append(item)
        
    conn.close()
    return results

@app.post("/approvals/{approval_id}/approve")
def approve_reorder_endpoint(approval_id: int):
    """
    Approves a restocking/pack suggestion:
    1. Triggers Instamart build_cart and place_order.
    2. Marks the approval response as 'approved' and updates responded_at.
    3. Persists the placed order in order_history.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM approvals WHERE id = ? AND user_response = 'pending';", (approval_id,))
    app_row = cursor.fetchone()
    if not app_row:
        conn.close()
        raise HTTPException(status_code=404, detail=ERROR_APPROVAL_NOT_FOUND)
        
    pattern_id = app_row["pattern_id"]
    cursor.execute("SELECT item_name, item_id FROM patterns WHERE id = ?;", (pattern_id,))
    pat_row = cursor.fetchone()
    item_name = pat_row["item_name"] if pat_row else "Grocery Item"
    item_id = pat_row["item_id"] if pat_row else None
    
    # 1. Fetch recent orders and check if there is a pack-size suggestion
    cursor.execute("SELECT item_name, quantity, unit, price, ordered_at FROM order_history WHERE item_name = ?;", (item_name,))
    recent_orders = [dict(r) for r in cursor.fetchall()]
    
    # Fetch pack options
    pack_options = find_pack_size_options(item_name)
    
    # Check if this item had a pack suggestion
    suggestion = suggest_pack_size(item_name, recent_orders, pack_options)
    
    if suggestion:
        # It's a pack-size suggestion!
        suggested_pack = suggestion["suggested_pack"]
        from app.instamart_client import parse_pack_size
        qty, unit = parse_pack_size(suggested_pack.get("pack_size", ""))
        price = float(suggested_pack.get("price", 0.0))
        
        # Automatically update the pattern's predicted_cycle_days to suggested_frequency_days
        new_cycle = float(suggestion["suggested_frequency_days"])
        cursor.execute("UPDATE patterns SET predicted_cycle_days = ? WHERE id = ?;", (new_cycle, pattern_id))
        order_source = "bulk_switch"
    else:
        # Standard reorder or check-in
        cursor.execute("SELECT quantity, unit FROM order_history WHERE item_name = ? ORDER BY ordered_at DESC LIMIT 1;", (item_name,))
        history_row = cursor.fetchone()
        qty = history_row["quantity"] if history_row else 1.0
        unit = history_row["unit"] if history_row else "pc"
        price = float(app_row["proposed_cost"])
        order_source = "reorder"
        
    # Call Instamart MCP client functions
    cart_items = [{"name": item_name, "quantity": qty, "unit": unit}]
    try:
        build_cart(cart_items)
        order_res = place_order()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=ERROR_CHECKOUT_FAILED)
        
    # Insert new order into order_history
    if order_res and order_res.get("status") == "success":
        now_str = datetime.datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO order_history (item_name, quantity, unit, price, ordered_at, order_source, item_id)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (item_name, qty, unit, price, now_str, order_source, item_id))
        conn.commit()
        
    conn.close()
    
    # Persist the approval response
    respond_to_approval(DB_PATH, approval_id, "approved")
    
    payload = get_state_payload(status="success", message=get_approve_approval_msg(approval_id))
    payload["item"] = item_name
    return payload

@app.post("/approvals/{approval_id}/decline")
def decline_reorder_endpoint(approval_id: int):
    """
    Declines a restocking suggestion. Sets response to 'declined'.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM approvals WHERE id = ? AND user_response = 'pending';", (approval_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=ERROR_APPROVAL_NOT_FOUND)
    conn.close()
    
    respond_to_approval(DB_PATH, approval_id, "declined")
    return get_state_payload(status="success", message=get_decline_approval_msg(approval_id))

@app.get("/budget")
def get_budget_endpoint():
    """
    Returns weekly budget stats: current spend (since Monday of current week), weekly cap, remaining spend, overage, and the items breakdown.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Monday of current week
    today = datetime.date.today()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    start_of_week_str = start_of_week.isoformat() + "T00:00:00"
    
    cursor.execute("""
        SELECT o.item_name, o.unit, SUM(o.quantity) as qty_sum, SUM(o.price) as cost_sum, o.item_id, i.display_name
        FROM order_history o
        LEFT JOIN items i ON o.item_id = i.id
        WHERE o.ordered_at >= ?
        GROUP BY o.item_name, o.unit, o.item_id
        ORDER BY cost_sum DESC;
    """, (start_of_week_str,))
    rows = cursor.fetchall()
    
    weekly_items = []
    for r in rows:
        qty_sum = r["qty_sum"] if r["qty_sum"] is not None else 0.0
        cost_sum = r["cost_sum"] if r["cost_sum"] is not None else 0.0
        item_name = r["item_name"]
        unit = r["unit"]
        item_id = r["item_id"]
        display_name = r["display_name"] or get_display_name(item_name)
        
        # Check most recent order this week for this item + unit to see if order_source is bulk_switch
        cursor.execute("""
            SELECT order_source
            FROM order_history
            WHERE item_name = ? AND unit = ? AND ordered_at >= ?
            ORDER BY ordered_at DESC
            LIMIT 1;
        """, (item_name, unit, start_of_week_str))
        last_order = cursor.fetchone()
        source = last_order["order_source"] if last_order else None
        
        note = None
        if source == "bulk_switch":
            cursor.execute("SELECT predicted_cycle_days FROM patterns WHERE item_name = ?;", (item_name,))
            pat_row = cursor.fetchone()
            cycle = pat_row["predicted_cycle_days"] if pat_row else 30.0
            note = f"Bought in bulk — likely won't need to reorder for about {int(round(cycle))} days"
            
        weekly_items.append({
            "item_name": item_name,
            "display_name": display_name,
            "quantity": round(qty_sum, 1) if qty_sum % 1 != 0 else int(qty_sum),
            "total_cost": round(cost_sum, 2),
            "unit": unit,
            "item_id": item_id,
            "note": note
        })
        
    cursor.execute("SELECT budget_cap_weekly FROM users WHERE id = 1;")
    user_row = cursor.fetchone()
    weekly_cap = user_row["budget_cap_weekly"] if user_row else 1500.0
    conn.close()
    
    current_week_spend = sum(item["total_cost"] for item in weekly_items)
    projected = check_budget(0.0, current_week_spend, weekly_cap)
    
    return {
        "current_week_spend": round(current_week_spend, 2),
        "weekly_cap": round(weekly_cap, 2),
        "remaining": round(max(0.0, weekly_cap - current_week_spend), 2),
        "overage": projected["overage"],
        "weekly_items": weekly_items
    }

@app.post("/budget/cap")
def update_budget_cap_endpoint(body: UpdateCapSchema):
    """
    Updates the weekly budget cap for the user.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE id = 1;")
    user_exists = cursor.fetchone()
    
    if user_exists:
        cursor.execute("UPDATE users SET budget_cap_weekly = ? WHERE id = 1;", (body.weekly_cap,))
    else:
        cursor.execute("INSERT INTO users (id, budget_cap_weekly) VALUES (1, ?);", (body.weekly_cap,))
        
    conn.commit()
    conn.close()
    return get_state_payload(status="success", message=get_update_budget_cap_msg(body.weekly_cap))

@app.get("/persona")
def get_persona_endpoint():
    """
    Returns the latest persona snapshot (builds one dynamically from live data)
    and the full timeline of past snapshots.
    """
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Fetch current order_history and approvals data
    cursor.execute("SELECT item_name, quantity, unit, price, ordered_at FROM order_history;")
    orders = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT pattern_id, proposed_date, proposed_cost, user_response, responded_at FROM approvals;")
    approvals_list = [dict(r) for r in cursor.fetchall()]
    
    # Current week is the Monday of the current week
    today = datetime.date.today()
    current_week_monday = today - datetime.timedelta(days=today.weekday())
    
    # Check what historical weeks are missing from DB
    missing_weeks = []
    if orders:
        def parse_date_only(v):
            if isinstance(v, datetime.datetime):
                return v.date()
            if isinstance(v, datetime.date):
                return v
            return datetime.date.fromisoformat(str(v).split("T")[0])
            
        dates = []
        for o in orders:
            try:
                dates.append(parse_date_only(o["ordered_at"]))
            except Exception:
                pass
        if dates:
            min_date = min(dates)
            curr = min_date - datetime.timedelta(days=min_date.weekday())
            while curr < current_week_monday:
                cursor.execute("SELECT 1 FROM persona_snapshots WHERE week_of = ?;", (curr.isoformat(),))
                if not cursor.fetchone():
                    missing_weeks.append(curr)
                curr += datetime.timedelta(days=7)
                
    conn.close() # Close read connection to prevent database lock
    
    # Persist missing historical weeks
    if missing_weeks:
        def parse_dt(v):
            if isinstance(v, datetime.datetime):
                return v
            return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00").split("+")[0])
            
        for w in missing_weeks:
            end_dt = datetime.datetime.combine(w + datetime.timedelta(days=7), datetime.time.min)
            
            # Filter orders/approvals up to the end of that historical week
            f_orders = []
            for o in orders:
                try:
                    if parse_dt(o["ordered_at"]) < end_dt:
                        f_orders.append(o)
                except Exception:
                    f_orders.append(o)
                    
            f_apprs = []
            for a in approvals_list:
                try:
                    resp_at = a.get("responded_at")
                    if resp_at:
                        if parse_dt(resp_at) < end_dt:
                            f_apprs.append(a)
                    else:
                        prop_date = datetime.datetime.strptime(a["proposed_date"], "%Y-%m-%d")
                        if prop_date < end_dt:
                            f_apprs.append(a)
                except Exception:
                    f_apprs.append(a)
                    
            past_snap = build_persona_snapshot(w, f_orders, f_apprs)
            save_persona_snapshot(DB_PATH, past_snap)
            
    # Build the fresh snapshot for the current week dynamically
    current_snapshot = build_persona_snapshot(current_week_monday, orders, approvals_list)
    
    # Fetch historical snapshots from DB
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM persona_snapshots WHERE week_of < ? ORDER BY week_of DESC;", (current_week_monday.isoformat(),))
    historical_snapshots = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Fetch display name mapping from items table
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT canonical_name, display_name FROM items;")
    display_map = {row["canonical_name"]: row["display_name"] for row in cursor.fetchall()}
    conn.close()
    
    # Combine to timeline
    snapshots = [current_snapshot] + historical_snapshots
    
    # Parse top items json string for each snapshot and translate
    for snap in snapshots:
        try:
            top_names = json.loads(snap["top_items_json"]) if snap.get("top_items_json") else []
        except (json.JSONDecodeError, TypeError):
            top_names = []
        snap["top_items"] = [display_map.get(name, get_display_name(name)) for name in top_names]
        snap["top_items_json"] = json.dumps(snap["top_items"])
            
    latest = current_snapshot
    return {
        "latest": latest,
        "timeline": snapshots
    }
