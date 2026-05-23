"""
SpendIQ v2 Migration Script — Create v2 database and import structured data.

Creates the v2 database from schema SQL files and imports Walmart Excel orders.
Costco PDFs require AI parsing and are handled separately.

Usage:
    cd backend
    python scripts/migrate_v2.py --walmart-dir /path/to/Walmart_Bills
    python scripts/migrate_v2.py --walmart-dir /path/to/Walmart_Bills --dry-run
    python scripts/migrate_v2.py --costco  # prints AI parser instructions

Examples:
    # Import Walmart orders
    python scripts/migrate_v2.py --walmart-dir ~/Bills/Walmart_Bills

    # Preview without writing to DB
    python scripts/migrate_v2.py --walmart-dir ~/Bills/Walmart_Bills --dry-run

    # Custom DB path
    python scripts/migrate_v2.py --walmart-dir ~/Bills/Walmart_Bills --db-path ./data/test_v2.db

    # Show Costco import instructions
    python scripts/migrate_v2.py --costco --costco-dir ~/Bills/Costco_Bills
"""

import argparse
import os
import re
import sqlite3
import sys
import statistics
from datetime import datetime
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = BACKEND_DIR / "schema"
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "spendiq_v2.db"

WALMART_STORE_ID = 2  # From seed data: Costco=1, Walmart=2
WALMART_GROCERY_CATEGORY_ID = 4  # 'Grocery' category for Walmart (seed row 4)

# Regex to extract order number from Walmart filenames like:
#   Order_01031637115895536570.xlsx
ORDER_NUMBER_RE = re.compile(r"Order[_\s-]?(\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def create_v2_database(db_path: str, *, dry_run: bool = False) -> sqlite3.Connection:
    """
    Create the v2 database by running all schema SQL files in order.

    Returns an open connection to the new database.
    """
    schema_files = sorted(SCHEMA_DIR.glob("*.sql"))
    if not schema_files:
        print(f"ERROR: No schema SQL files found in {SCHEMA_DIR}")
        sys.exit(1)

    if dry_run:
        print(f"[DRY RUN] Would create database at: {db_path}")
        print(f"[DRY RUN] Would run {len(schema_files)} schema files")
        # Use in-memory DB for dry runs so we can still validate queries
        conn = sqlite3.connect(":memory:")
    else:
        # Ensure data directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)

    conn.row_factory = sqlite3.Row

    print(f"\n{'=' * 60}")
    print(f"Creating v2 database schema")
    print(f"{'=' * 60}")

    for sql_file in schema_files:
        try:
            sql = sql_file.read_text()
            conn.executescript(sql)
            print(f"  [OK] {sql_file.name}")
        except sqlite3.Error as e:
            print(f"  [FAIL] {sql_file.name}: {e}")
            conn.close()
            sys.exit(1)

    conn.execute("PRAGMA foreign_keys = ON")
    print(f"\nSchema ready: {len(schema_files)} files applied")
    return conn


# ---------------------------------------------------------------------------
# Product name normalization & deduplication
# ---------------------------------------------------------------------------

# Common brand prefixes to strip for canonical matching
_BRAND_PREFIXES = [
    "great value", "marketside", "freshness guaranteed",
    "sam's choice", "equate", "ol' roy", "parent's choice",
    "mainstays", "onn.", "george", "time and tru",
]

# Compile once
_BRAND_RE = re.compile(
    r"^(?:" + "|".join(re.escape(b) for b in _BRAND_PREFIXES) + r")\s+",
    re.IGNORECASE,
)


def normalize_product_name(raw_name: str) -> str:
    """
    Normalize a product name for deduplication:
      1. Strip leading/trailing whitespace
      2. Remove known brand prefixes
      3. Lowercase
      4. Collapse multiple spaces
      5. Strip trailing size descriptors like "(16 oz)" or ", 12 ct"
    """
    name = raw_name.strip()
    # Remove brand prefix
    name = _BRAND_RE.sub("", name)
    # Lowercase
    name = name.lower()
    # Remove trailing parenthetical size info: "(16 oz)", "(2 lb bag)"
    name = re.sub(r"\s*\(.*?\)\s*$", "", name)
    # Remove trailing comma-separated size: ", 12 ct", ", 5 oz"
    name = re.sub(r",\s*\d+[\d.]*\s*(?:oz|lb|ct|count|fl\s*oz|gallon|ml|liter|g|kg|pack|each)\s*$", "", name, flags=re.IGNORECASE)
    # Collapse spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name


def is_sold_by_weight(quantity: float) -> bool:
    """
    Determine if a product is sold by weight based on its quantity.
    If quantity has a meaningful decimal (not .0), it's likely by-weight.
    e.g., 4.2 (bananas by lb), 0.47 (broccoli by lb)
    """
    if quantity is None:
        return False
    # Check if there's a non-zero fractional part
    # Round to avoid floating point noise
    frac = round(quantity % 1, 4)
    return frac != 0.0


# ---------------------------------------------------------------------------
# Walmart import
# ---------------------------------------------------------------------------

def _extract_order_number(filename: str) -> str:
    """Extract order number from Walmart filename."""
    match = ORDER_NUMBER_RE.search(filename)
    if match:
        return match.group(1)
    # Fallback: use filename without extension
    return Path(filename).stem


def _get_order_date(filepath: str) -> str:
    """Get order date from file modification time, as YYYY-MM-DD."""
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def import_walmart_orders(
    conn: sqlite3.Connection,
    walmart_dir: str,
    *,
    dry_run: bool = False,
) -> dict:
    """
    Import all Walmart Excel orders from the given directory into v2 schema.

    Returns summary stats dict.
    """
    walmart_path = Path(walmart_dir)
    if not walmart_path.is_dir():
        print(f"ERROR: Walmart directory not found: {walmart_dir}")
        return {"orders": 0, "items": 0, "products": 0, "skipped": 0, "errors": 0}

    xlsx_files = sorted(
        f for f in walmart_path.iterdir()
        if f.suffix.lower() in (".xlsx", ".xls") and not f.name.startswith("~")
    )

    if not xlsx_files:
        print(f"  No .xlsx files found in {walmart_dir}")
        return {"orders": 0, "items": 0, "products": 0, "skipped": 0, "errors": 0}

    print(f"\n{'=' * 60}")
    print(f"Importing Walmart orders from: {walmart_dir}")
    print(f"Found {len(xlsx_files)} Excel files")
    print(f"{'=' * 60}")

    # Track stats
    stats = {"orders": 0, "items": 0, "products": 0, "skipped": 0, "errors": 0}

    # Product cache: normalized_name -> product_id
    product_cache = _load_existing_products(conn)
    # Alias cache: (store_id, store_product_name) -> alias_id
    alias_cache = _load_existing_aliases(conn, WALMART_STORE_ID)
    # Order cache: order_number -> True (for dedup)
    order_cache = _load_existing_orders(conn, WALMART_STORE_ID)

    for xlsx_file in xlsx_files:
        try:
            result = _import_single_walmart_order(
                conn, xlsx_file, product_cache, alias_cache, order_cache,
                dry_run=dry_run,
            )
            if result == "skipped":
                stats["skipped"] += 1
                print(f"  [SKIP] {xlsx_file.name} (already imported)")
            elif result == "empty":
                stats["skipped"] += 1
                print(f"  [SKIP] {xlsx_file.name} (no valid items)")
            else:
                stats["orders"] += 1
                stats["items"] += result["item_count"]
                stats["products"] += result["new_products"]
                action = "Would import" if dry_run else "Imported"
                print(
                    f"  [OK] {xlsx_file.name}: "
                    f"{result['item_count']} items, "
                    f"${result['order_total']:.2f}, "
                    f"{result['new_products']} new products"
                )
        except Exception as e:
            stats["errors"] += 1
            print(f"  [FAIL] {xlsx_file.name}: {e}")

    if not dry_run:
        conn.commit()

    return stats


def _load_existing_products(conn: sqlite3.Connection) -> dict:
    """Load existing products into a cache: canonical_name -> product_id."""
    cache = {}
    try:
        rows = conn.execute("SELECT id, canonical_name FROM products").fetchall()
        for row in rows:
            cache[row["canonical_name"].lower()] = row["id"]
    except sqlite3.OperationalError:
        pass  # Table might not exist yet in dry-run edge cases
    return cache


def _load_existing_aliases(conn: sqlite3.Connection, store_id: int) -> dict:
    """Load existing aliases into a cache: store_product_name -> alias_id."""
    cache = {}
    try:
        rows = conn.execute(
            "SELECT id, store_product_name FROM product_aliases WHERE store_id = ?",
            (store_id,),
        ).fetchall()
        for row in rows:
            cache[row["store_product_name"]] = row["id"]
    except sqlite3.OperationalError:
        pass
    return cache


def _load_existing_orders(conn: sqlite3.Connection, store_id: int) -> set:
    """Load existing order numbers for dedup."""
    cache = set()
    try:
        rows = conn.execute(
            "SELECT order_number FROM orders WHERE store_id = ?",
            (store_id,),
        ).fetchall()
        for row in rows:
            cache.add(row["order_number"])
    except sqlite3.OperationalError:
        pass
    return cache


def _get_or_create_product(
    conn: sqlite3.Connection,
    product_cache: dict,
    canonical_name: str,
    *,
    dry_run: bool = False,
) -> int:
    """
    Get or create a product by canonical name.
    Returns product_id.
    """
    key = canonical_name.lower()
    if key in product_cache:
        return product_cache[key]

    if dry_run:
        # Assign a fake negative ID for dry run tracking
        fake_id = -(len(product_cache) + 1)
        product_cache[key] = fake_id
        return fake_id

    cursor = conn.execute(
        "INSERT INTO products (canonical_name) VALUES (?)",
        (canonical_name,),
    )
    product_id = cursor.lastrowid
    product_cache[key] = product_id
    return product_id


def _get_or_create_alias(
    conn: sqlite3.Connection,
    alias_cache: dict,
    product_id: int,
    store_product_name: str,
    quantity: float,
    *,
    dry_run: bool = False,
) -> int:
    """
    Get or create a product alias for this store product name.
    Returns alias_id.
    """
    if store_product_name in alias_cache:
        return alias_cache[store_product_name]

    sold_by = "weight" if is_sold_by_weight(quantity) else "unit"
    package_unit = "lb" if sold_by == "weight" else None

    if dry_run:
        fake_id = -(len(alias_cache) + 1)
        alias_cache[store_product_name] = fake_id
        return fake_id

    cursor = conn.execute(
        """INSERT INTO product_aliases
           (product_id, store_id, store_product_name, sold_by, package_unit)
           VALUES (?, ?, ?, ?, ?)""",
        (product_id, WALMART_STORE_ID, store_product_name, sold_by, package_unit),
    )
    alias_id = cursor.lastrowid
    alias_cache[store_product_name] = alias_id
    return alias_id


def _import_single_walmart_order(
    conn: sqlite3.Connection,
    xlsx_path: Path,
    product_cache: dict,
    alias_cache: dict,
    order_cache: set,
    *,
    dry_run: bool = False,
) -> str | dict:
    """
    Import a single Walmart Excel file.

    Returns:
        "skipped" if duplicate order
        "empty" if no valid line items
        dict with {item_count, order_total, new_products} on success
    """
    filename = xlsx_path.name

    # Read Excel
    df = pd.read_excel(str(xlsx_path), engine="openpyxl")

    # Validate columns
    if "Product Name" not in df.columns or "Price" not in df.columns:
        raise ValueError(
            f"Missing required columns. Found: {list(df.columns)}"
        )

    # First pass: extract metadata
    metadata = {}
    METADATA_KEYS = {
        'order number', 'order date', 'address recipient', 'shipping address', 
        'delivery instructions', 'payment method', 'payment messages', 
        'subtotal (before savings)', 'savings', 'subtotal', 'delivery charges', 
        'bag fee', 'tax', 'tip', 'order total'
    }

    for _, row in df.iterrows():
        pname = str(row.get("Product Name", "")).strip()
        if not pname or pname == "nan":
            continue
        pname_lower = pname.lower()
        if pname_lower in METADATA_KEYS:
            metadata[pname_lower] = row.get("Quantity")

    # Order number
    order_number = None
    if 'order number' in metadata and not pd.isna(metadata['order number']):
        val = metadata['order number']
        if isinstance(val, (int, float)):
            order_number = f"{int(val)}"
        else:
            order_number = str(val).strip()
    if not order_number:
        order_number = _extract_order_number(filename)

    # Dedup check
    if order_number in order_cache:
        return "skipped"

    # Order date
    order_date = None
    if 'order date' in metadata and not pd.isna(metadata['order date']):
        raw_date = str(metadata['order date']).strip()
        cleaned_date = re.sub(r'\s+purchase$', '', raw_date, flags=re.IGNORECASE).strip()
        try:
            order_date = datetime.strptime(cleaned_date, "%b %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            pass
    if not order_date:
        order_date = _get_order_date(str(xlsx_path))

    # Payment method
    payment_method = None
    if 'payment method' in metadata and not pd.isna(metadata['payment method']):
        payment_method = str(metadata['payment method']).strip()

    # Financial details
    def parse_float(val, default=0.0):
        if pd.isna(val) or val is None:
            return default
        try:
            return float(str(val).replace("$", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return default

    subtotal_before_savings = parse_float(metadata.get('subtotal (before savings)'), 0.0)
    savings = parse_float(metadata.get('savings'), 0.0)
    subtotal = parse_float(metadata.get('subtotal'), 0.0)
    delivery_charges = parse_float(metadata.get('delivery charges'), 0.0)
    bag_fee = parse_float(metadata.get('bag fee'), 0.0)
    tax = parse_float(metadata.get('tax'), 0.0)
    tip = parse_float(metadata.get('tip'), 0.0)
    order_total_meta = parse_float(metadata.get('order total'), None)

    # Parse line items
    items = []
    order_total = 0.0
    new_product_count = 0

    for _, row in df.iterrows():
        product_name = str(row.get("Product Name", "")).strip()
        if not product_name or product_name == "nan":
            continue

        # Skip metadata rows
        if product_name.lower() in METADATA_KEYS:
            continue

        # Parse quantity
        quantity = row.get("Quantity", 1)
        if pd.isna(quantity):
            quantity = 1.0
        else:
            try:
                quantity = float(str(quantity).replace(",", ""))
            except (ValueError, TypeError):
                quantity = 1.0

        # Parse price
        price = row.get("Price")
        if pd.isna(price):
            price = None
        else:
            try:
                price = float(str(price).replace("$", "").replace(",", "").strip())
            except (ValueError, TypeError):
                price = None

        # Delivery status
        status = str(row.get("Delivery Status", "")).strip()
        if status == "nan":
            status = None

        total_price = round(price * quantity, 2) if price else None

        # Product dedup: normalize name for canonical product
        canonical = normalize_product_name(product_name)
        if not canonical:
            canonical = product_name.strip().lower()

        # Track if this is a new product
        was_new = canonical.lower() not in product_cache

        # Get or create product + alias
        product_id = _get_or_create_product(
            conn, product_cache, canonical, dry_run=dry_run,
        )
        alias_id = _get_or_create_alias(
            conn, alias_cache, product_id, product_name, quantity,
            dry_run=dry_run,
        )

        if was_new:
            new_product_count += 1

        items.append({
            "product_id": product_id,
            "alias_id": alias_id,
            "raw_product_name": product_name,
            "quantity": quantity,
            "unit_price": price or 0,
            "total_price": total_price,
            "delivery_status": status,
        })

        if total_price:
            order_total += total_price

    if not items:
        return "empty"

    if order_total_meta is not None:
        order_total = order_total_meta
    else:
        order_total = round(order_total, 2)

    # Insert order
    if not dry_run:
        cursor = conn.execute(
            """INSERT INTO orders
               (store_id, category_id, order_number, order_date, payment_method,
                subtotal_before_savings, savings, subtotal, delivery_charges, bag_fee,
                tax, tip, order_total, source_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                WALMART_STORE_ID,
                WALMART_GROCERY_CATEGORY_ID,
                order_number,
                order_date,
                payment_method,
                subtotal_before_savings,
                savings,
                subtotal,
                delivery_charges,
                bag_fee,
                tax,
                tip,
                order_total,
                filename,
            ),
        )
        order_id = cursor.lastrowid

        # Insert order items
        for item in items:
            conn.execute(
                """INSERT INTO order_items
                   (order_id, product_id, alias_id, raw_product_name,
                    quantity, unit_price, total_price, delivery_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order_id,
                    item["product_id"],
                    item["alias_id"],
                    item["raw_product_name"],
                    item["quantity"],
                    item["unit_price"],
                    item["total_price"],
                    item["delivery_status"],
                ),
            )

    # Mark as seen for dedup
    order_cache.add(order_number)

    return {
        "item_count": len(items),
        "order_total": order_total,
        "new_products": new_product_count,
    }


# ---------------------------------------------------------------------------
# Purchase pattern computation
# ---------------------------------------------------------------------------

def compute_purchase_patterns(conn: sqlite3.Connection, *, dry_run: bool = False) -> int:
    """
    Compute purchase_patterns from order data.

    For each (product_id, store_id) pair:
      - Count total purchases
      - First/last purchase dates
      - Average frequency (days between purchases)
      - Median frequency
      - Average quantity per trip
      - Predict next purchase date
      - Mark as recurring if purchased 3+ times with regular frequency

    Returns number of patterns computed.
    """
    print(f"\n{'=' * 60}")
    print("Computing purchase patterns")
    print(f"{'=' * 60}")

    # Get all (product, store) purchase history
    rows = conn.execute("""
        SELECT
            oi.product_id,
            o.store_id,
            o.order_date,
            oi.quantity
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE oi.product_id IS NOT NULL
        ORDER BY oi.product_id, o.store_id, o.order_date
    """).fetchall()

    if not rows:
        print("  No order data to compute patterns from.")
        return 0

    # Group by (product_id, store_id)
    from collections import defaultdict
    groups = defaultdict(list)
    for row in rows:
        key = (row["product_id"], row["store_id"])
        groups[key].append({
            "date": row["order_date"],
            "quantity": row["quantity"],
        })

    pattern_count = 0

    for (product_id, store_id), purchases in groups.items():
        # Sort by date
        purchases.sort(key=lambda p: p["date"])

        total_purchases = len(purchases)
        first_purchased = purchases[0]["date"]
        last_purchased = purchases[-1]["date"]

        # Average quantity
        quantities = [p["quantity"] for p in purchases]
        avg_quantity = round(sum(quantities) / len(quantities), 2)

        # Compute frequency gaps (days between consecutive purchases)
        avg_freq = None
        median_freq = None
        next_predicted = None
        is_recurring = 0
        confidence = 0.0

        if total_purchases >= 2:
            dates = []
            for p in purchases:
                try:
                    dates.append(datetime.strptime(p["date"], "%Y-%m-%d"))
                except ValueError:
                    continue

            if len(dates) >= 2:
                gaps = []
                for i in range(1, len(dates)):
                    gap = (dates[i] - dates[i - 1]).days
                    if gap > 0:  # Skip same-day duplicates
                        gaps.append(gap)

                if gaps:
                    avg_freq = round(sum(gaps) / len(gaps), 1)
                    median_freq = round(statistics.median(gaps), 1)

                    # Predict next purchase
                    last_date = dates[-1]
                    predicted_gap = median_freq if len(gaps) >= 3 else avg_freq
                    from datetime import timedelta
                    next_predicted = (
                        last_date + timedelta(days=int(predicted_gap))
                    ).strftime("%Y-%m-%d")

                    # Mark as recurring if 3+ purchases with coefficient of variation < 0.6
                    if total_purchases >= 3 and len(gaps) >= 2:
                        mean_gap = sum(gaps) / len(gaps)
                        if mean_gap > 0:
                            stdev = statistics.stdev(gaps) if len(gaps) > 1 else 0
                            cv = stdev / mean_gap
                            if cv < 0.6:
                                is_recurring = 1
                                confidence = round(max(0, 1.0 - cv), 3)
                            else:
                                confidence = round(max(0, 0.5 - (cv - 0.6)), 3)

        if not dry_run:
            conn.execute(
                """INSERT INTO purchase_patterns
                   (product_id, store_id, total_purchases, first_purchased,
                    last_purchased, avg_frequency_days, median_frequency_days,
                    avg_quantity, next_predicted_date, confidence_score, is_recurring)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(product_id, store_id) DO UPDATE SET
                    total_purchases = excluded.total_purchases,
                    first_purchased = excluded.first_purchased,
                    last_purchased = excluded.last_purchased,
                    avg_frequency_days = excluded.avg_frequency_days,
                    median_frequency_days = excluded.median_frequency_days,
                    avg_quantity = excluded.avg_quantity,
                    next_predicted_date = excluded.next_predicted_date,
                    confidence_score = excluded.confidence_score,
                    is_recurring = excluded.is_recurring,
                    updated_at = datetime('now')
                """,
                (
                    product_id, store_id, total_purchases, first_purchased,
                    last_purchased, avg_freq, median_freq,
                    avg_quantity, next_predicted, confidence, is_recurring,
                ),
            )

        pattern_count += 1

    if not dry_run:
        conn.commit()

    recurring_count = sum(
        1 for (_, _), purchases in groups.items()
        if len(purchases) >= 3
    )

    print(f"  Computed {pattern_count} product patterns")
    print(f"  Recurring items (3+ purchases): {recurring_count}")

    return pattern_count


# ---------------------------------------------------------------------------
# Costco instructions
# ---------------------------------------------------------------------------

def print_costco_instructions(costco_dir: str | None = None):
    """Print instructions for importing Costco PDFs via the AI bill parser."""
    print(f"\n{'=' * 60}")
    print("Costco PDF Import — AI Parser Required")
    print(f"{'=' * 60}")
    print()
    print("Costco receipts are unstructured PDFs that require AI extraction.")
    print("They cannot be imported with this script directly.")
    print()

    if costco_dir and os.path.isdir(costco_dir):
        # Count PDFs in subdirectories
        costco_path = Path(costco_dir)
        subdirs = {
            "Groceries": costco_path / "Groceries",
            "Online": costco_path / "Online",
            "Warehose": costco_path / "Warehose",  # Intentional typo
        }
        print("Detected Costco bill folders:")
        total = 0
        for name, subdir in subdirs.items():
            if subdir.is_dir():
                pdfs = list(subdir.glob("*.pdf")) + list(subdir.glob("*.PDF"))
                count = len(pdfs)
                total += count
                print(f"  {name}/: {count} PDFs")
            else:
                # Try without the typo too
                alt = costco_path / name.replace("Warehose", "Warehouse")
                if alt.is_dir():
                    pdfs = list(alt.glob("*.pdf")) + list(alt.glob("*.PDF"))
                    count = len(pdfs)
                    total += count
                    print(f"  {name}/: {count} PDFs")
                else:
                    print(f"  {name}/: (not found)")
        print(f"  Total: {total} PDFs pending import")
    else:
        print("Expected Costco bill structure:")
        print("  Costco_Bills/")
        print("    Groceries/   (Same-Day delivery receipts)")
        print("    Online/      (Costco.com order confirmations)")
        print("    Warehose/    (In-store warehouse receipts)")
    print()
    print("To import Costco PDFs, use the AI bill parser (per CLAUDE_V2.md):")
    print()
    print("  1. Ensure your AI provider is configured in backend/.env")
    print("     (GEMINI_API_KEY or ANTHROPIC_API_KEY)")
    print()
    print("  2. Run the AI bill parser (to be built):")
    print("     python scripts/parse_bills_ai.py --source costco \\")
    print("       --costco-dir /path/to/Costco_Bills \\")
    print("       --db-path backend/data/spendiq_v2.db")
    print()
    print("  The AI parser will:")
    print("    - Extract text from each PDF using pdfplumber")
    print("    - Send text to Gemini/Claude for structured extraction")
    print("    - Parse order totals, item names, quantities, prices")
    print("    - Extract package sizes (e.g., '1 lb', '5 oz', '64 fl oz')")
    print("    - Map to Costco store_id=1 with appropriate categories:")
    print("        Groceries/ -> category 'Groceries' (id=1)")
    print("        Online/    -> category 'Online' (id=2)")
    print("        Warehose/  -> category 'Warehouse' (id=3)")
    print()


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def print_summary(conn: sqlite3.Connection, stats: dict, *, dry_run: bool = False):
    """Print final summary statistics."""
    prefix = "[DRY RUN] " if dry_run else ""

    print(f"\n{'=' * 60}")
    print(f"{prefix}Migration Summary")
    print(f"{'=' * 60}")

    # Import stats
    print(f"\n  Walmart Orders:")
    print(f"    {prefix}Imported:       {stats.get('orders', 0)}")
    print(f"    Skipped (dupes): {stats.get('skipped', 0)}")
    print(f"    Errors:          {stats.get('errors', 0)}")
    print(f"    Total items:     {stats.get('items', 0)}")
    print(f"    New products:    {stats.get('products', 0)}")

    if stats.get("patterns", 0):
        print(f"\n  Purchase Patterns: {stats['patterns']}")

    # Query actual DB counts if not dry run
    if not dry_run:
        try:
            counts = {}
            for table in ["products", "product_aliases", "orders", "order_items", "purchase_patterns"]:
                row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                counts[table] = row["cnt"] if row else 0

            print(f"\n  Database totals:")
            print(f"    Products:          {counts['products']}")
            print(f"    Product aliases:   {counts['product_aliases']}")
            print(f"    Orders:            {counts['orders']}")
            print(f"    Order items:       {counts['order_items']}")
            print(f"    Purchase patterns: {counts['purchase_patterns']}")

            # Top 10 most purchased products
            top = conn.execute("""
                SELECT p.canonical_name, pp.total_purchases, pp.avg_frequency_days,
                       pp.is_recurring
                FROM purchase_patterns pp
                JOIN products p ON pp.product_id = p.id
                ORDER BY pp.total_purchases DESC
                LIMIT 10
            """).fetchall()

            if top:
                print(f"\n  Top 10 most purchased products:")
                for row in top:
                    freq = f"every {row['avg_frequency_days']:.0f}d" if row["avg_frequency_days"] else "n/a"
                    recurring = " [recurring]" if row["is_recurring"] else ""
                    print(f"    {row['total_purchases']:3d}x  {row['canonical_name'][:45]:<45}  {freq}{recurring}")

            # By-weight products
            weight_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM product_aliases WHERE sold_by = 'weight'"
            ).fetchone()
            if weight_count and weight_count["cnt"]:
                print(f"\n  Products sold by weight: {weight_count['cnt']}")

        except sqlite3.OperationalError as e:
            print(f"\n  (Could not query DB stats: {e})")

    if dry_run:
        print(f"\n  ** DRY RUN — no changes were written to disk **")

    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SpendIQ v2 Migration: Create database and import structured data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/migrate_v2.py --walmart-dir /path/to/Walmart_Bills
  python scripts/migrate_v2.py --walmart-dir /path/to/Walmart_Bills --dry-run
  python scripts/migrate_v2.py --costco --costco-dir /path/to/Costco_Bills
        """,
    )
    parser.add_argument(
        "--walmart-dir",
        default=None,
        help="Path to directory containing Walmart .xlsx order files",
    )
    parser.add_argument(
        "--costco-dir",
        default=None,
        help="Path to directory containing Costco PDF receipts (subfolders: Groceries/, Online/, Warehose/)",
    )
    parser.add_argument(
        "--costco",
        action="store_true",
        help="Print instructions for Costco PDF import via AI parser",
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to v2 database file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be imported without writing to the database",
    )
    args = parser.parse_args()

    # Must specify at least one action
    if not args.walmart_dir and not args.costco:
        parser.print_help()
        print("\nError: Specify --walmart-dir and/or --costco")
        sys.exit(1)

    # Handle Costco instructions
    if args.costco:
        print_costco_instructions(args.costco_dir)
        if not args.walmart_dir:
            return  # Nothing else to do

    # Create / open v2 database
    conn = create_v2_database(args.db_path, dry_run=args.dry_run)

    stats = {}

    # Import Walmart
    if args.walmart_dir:
        walmart_stats = import_walmart_orders(
            conn, args.walmart_dir, dry_run=args.dry_run,
        )
        stats.update(walmart_stats)

        # Compute purchase patterns
        if walmart_stats["orders"] > 0 or not args.dry_run:
            pattern_count = compute_purchase_patterns(conn, dry_run=args.dry_run)
            stats["patterns"] = pattern_count

    # Print summary
    print_summary(conn, stats, dry_run=args.dry_run)

    conn.close()

    if not args.dry_run:
        print(f"Database saved to: {args.db_path}")


if __name__ == "__main__":
    main()
