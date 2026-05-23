"""
Batch Import v2 — Import all bills from resources/ into v2 schema.

Usage:
    cd backend
    ./venv/bin/python scripts/import_bills.py              # Import all
    ./venv/bin/python scripts/import_bills.py --source walmart
    ./venv/bin/python scripts/import_bills.py --source costco
    ./venv/bin/python scripts/import_bills.py --dry-run
"""

import os
import sys
import argparse
import asyncio
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

from database import (
    get_db, init_db, get_unit_conversions,
    compute_standard_units, compute_price_per_unit,
    find_or_create_store, find_or_create_product, find_or_create_alias,
)
from intelligence.engine import IntelligenceEngine


RESOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")


def insert_v2_order(db, parsed: dict, conversions: dict, dry_run: bool = False) -> bool:
    """
    Insert a parsed bill into v2 schema.
    parsed: output of ai/bill_parser.parse_bill() or a manually constructed dict.
    Returns True if inserted, False if skipped.
    """
    store_name = parsed.get("store") or "Unknown"
    store_id = find_or_create_store(db, store_name)
    order_number = parsed.get("order_number") or f"batch_{parsed.get('source_file', 'unknown')}"

    # Duplicate check
    existing = db.execute(
        "SELECT id FROM orders WHERE store_id = ? AND order_number = ?",
        (store_id, order_number)
    ).fetchone()
    if existing:
        return False

    if dry_run:
        return True

    category_id = parsed.get("category_id")

    # Insert order
    cursor = db.execute("""
        INSERT INTO orders (store_id, category_id, order_number, order_date, payment_method,
                           subtotal_before_savings, savings, subtotal,
                           delivery_charges, tax, tip, order_total, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        store_id, category_id, order_number,
        parsed.get("order_date") or date.today().isoformat(),
        parsed.get("payment_method"),
        parsed.get("subtotal", 0), parsed.get("savings", 0), parsed.get("subtotal", 0),
        parsed.get("delivery_charges", 0), parsed.get("tax", 0),
        parsed.get("tip", 0), parsed.get("total", 0),
        parsed.get("source_file"),
    ))
    order_id = cursor.lastrowid

    for item in parsed.get("items", []):
        product_name = item.get("product_name", "Unknown")
        brand = item.get("brand")
        pkg_unit = item.get("package_unit")
        pkg_size = item.get("package_size")

        standard_unit = None
        unit_category = None
        if pkg_unit and pkg_unit in conversions:
            standard_unit = conversions[pkg_unit]["to_standard"]
            unit_category = conversions[pkg_unit]["category"]

        product_id = find_or_create_product(db, product_name, brand, standard_unit, unit_category)

        alias_id = find_or_create_alias(db, product_id, store_id, product_name, {
            "package_size": pkg_size,
            "package_unit": pkg_unit,
            "package_count": item.get("package_count", 1),
            "store_item_number": item.get("store_item_number"),
            "sold_by": item.get("sold_by", "unit"),
        }, conversions)

        alias = db.execute("SELECT * FROM product_aliases WHERE id = ?", (alias_id,)).fetchone()
        quantity = item.get("quantity", 1)
        unit_price = item.get("unit_price", 0)
        total_price = item.get("total_price") or (quantity * unit_price)

        total_std_units = None
        price_per_std = None
        if alias and alias["standard_units_per_package"]:
            if alias["sold_by"] == "weight" and pkg_unit and pkg_unit in conversions:
                total_std_units = quantity * conversions[pkg_unit]["multiplier"]
            else:
                total_std_units = quantity * alias["standard_units_per_package"]
            price_per_std = compute_price_per_unit(total_price, total_std_units)

        db.execute("""
            INSERT INTO order_items
            (order_id, product_id, alias_id, raw_product_name,
             quantity, unit_price, total_price,
             total_standard_units, price_per_standard_unit,
             savings_amount, was_on_sale, delivery_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id, product_id, alias_id, product_name,
            quantity, unit_price, total_price,
            total_std_units, price_per_std,
            item.get("savings_amount", 0),
            1 if item.get("was_on_sale") else 0,
            item.get("delivery_status"),
        ))

        if price_per_std is not None:
            db.execute("""
                INSERT OR REPLACE INTO price_history
                (product_id, store_id, alias_id, recorded_date,
                 raw_price, quantity_purchased,
                 package_size, package_unit, package_count,
                 total_standard_units, price_per_standard_unit,
                 was_on_sale, savings_amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_id, store_id, alias_id,
                parsed.get("order_date") or date.today().isoformat(),
                total_price, quantity,
                pkg_size, pkg_unit, item.get("package_count", 1),
                total_std_units, price_per_std,
                1 if item.get("was_on_sale") else 0,
                item.get("savings_amount", 0),
            ))

    return True


async def import_with_ai(folder: str, source: str, db, conversions: dict, dry_run: bool):
    """Import bills using AI parser for full extraction."""
    from ai.bill_parser import parse_bill
    from parsers.pdf_parser import extract_text_from_pdf as pdf_extract_text
    import pandas as pd

    inserted = 0
    skipped = 0
    items = 0

    files_to_process = []
    subfolders_map = {
        "groceries": 1,
        "online": 2,
        "warehose": 3,
        "warehouse": 3
    }

    # Check for subdirectories
    has_subfolders = False
    if os.path.isdir(folder):
        for sub in sorted(os.listdir(folder)):
            sub_path = os.path.join(folder, sub)
            if os.path.isdir(sub_path) and sub.lower() in subfolders_map:
                has_subfolders = True
                cat_id = subfolders_map[sub.lower()]
                for filename in sorted(os.listdir(sub_path)):
                    if filename.lower().endswith((".pdf", ".xlsx", ".xls")) and not filename.startswith("."):
                        files_to_process.append((os.path.join(sub_path, filename), cat_id))

    if not has_subfolders and os.path.isdir(folder):
        for filename in sorted(os.listdir(folder)):
            if filename.lower().endswith((".pdf", ".xlsx", ".xls")) and not filename.startswith("."):
                cat_id = None
                filename_lower = filename.lower()
                if "groceries" in filename_lower:
                    cat_id = 1
                elif "online" in filename_lower:
                    cat_id = 2
                elif "warehouse" in filename_lower or "warehose" in filename_lower:
                    cat_id = 3
                files_to_process.append((os.path.join(folder, filename), cat_id))

    print(f"Found {len(files_to_process)} receipt files to process...")

    import re
    for filepath, cat_id in files_to_process:
        filename = os.path.basename(filepath)
        ext = filename.lower().rsplit(".", 1)[-1]

        # Extract order number from filename for pre-dedup check
        order_num_match = re.search(r'(\d+)', filename)
        if order_num_match:
            order_number = order_num_match.group(1)
            store_id = 2 if source.lower() == "walmart" else 1
            existing = db.execute(
                "SELECT id FROM orders WHERE store_id = ? AND order_number = ?",
                (store_id, order_number)
            ).fetchone()
            if existing:
                skipped += 1
                print(f"  = {filename}: duplicate (pre-checked), skipped")
                continue

        try:
            # Introduce delay to prevent exceeding 15 RPM Gemini rate limit
            await asyncio.sleep(4.5)

            if ext == "pdf":
                bill_text = pdf_extract_text(filepath)
                parsed = await parse_bill(bill_text, source_type="pdf", filename=filename)
            elif ext in ("xlsx", "xls"):
                df = pd.read_excel(filepath, engine="openpyxl")
                bill_text = df.to_string()
                parsed = await parse_bill(bill_text, source_type="excel", filename=filename)
            else:
                continue

            if not parsed or not parsed.get("items"):
                print(f"  ? {filename}: no items extracted")
                continue

            parsed["source_file"] = filename
            if cat_id:
                parsed["category_id"] = cat_id

            was_inserted = insert_v2_order(db, parsed, conversions, dry_run)
            if was_inserted:
                inserted += 1
                items += len(parsed.get("items", []))
                print(f"  + {filename}: {len(parsed['items'])} items")
            else:
                skipped += 1
                print(f"  = {filename}: duplicate, skipped")
        except Exception as e:
            print(f"  ✗ {filename}: error - {e}")

    return inserted, skipped, items


def main():
    parser = argparse.ArgumentParser(description="Import bills into SpendIQ v2")
    parser.add_argument("--source", help="Import only one source (walmart, costco, or directory path)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    args = parser.parse_args()

    init_db()
    db = get_db()
    conversions = get_unit_conversions(db)

    total_inserted = 0
    total_skipped = 0
    total_items = 0

    sources = []
    if args.source and (os.path.isdir(args.source) or os.path.exists(args.source)):
        # Treat as custom directory
        path_lower = args.source.lower()
        if "walmart" in path_lower:
            sources.append(("Walmart", args.source))
        else:
            sources.append(("Costco", args.source))
    else:
        if args.source in (None, "walmart"):
            walmart_dir = os.path.join(RESOURCES_DIR, "walmart")
            if os.path.isdir(walmart_dir):
                sources.append(("Walmart", walmart_dir))
        if args.source in (None, "costco"):
            costco_dir = os.path.join(RESOURCES_DIR, "costco")
            if os.path.isdir(costco_dir):
                sources.append(("Costco", costco_dir))

    for name, folder in sources:
        print(f"\n{'='*60}")
        print(f"Importing {name} orders from: {folder}")
        print(f"{'='*60}")

        inserted, skipped, items = asyncio.run(
            import_with_ai(folder, name.lower(), db, conversions, args.dry_run)
        )

        if not args.dry_run:
            db.commit()

        total_inserted += inserted
        total_skipped += skipped
        total_items += items

        action = "Would insert" if args.dry_run else "Inserted"
        print(f"\n  {action}: {inserted} orders ({items} line items)")
        if skipped:
            print(f"  Skipped (duplicates): {skipped}")

    # Refresh intelligence after all imports
    if not args.dry_run and total_inserted > 0:
        print(f"\n{'='*60}")
        print("Refreshing intelligence engine...")
        engine = IntelligenceEngine(db)
        engine.refresh()

    db.close()

    print(f"\n{'='*60}")
    print(f"TOTAL: {total_inserted} orders, {total_items} line items")
    if total_skipped:
        print(f"SKIPPED: {total_skipped} duplicates")
    if args.dry_run:
        print("(DRY RUN -- nothing was saved)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
