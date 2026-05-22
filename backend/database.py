"""
SpendIQ Database Module
SQLite connection manager with schema initialization and seed data.
Uses separate database files for demo mode vs real data.
"""

import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(__file__), "data")


def _get_db_path() -> str:
    """Return the active database path based on DEMO_MODE."""
    from demo_data import is_demo_mode
    filename = "spendiq_demo.db" if is_demo_mode() else "spendiq.db"
    return os.path.join(DB_DIR, filename)


def get_db():
    """Get a database connection with row factory enabled."""
    os.makedirs(DB_DIR, exist_ok=True)
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables and seed vendor rules if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    # Core transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            vendor      TEXT NOT NULL,
            amount      REAL,
            category    TEXT DEFAULT 'other',
            source      TEXT DEFAULT 'upload',
            file_name   TEXT,
            raw_text    TEXT,
            is_verified INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # Shopping lists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shopping_lists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            item        TEXT NOT NULL,
            store       TEXT,
            frequency   TEXT,
            est_price   REAL,
            list_type   TEXT DEFAULT 'weekly',
            is_done     INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # Vendor rules for auto-categorization
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendor_rules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern     TEXT NOT NULL,
            category    TEXT NOT NULL,
            store_name  TEXT
        )
    """)

    # Line items — individual products within an order
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS line_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id  INTEGER NOT NULL,
            product_name    TEXT NOT NULL,
            quantity        REAL DEFAULT 1,
            unit_price      REAL,
            total_price     REAL,
            item_status     TEXT,
            item_number     TEXT,
            discount        REAL DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tx_vendor ON transactions(vendor)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tx_source ON transactions(source)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_li_txid ON line_items(transaction_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_li_product ON line_items(product_name)")

    # Pre-seed vendor rules (only if table is empty)
    existing = cursor.execute("SELECT COUNT(*) FROM vendor_rules").fetchone()[0]
    if existing == 0:
        seed_rules = [
            ("walmart", "grocery", "Walmart"),
            ("costco", "grocery", "Costco"),
            ("doordash", "food", "DoorDash"),
            ("uber eats", "food", "Uber Eats"),
            ("grubhub", "food", "Grubhub"),
            ("amazon", "shopping", "Amazon"),
            ("wellness", "health", "Wellness Clinic"),
            ("dental", "dental", "Dental"),
            ("apple", "subscription", "Apple"),
            ("netflix", "subscription", "Netflix"),
            ("spotify", "subscription", "Spotify"),
            ("anthropic", "subscription", "Anthropic Claude"),
            ("google", "subscription", "Google"),
            ("target", "shopping", "Target"),
            ("cvs", "health", "CVS Pharmacy"),
            ("walgreens", "health", "Walgreens"),
        ]
        cursor.executemany(
            "INSERT INTO vendor_rules (pattern, category, store_name) VALUES (?, ?, ?)",
            seed_rules,
        )

    conn.commit()
    conn.close()
    db_path = _get_db_path()
    mode = "demo" if "demo" in db_path else "production"
    print(f"✓ Database initialized at {db_path} ({mode} mode)")


def categorize_vendor(vendor_name: str) -> tuple[str, str]:
    """
    Match a vendor name against vendor_rules to auto-categorize.
    Returns (category, normalized_store_name).
    """
    conn = get_db()
    rules = conn.execute("SELECT pattern, category, store_name FROM vendor_rules").fetchall()
    conn.close()

    vendor_lower = vendor_name.lower()
    for rule in rules:
        if rule["pattern"] in vendor_lower:
            return rule["category"], rule["store_name"]
    return "other", vendor_name


if __name__ == "__main__":
    init_db()
