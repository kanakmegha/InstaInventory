from datetime import datetime, timedelta
from app.pack_optimizer import suggest_pack_size

def test_suggest_pack_size_bulk_savings():
    """
    1. A case where buying in bulk clearly saves money — assert a suggestion
       is returned with the correct savings figure.
    """
    base_time = datetime.now()
    # 10 orders of 1.0 quantity at ₹28 each = ₹280 total cost
    recent_orders = []
    for i in range(10):
        recent_orders.append({
            "item_name": "milk",
            "quantity": 1.0,
            "unit": "ml",
            "price": 28.0,
            "ordered_at": (base_time - timedelta(days=i)).isoformat()
        })
        
    # Option 2 has a cheaper price_per_unit (₹15.0 vs ₹28.0)
    # Suggested cost = 10 * 15 = ₹150
    # Expected savings = 280 - 150 = ₹130
    # Threshold = max(₹10, 10% of 280 = 28) = ₹28
    # Since 130 >= 28, it should return the suggestion.
    pack_options = [
        {"variant_id": "v1", "price": 28.0, "price_per_unit": 28.0},
        {"variant_id": "v2", "price": 150.0, "price_per_unit": 15.0}
    ]
    
    suggestion = suggest_pack_size("milk", recent_orders, pack_options)
    assert suggestion is not None
    assert suggestion["item_name"] == "milk"
    assert suggestion["current_total_cost"] == 280.0
    assert suggestion["suggested_total_cost"] == 150.0
    assert suggestion["savings"] == 130.0
    assert suggestion["suggested_pack"]["variant_id"] == "v2"

def test_suggest_pack_size_savings_below_threshold():
    """
    2. A case where the savings is below threshold — assert None is returned.
    """
    base_time = datetime.now()
    # 2 orders of 1.0 quantity at ₹28 each = ₹56 total cost
    recent_orders = [
        {"item_name": "milk", "quantity": 1.0, "unit": "ml", "price": 28.0, "ordered_at": base_time.isoformat()},
        {"item_name": "milk", "quantity": 1.0, "unit": "ml", "price": 28.0, "ordered_at": (base_time - timedelta(days=1)).isoformat()}
    ]
    
    # Suggested cost = 2 * 27.0 = ₹54
    # Expected savings = 56 - 54 = ₹2.0
    # Threshold = max(10, 5.6) = ₹10
    # Since 2.0 < 10, it should return None.
    pack_options = [
        {"variant_id": "v1", "price": 28.0, "price_per_unit": 28.0},
        {"variant_id": "v2", "price": 27.0, "price_per_unit": 27.0}
    ]
    
    suggestion = suggest_pack_size("milk", recent_orders, pack_options)
    assert suggestion is None

def test_suggest_pack_size_single_option():
    """
    3. A case with only one pack size available — assert None (nothing to compare against).
    """
    base_time = datetime.now()
    recent_orders = [
        {"item_name": "milk", "quantity": 1.0, "unit": "ml", "price": 28.0, "ordered_at": base_time.isoformat()}
    ]
    
    # Only 1 option in options list
    pack_options = [
        {"variant_id": "v1", "price": 28.0, "price_per_unit": 28.0}
    ]
    
    suggestion = suggest_pack_size("milk", recent_orders, pack_options)
    assert suggestion is None

def test_suggest_pack_size_unit_conversion():
    """
    4. Test case where order_history uses "packet" (unit) and pack_options uses "ml" (unit)
       for "milk".
       Suppose the user has ordered 10 packets of milk (each is 500ml, so total_qty_base = 5000 ml).
       Actual paid: 10 * ₹28.0 = ₹280.0
       Pack size option 1 (packets): 1 packet = 500 ml, price = 28.0 (price per base unit = 28.0/500.0 = 0.056)
       Pack size option 2 (bulk pack): 1 litre (1000 ml), price = 50.0 (price per base unit = 50.0/1000.0 = 0.05).
       For 5000 ml, buying using Option 2 (1000 ml packs) requires 5 packs, costing 5 * 50 = ₹250.0.
       Expected savings = 280.0 - 250.0 = ₹30.0.
       Threshold = max(10, 28.0) = 28.0.
       Since 30.0 >= 28.0, it should recommend Option 2!
    """
    base_time = datetime.now()
    recent_orders = []
    for i in range(10):
        recent_orders.append({
            "item_name": "milk",
            "quantity": 1.0,
            "unit": "packet",
            "price": 28.0,
            "ordered_at": (base_time - timedelta(days=i)).isoformat()
        })
        
    pack_options = [
        {"variant_id": "v-packet", "pack_size": "500 ml", "price": 28.0},
        {"variant_id": "v-litre", "pack_size": "1 litre", "price": 50.0}
    ]
    
    suggestion = suggest_pack_size("milk", recent_orders, pack_options)
    assert suggestion is not None
    assert suggestion["item_name"] == "milk"
    assert suggestion["current_total_cost"] == 280.0
    assert suggestion["suggested_total_cost"] == 250.0
    assert suggestion["savings"] == 30.0
    assert suggestion["suggested_pack"]["variant_id"] == "v-litre"

def test_suggest_pack_size_frequency_calculation():
    """
    Asserts current_frequency_days and suggested_frequency_days are calculated correctly.
    User buys 10 packets of milk (500ml each) over 27 days at a fixed interval of 3 days.
    Total base quantity = 5000ml.
    Option 2 is a 1 litre (1000ml) pack at ₹50.0.
    Usage rate = 5000ml / 30 days = 166.67 ml/day.
    Suggested frequency = 1000ml / 166.67 ml/day = 6.0 days.
    """
    base_time = datetime.now()
    recent_orders = []
    # 10 orders spaced 3 days apart
    for i in range(10):
        recent_orders.append({
            "item_name": "milk",
            "quantity": 1.0,
            "unit": "packet",
            "price": 28.0,
            "ordered_at": (base_time - timedelta(days=i * 3)).isoformat()
        })
        
    pack_options = [
        {"variant_id": "v-packet", "pack_size": "500 ml", "price": 28.0},
        {"variant_id": "v-litre", "pack_size": "1 litre", "price": 50.0}
    ]
    
    suggestion = suggest_pack_size("milk", recent_orders, pack_options)
    assert suggestion is not None
    assert suggestion["current_frequency_days"] == 3.0
    assert suggestion["suggested_frequency_days"] == 6.0

def test_suggest_pack_size_frequency_scaling():
    """
    Verifies that frequency scaling is derived from a single daily usage rate.
    Usage rate: 250ml/day (7500ml over 30 days, or 15 orders of 500ml).
    Current pack: 500ml -> frequency should be 500 / 250 = 2.0 days.
    Suggested pack: 1000ml -> frequency should be 1000 / 250 = 4.0 days.
    """
    base_time = datetime.now()
    recent_orders = []
    # 15 orders of 1.0 packet (500ml)
    for i in range(15):
        recent_orders.append({
            "item_name": "milk",
            "quantity": 1.0,
            "unit": "packet",
            "price": 28.0,
            "ordered_at": (base_time - timedelta(days=i * 2)).isoformat()
        })
        
    pack_options = [
        {"variant_id": "v-packet", "pack_size": "500 ml", "price": 28.0},
        {"variant_id": "v-litre", "pack_size": "1 litre", "price": 50.0}
    ]
    
    suggestion = suggest_pack_size("milk", recent_orders, pack_options)
    assert suggestion is not None
    assert suggestion["current_frequency_days"] == 2.0
    assert suggestion["suggested_frequency_days"] == 4.0

def test_suggest_pack_size_frequency_cost_consistency():
    """
    Asserts that suggested_frequency_days is mathematically consistent with monthly cost:
    suggested_monthly_cost / suggested_pack_price == 30.0 / suggested_frequency_days (approximately).
    Also replicates the exact case: current ~1 day frequency, suggested pack yielding ~15.5 purchases/month,
    and asserts the displayed suggested_frequency_days is ~1.9-2.0 days, not collapsed.
    """
    base_time = datetime.now()
    recent_orders = []
    # User orders 30 packets of milk (500ml each) over 30 days -> ~1.0 packet/day usage
    for i in range(30):
        recent_orders.append({
            "item_name": "milk",
            "quantity": 1.0,
            "unit": "packet",
            "price": 28.0,
            "ordered_at": (base_time - timedelta(days=i)).isoformat()
        })
        
    # Suggested options:
    # Option 1: 500ml at 28.0 (price per base = 28/500 = 0.056)
    # Option 2: 1 litre (1000ml) at 40.0 (price per base = 40/1000 = 0.040)
    pack_options = [
        {"variant_id": "v-packet", "pack_size": "500 ml", "price": 28.0},
        {"variant_id": "v-litre", "pack_size": "1 litre", "price": 40.0}
    ]
    
    suggestion = suggest_pack_size("milk", recent_orders, pack_options)
    assert suggestion is not None
    
    # Assert current pack size does not equal suggested pack size
    assert suggestion["current_pack_qty_base"] == 500.0
    assert suggestion["current_price_per_pack"] == 28.0
    assert suggestion["suggested_pack_qty_base"] == 1000.0
    assert suggestion["suggested_price_per_pack"] == 40.0
    assert suggestion["current_pack_qty_base"] != suggestion["suggested_pack_qty_base"]
    
    # Assert current frequency is roughly 1.0 day
    assert abs(suggestion["current_frequency_days"] - 1.0) < 0.01
    
    # Assert suggested frequency is roughly 2.0 days (specifically 2.0 since 1000ml / (15000ml / 30.0) = 2.0 days)
    assert abs(suggestion["suggested_frequency_days"] - 2.0) < 0.1
    
    # Verify cost consistency:
    # suggested_monthly_cost / suggested_price_per_pack ≈ 30.0 / suggested_frequency_days
    cost_purchases = suggestion["suggested_monthly_cost"] / suggestion["suggested_price_per_pack"]
    freq_purchases = 30.0 / suggestion["suggested_frequency_days"]
    assert abs(cost_purchases - freq_purchases) < 0.1
