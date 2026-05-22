"""
Walmart Parser — Parse Walmart order Excel exports (.xlsx).

Walmart exports have columns:
  Product Name | Quantity | Price | Delivery Status | Product Link

Each file = one order. The parser:
1. Reads all items from the Excel
2. Sums prices for the order total
3. Returns a transaction dict + list of line_item dicts
"""

import os
from datetime import datetime
import pandas as pd


def parse_walmart_order(filepath: str, order_date: str | None = None) -> dict:
    """
    Parse a Walmart order Excel file.

    Args:
        filepath: Path to the .xlsx file.
        order_date: Optional YYYY-MM-DD date. If None, uses file modification date.

    Returns:
        {
            "transaction": { date, vendor, amount, category, source, file_name },
            "line_items": [ { product_name, quantity, unit_price, total_price, item_status } ]
        }
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Walmart file not found: {filepath}")

    df = pd.read_excel(filepath, engine="openpyxl")

    # Validate expected columns
    expected = {"Product Name", "Price"}
    found = set(df.columns)
    if not expected.issubset(found):
        raise ValueError(
            f"Not a Walmart order format. Expected columns {expected}, "
            f"found: {list(df.columns)}"
        )

    # Determine order date
    if not order_date:
        # Use file modification time as fallback
        mtime = os.path.getmtime(filepath)
        order_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

    # Parse line items
    line_items = []
    order_total = 0.0

    for _, row in df.iterrows():
        product_name = str(row.get("Product Name", "Unknown")).strip()
        if not product_name or product_name == "nan":
            continue

        quantity = row.get("Quantity", 1)
        if pd.isna(quantity):
            quantity = 1.0
        else:
            try:
                quantity = float(str(quantity).replace(",", ""))
            except (ValueError, TypeError):
                quantity = 1.0

        price = row.get("Price")
        if pd.isna(price):
            price = None
        else:
            try:
                price = float(str(price).replace("$", "").replace(",", "").strip())
            except (ValueError, TypeError):
                price = None

        status = str(row.get("Delivery Status", "")).strip()
        if status == "nan":
            status = None

        total_price = price * quantity if price else None

        line_items.append({
            "product_name": product_name,
            "quantity": quantity,
            "unit_price": price,
            "total_price": total_price,
            "item_status": status,
        })

        if total_price:
            order_total += total_price

    filename = os.path.basename(filepath)

    return {
        "transaction": {
            "date": order_date,
            "vendor": "Walmart Supercenter",
            "amount": round(order_total, 2) if order_total > 0 else None,
            "category": "grocery",
            "source": "upload",
            "file_name": filename,
        },
        "line_items": line_items,
    }


def parse_walmart_folder(folder: str) -> list[dict]:
    """
    Parse all Walmart order Excel files in a folder.

    Returns:
        List of { transaction, line_items } dicts.
    """
    results = []
    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith((".xlsx", ".xls")):
            continue
        filepath = os.path.join(folder, filename)
        try:
            result = parse_walmart_order(filepath)
            results.append(result)
            print(f"  ✓ {filename}: {len(result['line_items'])} items, ${result['transaction']['amount']}")
        except Exception as e:
            print(f"  ✗ {filename}: {e}")
    return results
