import sqlite3
import random
from datetime import datetime, timedelta
from app.db import get_db_connection

def seed_mock_orders(db_path: str) -> None:
    """
    Seeds the order_history table in the SQLite database with at least 8 weeks
    of realistic, slightly irregular order data for the following items:
    tomato, milk, onion, eggs, rice, oil.
    """
    # Use a fixed seed for deterministic, repeatable tests
    rng = random.Random(42)
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Optional: Clear existing order history before seeding
    cursor.execute("DELETE FROM order_history;")
    
    # We will generate 60 days (~8.5 weeks) of history ending today
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    # Define item configurations
    items = {
        "milk": {
            "unit": "packet",
            "min_interval_days": 1,
            "max_interval_days": 2,
            "quantities": [1.0, 2.0],
            "weights": [0.6, 0.4],
            "base_unit_price": 28.0,
            "price_variance": 1.5,
            "time_offset_hours": (7, 9)  # ordered in the morning
        },
        "tomato": {
            "unit": "kg",
            "min_interval_days": 3,
            "max_interval_days": 5,
            "quantities": [0.5, 1.0, 1.5],
            "weights": [0.3, 0.5, 0.2],
            "base_unit_price": 40.0,
            "price_variance": 5.0,
            "time_offset_hours": (10, 19)
        },
        "onion": {
            "unit": "kg",
            "min_interval_days": 6,
            "max_interval_days": 9,
            "quantities": [1.0, 2.0, 3.0],
            "weights": [0.4, 0.5, 0.1],
            "base_unit_price": 35.0,
            "price_variance": 3.0,
            "time_offset_hours": (10, 19)
        },
        "eggs": {
            "unit": "pc",
            "min_interval_days": 6,
            "max_interval_days": 8,
            "quantities": [6.0, 12.0],
            "weights": [0.7, 0.3],
            "base_unit_price": 6.5,
            "price_variance": 0.5,
            "time_offset_hours": (8, 12)
        },
        "rice": {
            "unit": "kg",
            "min_interval_days": 20,
            "max_interval_days": 25,
            "quantities": [5.0, 10.0],
            "weights": [0.8, 0.2],
            "base_unit_price": 70.0,
            "price_variance": 4.0,
            "time_offset_hours": (11, 18)
        },
        "oil": {
            "unit": "litre",
            "min_interval_days": 22,
            "max_interval_days": 28,
            "quantities": [1.0, 2.0],
            "weights": [0.7, 0.3],
            "base_unit_price": 135.0,
            "price_variance": 8.0,
            "time_offset_hours": (11, 18)
        }
    }
    
    # Fetch item_id mapping from items table
    cursor.execute("SELECT id, canonical_name FROM items;")
    item_map = {row["canonical_name"]: row["id"] for row in cursor.fetchall()}
    
    orders = []
    
    for item_name, config in items.items():
        # Let's stagger the start dates so they don't all buy on day 0
        current_date = start_date + timedelta(days=rng.randint(0, 3))
        
        while current_date <= end_date:
            # 1. Choose quantity based on weights
            quantity = rng.choices(config["quantities"], weights=config["weights"])[0]
            
            # 2. Choose price per unit (with variance)
            unit_price = config["base_unit_price"] + rng.uniform(-config["price_variance"], config["price_variance"])
            total_price = round(quantity * unit_price, 2)
            
            # 3. Add random time offset within configured hours
            hour = rng.randint(config["time_offset_hours"][0], config["time_offset_hours"][1])
            minute = rng.randint(0, 59)
            second = rng.randint(0, 59)
            ordered_time = current_date.replace(hour=hour, minute=minute, second=second)
            
            item_id = item_map.get(item_name)
            # Record the order
            orders.append((
                item_name,
                quantity,
                config["unit"],
                total_price,
                ordered_time.isoformat(),
                "seed",
                item_id
            ))
            
            # 4. Advance date by a random interval
            interval_days = rng.randint(config["min_interval_days"], config["max_interval_days"])
            # Introduce a small fractional day variation (irregularity)
            fractional_day = rng.uniform(-0.25, 0.25)
            total_delta_days = max(0.5, interval_days + fractional_day)
            
            current_date += timedelta(days=total_delta_days)
            
    # Sort orders by ordered_at datetime before inserting to make the DB log logical
    orders.sort(key=lambda x: x[4])
    
    # Bulk insert
    cursor.executemany("""
        INSERT INTO order_history (item_name, quantity, unit, price, ordered_at, order_source, item_id)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, orders)
    
    # Seed a default user if not already present
    cursor.execute("SELECT COUNT(*) FROM users;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (id, budget_cap_weekly) VALUES (1, 1500.00);")
        
    conn.commit()
    conn.close()
