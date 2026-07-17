import sqlite3
import os

def get_db_connection(db_path: str) -> sqlite3.Connection:
    """
    Establishes and returns an SQLite database connection.
    Enables foreign keys and sets row_factory to sqlite3.Row.
    """
    # Ensure directory exists
    dir_name = os.path.dirname(db_path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(path: str) -> None:
    """
    Initializes the database schema if it does not already exist.
    Creates tables: users, order_history, patterns, approvals, and persona_snapshots.
    """
    conn = get_db_connection(path)
    cursor = conn.cursor()
    
    # 1. users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            budget_cap_weekly REAL
        );
    """)
    
    # 2. order_history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            price REAL NOT NULL,
            ordered_at TEXT NOT NULL
        );
    """)
    
    # 3. patterns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            predicted_cycle_days REAL NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL,
            last_confirmed_at TEXT
        );
    """)
    
    # 4. approvals
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_id INTEGER NOT NULL,
            proposed_date TEXT NOT NULL,
            proposed_cost REAL NOT NULL,
            user_response TEXT,
            responded_at TEXT,
            FOREIGN KEY (pattern_id) REFERENCES patterns(id) ON DELETE CASCADE
        );
    """)
    
    # 5. persona_snapshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS persona_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_of TEXT NOT NULL,
            avg_weekly_spend REAL NOT NULL,
            top_items_json TEXT NOT NULL,
            bulk_acceptance_rate REAL NOT NULL,
            approval_rate REAL NOT NULL,
            notes TEXT
        );
    """)
    
    conn.commit()
    conn.close()
