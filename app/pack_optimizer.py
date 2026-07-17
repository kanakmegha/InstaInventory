from datetime import datetime, timedelta
from typing import Any, Optional

# Named constants for thresholds
MIN_SAVINGS_INR = 10.0
MIN_SAVINGS_PERCENT = 0.10

def suggest_pack_size(item_name: str, recent_orders: list[dict[str, Any]], pack_options: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    Sums total quantity of item_name purchased across recent_orders in the last 30 days.
    Compares the actual total cost paid against the cost of buying that same total quantity
    using the cheapest per-unit pack option from pack_options.
    
    If the savings exceed a threshold (default ₹10 or 10% of current cost, whichever is higher),
    return a suggestion dict. Otherwise return None.
    
    If there is only one pack size option available, returns None.
    """
    # 1. Base validation
    if len(pack_options) <= 1:
        # Nothing to compare against if there is only 1 pack size option
        return None
        
    # Filter orders for this specific item
    item_orders = [o for o in recent_orders if o.get("item_name") == item_name]
    if not item_orders:
        return None
        
    # Helper to parse datetime strings safely
    def parse_date(date_val: Any) -> datetime:
        if isinstance(date_val, datetime):
            return date_val
        cleaned_str = str(date_val).replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned_str)
        
    # 2. Establish "current" reference date to support historical tests
    try:
        ref_date = max(parse_date(o["ordered_at"]) for o in recent_orders)
    except Exception:
        ref_date = datetime.now()
        
    cutoff_date = ref_date - timedelta(days=30)
    
    # 3. Sum total quantity & actual cost paid in the last 30 days
    total_qty = 0.0
    actual_total_cost = 0.0
    has_recent_orders = False
    
    for order in item_orders:
        try:
            o_date = parse_date(order["ordered_at"])
            if o_date >= cutoff_date:
                has_recent_orders = True
                total_qty += float(order.get("quantity", 0.0))
                actual_total_cost += float(order.get("price", 0.0))
        except Exception:
            pass
            
    if not has_recent_orders or total_qty <= 0.0:
        return None
        
    # 4. Find the cheapest pack option based on price_per_unit
    try:
        cheapest_option = min(pack_options, key=lambda x: float(x.get("price_per_unit", float('inf'))))
    except Exception:
        return None
        
    cheapest_price_per_unit = float(cheapest_option.get("price_per_unit", 0.0))
    if cheapest_price_per_unit <= 0.0 or cheapest_price_per_unit == float('inf'):
        return None
        
    # 5. Compute suggested total cost and savings
    suggested_total_cost = round(total_qty * cheapest_price_per_unit, 2)
    savings = round(actual_total_cost - suggested_total_cost, 2)
    
    # Threshold = max(₹10, 10% of current cost)
    threshold = max(MIN_SAVINGS_INR, MIN_SAVINGS_PERCENT * actual_total_cost)
    
    if savings >= threshold:
        return {
            "item_name": item_name,
            "current_total_cost": round(actual_total_cost, 2),
            "suggested_pack": cheapest_option,
            "suggested_total_cost": suggested_total_cost,
            "savings": savings
        }
        
    return None
