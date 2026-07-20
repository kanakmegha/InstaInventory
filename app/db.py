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
    Creates tables: users, items, order_history, patterns, approvals, and persona_snapshots.
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
    
    # 2. items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            unit_category TEXT NOT NULL CHECK(unit_category IN ('volume', 'weight', 'countable'))
        );
    """)
    
    # 3. order_history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            price REAL NOT NULL,
            ordered_at TEXT NOT NULL,
            order_source TEXT,
            item_id INTEGER,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
        );
    """)
    
    # 4. patterns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            predicted_cycle_days REAL NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL,
            last_confirmed_at TEXT,
            item_id INTEGER,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
        );
    """)
    
    # 5. approvals
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_id INTEGER NOT NULL,
            proposed_date TEXT NOT NULL,
            proposed_cost REAL NOT NULL,
            user_response TEXT,
            responded_at TEXT,
            item_id INTEGER,
            FOREIGN KEY (pattern_id) REFERENCES patterns(id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
        );
    """)
    
    # 6. persona_snapshots
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
    
    # Self-healing migrations for existing DBs
    try:
        cursor.execute("ALTER TABLE order_history ADD COLUMN order_source TEXT;")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE order_history ADD COLUMN item_id INTEGER REFERENCES items(id);")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE patterns ADD COLUMN item_id INTEGER REFERENCES items(id);")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE approvals ADD COLUMN item_id INTEGER REFERENCES items(id);")
    except sqlite3.OperationalError:
        pass
        
    # Seed default items in items table
    seed_items = [
        {"canonical_name": "milk", "display_name": "Toned Milk", "unit_category": "volume"},
        {"canonical_name": "tomato", "display_name": "Tomato", "unit_category": "weight"},
        {"canonical_name": "eggs", "display_name": "Eggs", "unit_category": "countable"},
        {"canonical_name": "rice", "display_name": "Basmati Rice", "unit_category": "weight"},
        {"canonical_name": "oil", "display_name": "Sunflower Oil", "unit_category": "volume"},
        {"canonical_name": "onion", "display_name": "Onion", "unit_category": "weight"},
        {"canonical_name": "peach", "display_name": "Peach", "unit_category": "weight"},
        {"canonical_name": "atta", "display_name": "Atta", "unit_category": "weight"},
        {"canonical_name": "bread", "display_name": "Bread", "unit_category": "countable"}
    ]
    for item in seed_items:
        cursor.execute("""
            INSERT OR IGNORE INTO items (canonical_name, display_name, unit_category)
            VALUES (?, ?, ?);
        """, (item["canonical_name"], item["display_name"], item["unit_category"]))
        
    # Backfill item_id on existing rows
    cursor.execute("""
        UPDATE order_history
        SET item_id = (SELECT id FROM items WHERE items.canonical_name = order_history.item_name)
        WHERE item_id IS NULL;
    """)
    cursor.execute("""
        UPDATE patterns
        SET item_id = (SELECT id FROM items WHERE items.canonical_name = patterns.item_name)
        WHERE item_id IS NULL;
    """)
    cursor.execute("""
        UPDATE approvals
        SET item_id = (SELECT item_id FROM patterns WHERE patterns.id = approvals.pattern_id)
        WHERE item_id IS NULL;
    """)
    
    conn.commit()
    conn.close()
