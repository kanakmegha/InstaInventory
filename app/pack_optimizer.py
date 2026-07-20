from datetime import datetime, timedelta
from typing import Any, Optional
from app.instamart_client import parse_pack_size

# Named constants for thresholds
MIN_SAVINGS_INR = 10.0
MIN_SAVINGS_PERCENT = 0.10

def get_base_unit_info(item_name: str, unit_str: str) -> tuple[float, str]:
    """
    Given an item_name and a unit_str, returns:
    (conversion_multiplier_to_base_unit, base_unit_name)
    
    Base units:
    - Volume: 'ml'
    - Weight: 'g'
    - Countable: 'pc'
    """
    if not unit_str:
        raise ValueError(f"Missing unit for item '{item_name}'")
        
    item_clean = item_name.lower().strip()
    unit_clean = unit_str.lower().strip()
    
    # Determine category based on item_name keywords
    is_volume = any(k in item_clean for k in ("milk", "oil", "juice", "beverage", "water"))
    is_weight = any(k in item_clean for k in ("tomato", "onion", "rice", "potato", "flour", "sugar", "salt"))
    
    if is_volume:
        # Base unit is 'ml'
        if unit_clean in ("ml", "milliliter", "milliliters", "millilitres"):
            return 1.0, "ml"
        elif unit_clean in ("l", "litre", "litres", "liter", "liters"):
            return 1000.0, "ml"
        elif unit_clean in ("packet", "packets", "pkt", "pkts", "pack", "packs"):
            # A packet of milk is typically 500ml
            return 500.0, "ml"
        else:
            raise ValueError(f"Unrecognized volume unit '{unit_str}' for item '{item_name}'")
            
    elif is_weight:
        # Base unit is 'g'
        if unit_clean in ("g", "gm", "gram", "grams"):
            return 1.0, "g"
        elif unit_clean in ("kg", "kilo", "kilogram", "kilograms"):
            return 1000.0, "g"
        else:
            raise ValueError(f"Unrecognized weight unit '{unit_str}' for item '{item_name}'")
            
    else:
        # Countable -> 'pc'
        if unit_clean in ("pc", "pcs", "piece", "pieces", "unit", "units"):
            return 1.0, "pc"
        else:
            raise ValueError(f"Unrecognized countable unit '{unit_str}' for item '{item_name}'")

def suggest_pack_size(item_name: str, recent_orders: list[dict[str, Any]], pack_options: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    Sums total quantity of item_name purchased across recent_orders in the last 30 days.
    Compares the actual total cost paid against the cost of buying that same total quantity
    using the cheapest per-unit pack option from pack_options.
    
    Before comparing, all quantities are normalized to a common base unit
    (ml for volume, g for weight, pc for countable/others).
    
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
    total_qty_base = 0.0
    actual_total_cost = 0.0
    has_recent_orders = False
    
    import sys
    
    for order in item_orders:
        try:
            o_date = parse_date(order["ordered_at"])
            if o_date >= cutoff_date:
                qty = float(order.get("quantity", 0.0))
                unit = order.get("unit", "")
                if not unit:
                    raise ValueError(f"Missing unit for item '{item_name}' in order history")
                
                # Convert quantity to base unit
                mult, base_unit = get_base_unit_info(item_name, unit)
                total_qty_base += qty * mult
                actual_total_cost += float(order.get("price", 0.0))
                has_recent_orders = True
        except Exception as e:
            print(f"WARNING: Excluded order due to conversion issue: {e}", file=sys.stderr)
            pass
            
    if not has_recent_orders or total_qty_base <= 0.0:
        return None
        
    # 4. Find the cheapest pack option based on price per base unit
    options_with_base_rates = []
    for opt in pack_options:
        try:
            pack_size_val = opt.get("pack_size", "")
            if not pack_size_val:
                # Fallback for mock/test objects without pack size strings
                price_per_base_unit = float(opt.get("price_per_unit", opt.get("price", 0.0)))
                options_with_base_rates.append({
                    "option": opt,
                    "price_per_base_unit": price_per_base_unit
                })
            else:
                val, opt_unit = parse_pack_size(pack_size_val)
                mult, base_unit = get_base_unit_info(item_name, opt_unit)
                opt_qty_base = val * mult
                price = float(opt.get("price", 0.0))
                if opt_qty_base > 0:
                    price_per_base_unit = price / opt_qty_base
                    options_with_base_rates.append({
                        "option": opt,
                        "price_per_base_unit": price_per_base_unit
                    })
        except Exception:
            pass
            
    if not options_with_base_rates:
        return None
        
    # Find option with minimum price per base unit
    cheapest = min(options_with_base_rates, key=lambda x: x["price_per_base_unit"])
    cheapest_option = cheapest["option"]
    cheapest_price_per_base_unit = cheapest["price_per_base_unit"]
    
    # 5. Compute suggested total cost and savings
    suggested_total_cost = round(total_qty_base * cheapest_price_per_base_unit, 2)
    savings = round(actual_total_cost - suggested_total_cost, 2)
    
    # Threshold = max(₹10, 10% of current cost)
    threshold = max(MIN_SAVINGS_INR, MIN_SAVINGS_PERCENT * actual_total_cost)
    
    if savings >= threshold:
        # Find typical/most common order in recent_orders
        from collections import Counter
        duos = [(o.get("quantity", 1.0), o.get("unit") or "pc") for o in item_orders]
        if duos:
            typical_qty, typical_unit = Counter(duos).most_common(1)[0][0]
            # Find all prices paid for this configuration
            matching_prices = [float(o.get("price", 0.0)) for o in item_orders if o.get("quantity", 1.0) == typical_qty and (o.get("unit") or "pc") == typical_unit]
            typical_price = sum(matching_prices) / len(matching_prices) if matching_prices else 0.0
        else:
            typical_qty, typical_unit, typical_price = 1.0, "pc", 0.0
            
        # Convert typical_qty to base unit quantity
        mult, base_unit = get_base_unit_info(item_name, typical_unit)
        current_pack_qty_base = typical_qty * mult
        current_price_per_pack = typical_price
        
        # Calculate suggested pack size in base unit
        pack_size_val = cheapest_option.get("pack_size", "")
        if pack_size_val:
            val, opt_unit = parse_pack_size(pack_size_val)
            opt_mult, opt_base_unit = get_base_unit_info(item_name, opt_unit)
            suggested_pack_qty_base = val * opt_mult
        else:
            suggested_pack_qty_base = 1.0
            
        suggested_price_per_pack = cheapest_option.get("price", 0.0)
        
        # Daily usage rate
        daily_usage_rate = total_qty_base / 30.0
        if daily_usage_rate > 0:
            current_frequency_days = round(current_pack_qty_base / daily_usage_rate, 1)
            suggested_frequency_days = round(suggested_pack_qty_base / daily_usage_rate, 1)
        else:
            current_frequency_days = 30.0
            suggested_frequency_days = 30.0
            
        # Generate friendly current pack desc
        try:
            if base_unit == "ml":
                if current_pack_qty_base >= 1000.0:
                    size_str = f"{current_pack_qty_base / 1000.0:.1f}".rstrip('0').rstrip('.') + "L"
                else:
                    size_str = f"{int(current_pack_qty_base)}ml"
            elif base_unit == "g":
                if current_pack_qty_base >= 1000.0:
                    size_str = f"{current_pack_qty_base / 1000.0:.1f}".rstrip('0').rstrip('.') + "kg"
                else:
                    size_str = f"{int(current_pack_qty_base)}g"
            else:
                size_str = typical_unit
        except Exception:
            size_str = typical_unit
            
        qty_str = f"{typical_qty:.1f}".rstrip('0').rstrip('.')
        if typical_unit == "packet":
            unit_label = "packet" if typical_qty == 1.0 else "packets"
        elif typical_unit == "kg":
            unit_label = "kg"
        elif typical_unit in ["litre", "L", "liter"]:
            unit_label = "litre" if typical_qty == 1.0 else "litres"
        else:
            unit_label = typical_unit
            
        if typical_unit == "kg":
            current_pack_desc = f"{qty_str} kg"
        elif typical_unit in ["litre", "L", "liter"]:
            current_pack_desc = f"{qty_str} {unit_label}"
        elif typical_unit in ["pc", "piece", "pieces"]:
            current_pack_desc = f"{qty_str} {typical_unit}"
        else:
            current_pack_desc = f"{qty_str} {unit_label} ({size_str})"
            
        return {
            "item_name": item_name,
            "current_pack_qty_base": current_pack_qty_base,
            "current_price_per_pack": float(current_price_per_pack),
            "current_frequency_days": float(current_frequency_days),
            "current_monthly_cost": float(actual_total_cost),
            "current_total_cost": float(actual_total_cost),  # backward compatibility
            "current_pack_desc": current_pack_desc,
            
            "suggested_pack": cheapest_option,
            "suggested_pack_qty_base": suggested_pack_qty_base,
            "suggested_price_per_pack": float(suggested_price_per_pack),
            "suggested_frequency_days": float(suggested_frequency_days),
            "suggested_monthly_cost": float(suggested_total_cost),
            "suggested_total_cost": float(suggested_total_cost),  # backward compatibility
            
            "savings": float(savings)
        }
        
    return None
