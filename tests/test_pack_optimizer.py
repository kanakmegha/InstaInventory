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
        {"item_name": "milk", "quantity": 1.0, "price": 28.0, "ordered_at": base_time.isoformat()},
        {"item_name": "milk", "quantity": 1.0, "price": 28.0, "ordered_at": (base_time - timedelta(days=1)).isoformat()}
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
        {"item_name": "milk", "quantity": 1.0, "price": 28.0, "ordered_at": base_time.isoformat()}
    ]
    
    # Only 1 option in options list
    pack_options = [
        {"variant_id": "v1", "price": 28.0, "price_per_unit": 28.0}
    ]
    
    suggestion = suggest_pack_size("milk", recent_orders, pack_options)
    assert suggestion is None
