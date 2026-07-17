import os
import sqlite3
import pytest
from app.db import init_db, get_db_connection
from app.seed import seed_mock_orders

@pytest.fixture
def temp_db(tmp_path):
    """
    Pytest fixture that creates a temporary SQLite database and runs init_db.
    """
    db_file = tmp_path / "test_inventory.db"
    db_path = str(db_file)
    init_db(db_path)
    return db_path

def test_tables_exist(temp_db):
    """
    Asserts that all 5 required tables exist in the database.
    """
    conn = get_db_connection(temp_db)
    cursor = conn.cursor()
    
    # Query sqlite_master to verify tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()
    
    expected_tables = {"users", "order_history", "patterns", "approvals", "persona_snapshots"}
    
    # Check that all expected tables are a subset of the actual tables in SQLite
    for table in expected_tables:
        assert table in tables, f"Table '{table}' was not created."

def test_seed_mock_orders(temp_db):
    """
    Asserts that seed_mock_orders runs successfully and populates rows.
    """
    seed_mock_orders(temp_db)
    
    conn = get_db_connection(temp_db)
    cursor = conn.cursor()
    
    # Assert row counts for order_history
    cursor.execute("SELECT COUNT(*) as count FROM order_history;")
    count = cursor.fetchone()["count"]
    
    # Assert that at least 8 weeks of data is generated (realistic expectations based on interval averages)
    assert count >= 60, f"Expected at least 60 orders, but got {count}."
    
    # Assert that 1 user record is seeded (per seed.py script design)
    cursor.execute("SELECT COUNT(*) as count FROM users;")
    user_count = cursor.fetchone()["count"]
    assert user_count == 1, f"Expected 1 user, but got {user_count}."
    
    # Verify the items seeded match the ones we expect
    cursor.execute("SELECT DISTINCT item_name FROM order_history;")
    items = {row["item_name"] for row in cursor.fetchall()}
    expected_items = {"tomato", "milk", "onion", "eggs", "rice", "oil"}
    assert items == expected_items, f"Seeded items do not match. Got: {items}"
    
    conn.close()

def test_data_integrity(temp_db):
    """
    Asserts that:
    1. There are no duplicate primary keys in order_history.
    2. There are no null item_names in order_history.
    """
    seed_mock_orders(temp_db)
    
    conn = get_db_connection(temp_db)
    cursor = conn.cursor()
    
    # Check for duplicate IDs in order_history
    cursor.execute("SELECT id, COUNT(*) as c FROM order_history GROUP BY id HAVING c > 1;")
    duplicate_ids = cursor.fetchall()
    assert len(duplicate_ids) == 0, f"Found duplicate primary keys: {duplicate_ids}"
    
    # Check for NULL item_names
    cursor.execute("SELECT COUNT(*) as null_count FROM order_history WHERE item_name IS NULL;")
    null_items_count = cursor.fetchone()["null_count"]
    assert null_items_count == 0, "Found NULL values in item_name column."
    
    # Check for empty string item_names
    cursor.execute("SELECT COUNT(*) as empty_count FROM order_history WHERE item_name = '';")
    empty_items_count = cursor.fetchone()["empty_count"]
    assert empty_items_count == 0, "Found empty string values in item_name column."
    
    conn.close()
