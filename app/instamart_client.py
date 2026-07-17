import os
import re
import json
import urllib.request
from typing import Any

# Default config configuration flags
USE_MOCK_DATA_DEFAULT = "True"

def parse_pack_size(pack_size_str: str) -> tuple[float, str]:
    """
    Parses a pack size string (like '500 ml', '1.5 kg', '6 pcs', '1')
    and returns a tuple of (numeric_value, unit).
    """
    if not pack_size_str:
        return 1.0, "pc"
    pack_size_str = pack_size_str.strip()
    match = re.match(r"([\d\.]+)\s*([a-zA-Z]*)", pack_size_str)
    if match:
        try:
            val = float(match.group(1))
            unit = match.group(2).lower() or "pc"
            return val, unit
        except ValueError:
            pass
    return 1.0, "pc"

def _call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Issues a JSON-RPC request to call a tool on the Swiggy Instamart MCP server.
    """
    url = "https://mcp.swiggy.com/im"
    token = os.getenv("SWIGGY_ACCESS_TOKEN")
    if not token:
        raise ValueError("SWIGGY_ACCESS_TOKEN environment variable is not set.")
        
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": 1
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    with urllib.request.urlopen(req, timeout=10) as response:
        resp_data = response.read().decode("utf-8")
        return json.loads(resp_data)

def get_order_history() -> list[dict[str, Any]]:
    """
    Wraps the get_orders tool. Normalizes responses to match the order_history 
    schema from Phase 1.
    If USE_MOCK_DATA env var is set to True (default), it reads directly from the SQLite 
    database's order_history table.
    """
    use_mock = os.getenv("USE_MOCK_DATA", USE_MOCK_DATA_DEFAULT).lower() == "true"
    if use_mock:
        from app.db import get_db_connection
        db_path = os.getenv("DB_PATH", "test.db")
        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"Database file not found at '{db_path}'. Please initialize and seed the DB first."
            )
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, item_name, quantity, unit, price, ordered_at FROM order_history;")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
        
    # Live tool execution
    resp = _call_mcp_tool("get_orders", {})
    result = resp.get("result", {})
    
    orders = []
    if "content" in result:
        for c in result["content"]:
            if c.get("type") == "text" and c.get("text"):
                try:
                    orders = json.loads(c["text"])
                    break
                except Exception:
                    pass
    else:
        orders = result.get("orders", result)
        if not isinstance(orders, list):
            orders = [orders]
            
    normalized_items = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        ordered_at = order.get("ordered_at") or order.get("created_at") or order.get("date") or ""
        items_list = order.get("items") or order.get("order_items") or order.get("products") or []
        order_id = order.get("id") or order.get("order_id")
        
        for item in items_list:
            if not isinstance(item, dict):
                continue
            normalized_items.append({
                "id": item.get("id") or order_id,
                "item_name": item.get("name") or item.get("item_name") or "",
                "quantity": float(item.get("quantity") or item.get("qty") or 1.0),
                "unit": item.get("unit") or item.get("pack_size") or "pc",
                "price": float(item.get("price") or item.get("amount") or 0.0),
                "ordered_at": ordered_at
            })
            
    return normalized_items

def find_pack_size_options(item_name: str) -> list[dict[str, Any]]:
    """
    Wraps search_products tool. Returns product variants with parsed fields and price_per_unit.
    """
    resp = _call_mcp_tool("search_products", {"query": item_name})
    result = resp.get("result", {})
    
    products = []
    if "content" in result:
        for c in result["content"]:
            if c.get("type") == "text" and c.get("text"):
                try:
                    products = json.loads(c["text"])
                    break
                except Exception:
                    pass
    else:
        products = result.get("products", result)
        if not isinstance(products, list):
            products = [products]
            
    variants_list = []
    for prod in products:
        if not isinstance(prod, dict):
            continue
        prod_name = prod.get("name", "")
        variants = prod.get("variants") or [prod]
        
        for var in variants:
            if not isinstance(var, dict):
                continue
            spin_id = var.get("spin_id") or var.get("variant_id") or var.get("id") or ""
            pack_size = var.get("pack_size") or var.get("unit") or ""
            price = float(var.get("price") or var.get("amount") or 0.0)
            
            val, unit = parse_pack_size(pack_size)
            price_per_unit = round(price / val, 4) if val > 0.0 else price
            
            variants_list.append({
                "variant_id": spin_id,
                "item_name": f"{prod_name} ({pack_size})" if prod_name and pack_size else (prod_name or pack_size),
                "pack_size": pack_size,
                "price": price,
                "price_per_unit": price_per_unit,
                "unit": unit
            })
            
    return variants_list

def get_frequent_items() -> list[dict[str, Any]]:
    """
    Wraps the your_go_to_items tool. Returns frequently purchased items list.
    """
    resp = _call_mcp_tool("your_go_to_items", {})
    result = resp.get("result", {})
    
    items = []
    if "content" in result:
        for c in result["content"]:
            if c.get("type") == "text" and c.get("text"):
                try:
                    items = json.loads(c["text"])
                    break
                except Exception:
                    pass
    else:
        items = result.get("items", result)
        if not isinstance(items, list):
            items = [items]
    return items

def build_cart(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Wraps the update_cart tool.
    """
    resp = _call_mcp_tool("update_cart", {"items": items})
    return resp.get("result", resp)

def place_order() -> dict[str, Any]:
    """
    Wraps the checkout tool.
    
    WARNING: THIS FUNCTION TRIGGERS A REAL FINANCIAL TRANSACTION/ORDER PLACEMENT.
    IT MUST ONLY EVER BE CALLED AFTER EXPLICIT HUMAN CONFIRMATION.
    DO NOT CALL THIS AUTOMATICALLY OR FROM ANY UNIT TEST.
    """
    resp = _call_mcp_tool("checkout", {})
    return resp.get("result", resp)
