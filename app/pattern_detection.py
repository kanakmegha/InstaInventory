import math
from datetime import datetime
from typing import Any

def detect_patterns(order_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    For each unique item_name in order_history:
    1. Sort orders by ordered_at
    2. Compute the gap in days between consecutive orders
    3. predicted_cycle_days = mean of the gaps
    4. confidence = a score between 0 and 1 based on:
       (a) how many repeat orders exist (gaps count)
       (b) how low the variance in gaps is (Coefficient of Variation)
    5. Only include items with at least 2 orders in the output
    6. Return a list of dicts: {item_name, predicted_cycle_days, confidence, order_count}
    """
    # Group orders by item_name
    grouped_orders: dict[str, list[dict[str, Any]]] = {}
    for order in order_history:
        name = order.get("item_name")
        if not name:
            continue
        if name not in grouped_orders:
            grouped_orders[name] = []
        grouped_orders[name].append(order)
        
    results = []
    
    for item_name, orders in grouped_orders.items():
        if len(orders) < 2:
            # Cannot compute gap from 1 order
            continue
            
        # Helper to parse ISO8601 string to datetime
        def parse_date(date_val: Any) -> datetime:
            if isinstance(date_val, datetime):
                return date_val
            # Handle standard 'Z' suffix compatibility for older Python versions
            cleaned_str = str(date_val).replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned_str)
            
        # 1. Sort orders by ordered_at
        try:
            sorted_orders = sorted(orders, key=lambda x: parse_date(x["ordered_at"]))
        except Exception:
            sorted_orders = sorted(orders, key=lambda x: str(x.get("ordered_at", "")))
            
        # 2. Compute gaps in days between consecutive orders
        gaps = []
        for i in range(len(sorted_orders) - 1):
            dt1 = parse_date(sorted_orders[i]["ordered_at"])
            dt2 = parse_date(sorted_orders[i + 1]["ordered_at"])
            gap_days = (dt2 - dt1).total_seconds() / 86400.0
            gaps.append(gap_days)
            
        # 3. Compute predicted cycle days (mean of gaps)
        gaps_count = len(gaps)
        predicted_cycle_days = sum(gaps) / gaps_count
        
        # 4. Calculate confidence score (0.0 to 1.0)
        #
        # (a) count_factor:
        #     Rewards having more observation data. Having only 1 gap (2 orders) gives 
        #     very low certainty, while 4+ gaps (5+ orders) reaches full confidence potential.
        #     Formula: count_factor = min(1.0, 0.4 + 0.15 * gaps_count)
        #     - 1 gap: 0.55
        #     - 2 gaps: 0.70
        #     - 3 gaps: 0.85
        #     - 4+ gaps: 1.00
        count_factor = min(1.0, 0.4 + 0.15 * gaps_count)
        
        # (b) variance_factor:
        #     Penalizes deviation in interval gaps. Standard deviation (std_dev) is computed.
        #     We normalize it by dividing by the mean gap to get the Coefficient of Variation (CV).
        #     If gaps are highly regular, CV is small, so variance_factor is high (approaching 1.0).
        #     If gaps are highly irregular, CV is large, so variance_factor is low (approaching 0.0).
        #     If gaps_count is 1, variance/std_dev is undefined; we default variance_factor to 1.0.
        if gaps_count <= 1:
            variance_factor = 1.0
        else:
            mean_gap = predicted_cycle_days
            if mean_gap <= 0:
                variance_factor = 0.0
            else:
                variance = sum((g - mean_gap) ** 2 for g in gaps) / gaps_count
                std_dev = math.sqrt(variance)
                cv = std_dev / mean_gap
                variance_factor = max(0.0, 1.0 - cv)
                
        # Final confidence is the combination of the volume and regularness factors
        confidence = count_factor * variance_factor
        
        results.append({
            "item_name": item_name,
            "predicted_cycle_days": predicted_cycle_days,
            "confidence": confidence,
            "order_count": len(sorted_orders)
        })
        
    return results

def detect_drift(pattern: dict[str, Any], recent_responses: list[str]) -> bool:
    """
    Returns True if the last 2 or more responses in recent_responses are "declined".
    Signals that the pattern might be stale.
    """
    if len(recent_responses) < 2:
        return False
    # Check the last two elements (most recent responses chronologically)
    return recent_responses[-1].lower() == "declined" and recent_responses[-2].lower() == "declined"
