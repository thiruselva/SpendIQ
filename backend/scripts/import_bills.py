"""
Batch Import — Import all bills from resources/ into SpendIQ database.

Usage:
    cd backend
    ./venv/bin/python scripts/import_bills.py              # Import all
    ./venv/bin/python scripts/import_bills.py --source walmart   # Walmart only
    ./venv/bin/python scripts/import_bills.py --source costco    # Costco only
    ./venv/bin/python scripts/import_bills.py --dry-run          # Preview without inserting
"""

import os
import sys
import argparse

# Add parent directory to path so we can import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

from database import get_db, init_db
from parsers.walmart_parser import parse_walmart_folder
from parsers.costco_parser import parse_costco_folder


RESOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")


def _is_duplicate(db, vendor: str, date: str, file_name: str) -> bool:
    """Check if this order was already imported."""
    row = db.execute(
        "SELECT id FROM transactions WHERE vendor = ? AND date = ? AND file_name = ?",
        (vendor, date, file_name),
    ).fetchone()
    return row is not None


def insert_order(db, order: dict, dry_run: bool = False) -> bool:
    """
    Insert one order (transaction + line_items) into the database.

    Args:
        db: SQLite connection.
        order: { "transaction": {...}, "line_items": [...] }
        dry_run: If True, don't actually insert.

    Returns:
        True if inserted, False if skipped (duplicate).
    """
    tx = order["transaction"]

    # Skip duplicates
    if _is_duplicate(db, tx["vendor"], tx["date"], tx["file_name"]):
        return False

    if dry_run:
        return True

    # Insert transaction
    cursor = db.execute(
        """INSERT INTO transactions (date, vendor, amount, category, source, file_name, raw_text, is_verified)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            tx["date"],
            tx["vendor"],
            tx["amount"],
            tx["category"],
            tx["source"],
            tx["file_name"],
            tx.get("raw_text"),
        ),
    )
    tx_id = cursor.lastrowid

    # Insert line items
    for item in order.get("line_items", []):
        db.execute(
            """INSERT INTO line_items
               (transaction_id, product_name, quantity, unit_price, total_price, item_status, item_number, discount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx_id,
                item["product_name"],
                item.get("quantity", 1),
                item.get("unit_price"),
                item.get("total_price"),
                item.get("item_status"),
                item.get("item_number"),
                item.get("discount", 0),
            ),
        )

    return True


def main():
    parser = argparse.ArgumentParser(description="Import bills from resources/ into SpendIQ")
    parser.add_argument("--source", choices=["walmart", "costco"], help="Import only one source")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    args = parser.parse_args()

    # Ensure DB is initialized
    init_db()
    db = get_db()

    total_inserted = 0
    total_skipped = 0
    total_items = 0

    sources = []
    if args.source in (None, "walmart"):
        walmart_dir = os.path.join(RESOURCES_DIR, "walmart")
        if os.path.isdir(walmart_dir):
            sources.append(("Walmart", walmart_dir, parse_walmart_folder))
    if args.source in (None, "costco"):
        costco_dir = os.path.join(RESOURCES_DIR, "costco")
        if os.path.isdir(costco_dir):
            sources.append(("Costco", costco_dir, parse_costco_folder))

    for name, folder, parser_fn in sources:
        print(f"\n{'='*60}")
        print(f"Importing {name} orders from: {folder}")
        print(f"{'='*60}")

        orders = parser_fn(folder)
        inserted = 0
        skipped = 0
        items = 0

        for order in orders:
            was_inserted = insert_order(db, order, dry_run=args.dry_run)
            if was_inserted:
                inserted += 1
                items += len(order.get("line_items", []))
            else:
                skipped += 1

        if not args.dry_run:
            db.commit()

        total_inserted += inserted
        total_skipped += skipped
        total_items += items

        action = "Would insert" if args.dry_run else "Inserted"
        print(f"\n  {action}: {inserted} orders ({items} line items)")
        if skipped:
            print(f"  Skipped (duplicates): {skipped}")

    db.close()

    print(f"\n{'='*60}")
    print(f"TOTAL: {total_inserted} orders, {total_items} line items")
    if total_skipped:
        print(f"SKIPPED: {total_skipped} duplicates")
    if args.dry_run:
        print("(DRY RUN — nothing was saved)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
