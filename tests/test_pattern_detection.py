from datetime import datetime, timedelta
from app.pattern_detection import detect_patterns, detect_drift

def test_exact_intervals():
    """
    1. An item ordered every 7 days exactly, 5 times.
    Expect high confidence (>0.85) and cycle ≈ 7.
    """
    base_time = datetime(2026, 5, 1, 10, 0, 0)
    orders = []
    for i in range(5):
        ordered_time = base_time + timedelta(days=i * 7)
        orders.append({
            "item_name": "milk",
            "ordered_at": ordered_time.isoformat()
        })
        
    results = detect_patterns(orders)
    assert len(results) == 1
    result = results[0]
    assert result["item_name"] == "milk"
    assert abs(result["predicted_cycle_days"] - 7.0) < 1e-9
    assert result["confidence"] > 0.85
    assert result["order_count"] == 5

def test_two_orders_only():
    """
    2. An item ordered only twice, 10 days apart.
    Expect it included but with lower confidence than the exact milk intervals test.
    """
    base_time = datetime(2026, 5, 1, 10, 0, 0)
    orders = [
        {"item_name": "bread", "ordered_at": base_time.isoformat()},
        {"item_name": "bread", "ordered_at": (base_time + timedelta(days=10)).isoformat()}
    ]
    
    results = detect_patterns(orders)
    assert len(results) == 1
    result = results[0]
    assert result["item_name"] == "bread"
    assert abs(result["predicted_cycle_days"] - 10.0) < 1e-9
    
    # Establish milk baseline (exact interval, 5 orders)
    milk_orders = []
    for i in range(5):
        milk_orders.append({
            "item_name": "milk",
            "ordered_at": (base_time + timedelta(days=i * 7)).isoformat()
        })
    milk_results = detect_patterns(milk_orders)
    milk_confidence = milk_results[0]["confidence"]
    
    assert result["confidence"] < milk_confidence
    assert 0.0 < result["confidence"] < 1.0

def test_wildly_irregular_gaps():
    """
    3. An item ordered with wildly irregular gaps (3, 19, 6, 25 days).
    Expect low confidence (<0.5).
    """
    base_time = datetime(2026, 5, 1, 10, 0, 0)
    # Days from start: 0, 3, 22, 28, 53
    days = [0, 3, 22, 28, 53]
    orders = []
    for d in days:
        ordered_time = base_time + timedelta(days=d)
        orders.append({
            "item_name": "eggs",
            "ordered_at": ordered_time.isoformat()
        })
        
    results = detect_patterns(orders)
    assert len(results) == 1
    result = results[0]
    assert result["item_name"] == "eggs"
    assert result["confidence"] < 0.5
    assert result["order_count"] == 5

def test_single_order_excluded():
    """
    4. An item ordered only once.
    Expect it excluded entirely from the output.
    """
    orders = [
        {"item_name": "rice", "ordered_at": "2026-05-01T12:00:00"}
    ]
    results = detect_patterns(orders)
    assert len(results) == 0

def test_detect_drift_cases():
    """
    5. detect_drift returns True when given ["declined", "declined"], 
    False when given ["approved", "declined"].
    """
    dummy_pattern = {"item_name": "milk", "predicted_cycle_days": 7.0}
    
    # Must return True for last 2+ declined
    assert detect_drift(dummy_pattern, ["declined", "declined"]) is True
    assert detect_drift(dummy_pattern, ["approved", "declined", "declined"]) is True
    assert detect_drift(dummy_pattern, ["declined", "declined", "declined"]) is True
    
    # Must return False otherwise
    assert detect_drift(dummy_pattern, ["approved", "declined"]) is False
    assert detect_drift(dummy_pattern, ["declined", "approved"]) is False
    assert detect_drift(dummy_pattern, ["declined"]) is False
    assert detect_drift(dummy_pattern, []) is False
    assert detect_drift(dummy_pattern, ["approved"]) is False
