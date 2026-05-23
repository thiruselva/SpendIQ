"""
SpendIQ v2 Database Module
SQLite connection manager with schema initialization from SQL files.
Uses separate database files for demo mode vs real data.
"""

import sqlite3
import os
import glob

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schema")


def _get_db_path() -> str:
    """Return the active database path based on DEMO_MODE."""
    demo = os.getenv("DEMO_MODE", "false").lower() == "true"
    filename = "spendiq_v2_demo.db" if demo else "spendiq_v2.db"
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
    """
    Create all tables by executing schema SQL files in order.
    Files are named 00_pragmas.sql through 17_seed_data.sql.
    Safe to run multiple times (all CREATE TABLE IF NOT EXISTS, INSERT OR IGNORE).
    """
    conn = get_db()
    cursor = conn.cursor()

    schema_files = sorted(glob.glob(os.path.join(SCHEMA_DIR, "*.sql")))
    for sql_file in schema_files:
        with open(sql_file, "r") as f:
            sql = f.read()
        cursor.executescript(sql)
        print(f"  Applied: {os.path.basename(sql_file)}")

    conn.commit()
    conn.close()
    db_path = _get_db_path()
    mode = "demo" if "demo" in db_path else "production"
    print(f"Database initialized at {db_path} ({mode} mode)")


def get_unit_conversions(conn=None) -> dict:
    """
    Load unit_conversions table into a lookup dict.
    Returns: { 'lb': {'to_standard': 'oz', 'multiplier': 16.0, 'category': 'weight'}, ... }
    """
    close = False
    if conn is None:
        conn = get_db()
        close = True

    rows = conn.execute("SELECT from_unit, to_standard, multiplier, unit_category FROM unit_conversions").fetchall()
    result = {}
    for row in rows:
        result[row["from_unit"]] = {
            "to_standard": row["to_standard"],
            "multiplier": row["multiplier"],
            "category": row["unit_category"],
        }

    if close:
        conn.close()
    return result


def compute_standard_units(package_size: float, package_unit: str,
                           package_count: int, conversions: dict) -> float | None:
    """
    Compute total standard units in a package.

    Args:
        package_size: Size value (e.g., 5 for "5 oz", 1 for "1 lb")
        package_unit: Unit string (e.g., 'oz', 'lb', 'half_gallon')
        package_count: Multi-pack count (e.g., 3 for "3x half-gallon")
        conversions: Dict from get_unit_conversions()

    Returns:
        Total standard units (e.g., 16.0 oz, 192.0 fl_oz) or None.
    """
    if not package_size or not package_unit:
        return None
    conv = conversions.get(package_unit)
    if not conv:
        return None
    return package_size * conv["multiplier"] * (package_count or 1)


def compute_price_per_unit(total_price: float, total_standard_units: float) -> float | None:
    """
    Compute price per standard unit.

    Args:
        total_price: Total price paid for this line item
        total_standard_units: Total oz/fl_oz/each in this purchase

    Returns:
        Price per standard unit (e.g., $0.304/oz) or None.
    """
    if not total_price or not total_standard_units or total_standard_units <= 0:
        return None
    return round(total_price / total_standard_units, 6)


def find_or_create_store(conn, store_name: str) -> int:
    """Find store by name or create it. Returns store_id."""
    row = conn.execute("SELECT id FROM stores WHERE name = ?", (store_name,)).fetchone()
    if row:
        return row["id"]
    # Infer store type
    store_type = "warehouse" if "costco" in store_name.lower() else "grocery"
    cursor = conn.execute(
        "INSERT INTO stores (name, store_type) VALUES (?, ?)",
        (store_name, store_type)
    )
    conn.commit()
    return cursor.lastrowid


def find_or_create_product(conn, canonical_name: str, brand: str | None,
                           standard_unit: str | None, unit_category: str | None) -> int:
    """Find product by canonical name or create it. Returns product_id."""
    row = conn.execute(
        "SELECT id FROM products WHERE canonical_name = ?",
        (canonical_name,)
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        """INSERT INTO products (canonical_name, brand, standard_unit, unit_category)
           VALUES (?, ?, ?, ?)""",
        (canonical_name, brand, standard_unit, unit_category)
    )
    return cursor.lastrowid


def find_or_create_alias(conn, product_id: int, store_id: int,
                         store_product_name: str, package_info: dict,
                         conversions: dict) -> int:
    """
    Find or create a product_alias. Computes standard_units_per_package.
    Returns alias_id.

    package_info: {
        'package_size': 5.0, 'package_unit': 'oz', 'package_count': 1,
        'store_item_number': '96716', 'sold_by': 'unit'
    }
    """
    row = conn.execute(
        "SELECT id FROM product_aliases WHERE store_id = ? AND store_product_name = ?",
        (store_id, store_product_name)
    ).fetchone()
    if row:
        return row["id"]

    std_units = compute_standard_units(
        package_info.get("package_size"),
        package_info.get("package_unit"),
        package_info.get("package_count", 1),
        conversions,
    )

    cursor = conn.execute(
        """INSERT INTO product_aliases
           (product_id, store_id, store_product_name, store_item_number,
            package_size, package_unit, package_count,
            standard_units_per_package, sold_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            product_id, store_id, store_product_name,
            package_info.get("store_item_number"),
            package_info.get("package_size"),
            package_info.get("package_unit"),
            package_info.get("package_count", 1),
            std_units,
            package_info.get("sold_by", "unit"),
        )
    )
    return cursor.lastrowid



if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    init_db()
