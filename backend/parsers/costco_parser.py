"""
Costco Parser — Parse Costco Same-Day receipt PDFs.

Costco receipts have:
  - Date in header: "5/18/26, 4:42 PM"
  - Order ID: "Order ID: # 19169187152450000"
  - Items: "1 x Product Name $price"
  - Discounts: "✓ Save $X"

Uses regex for structured extraction, AI fallback for complex layouts.
"""

import os
import re
from datetime import datetime
import pdfplumber


def _extract_text(filepath: str) -> str:
    """Extract full text from all PDF pages."""
    with pdfplumber.open(filepath) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def _parse_date(text: str) -> str | None:
    """Extract date from Costco receipt header."""
    # Pattern: "5/18/26, 4:42 PM" or "05/18/2026"
    patterns = [
        (r"(\d{1,2}/\d{1,2}/\d{2}),\s*\d{1,2}:\d{2}\s*[AP]M", "%m/%d/%y"),
        (r"(\d{1,2}/\d{1,2}/\d{4})", "%m/%d/%Y"),
        (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
    ]
    for pattern, fmt in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def _parse_order_id(text: str) -> str | None:
    """Extract Costco order ID."""
    match = re.search(r"Order\s*ID:\s*#?\s*(\d+)", text)
    return match.group(1) if match else None


def _parse_items_regex(text: str) -> list[dict]:
    """
    Extract items using regex patterns.
    Handles formats like:
      1 x Organic Baby Spinach, 1 lb $4.87
      1 x WestEnd Cuisine Grilled Chicken $16.33
    """
    items = []

    # Primary pattern: "N x Product Name $price" (may span multiple lines)
    # Split by the item pattern to process each block
    item_blocks = re.split(r"(?=\d+\s+x\s+)", text)

    for block in item_blocks:
        # Match: quantity x product_name ... $price
        match = re.match(
            r"(\d+)\s+x\s+(.+?)\s+\$(\d+\.?\d*)",
            block,
            re.DOTALL
        )
        if not match:
            continue

        quantity = float(match.group(1))
        product_name = match.group(2).strip()
        # Clean up product name (remove line breaks, extra whitespace)
        product_name = re.sub(r"\s+", " ", product_name)
        # Remove trailing price-like patterns that got captured
        product_name = re.sub(r"\s*\$\d+\.?\d*\s*$", "", product_name)
        price = float(match.group(3))

        # Check for discount (Save $X)
        discount = 0.0
        save_match = re.search(r"Save\s+\$(\d+\.?\d*)", block)
        if save_match:
            discount = float(save_match.group(1))

        # Look for item number
        item_num = None
        item_match = re.search(r"Item\s+(\d+)", block)
        if item_match:
            item_num = item_match.group(1)

        items.append({
            "product_name": product_name,
            "quantity": quantity,
            "unit_price": price,
            "total_price": price,  # Price shown is already the line total
            "item_status": "Delivered",
            "item_number": item_num,
            "discount": discount,
        })

    return items


def parse_costco_receipt(filepath: str, order_date: str | None = None) -> dict:
    """
    Parse a Costco Same-Day receipt PDF.

    Args:
        filepath: Path to the PDF file.
        order_date: Optional YYYY-MM-DD override. If None, extracted from PDF.

    Returns:
        {
            "transaction": { date, vendor, amount, category, source, file_name },
            "line_items": [ { product_name, quantity, unit_price, total_price, ... } ]
        }
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Costco file not found: {filepath}")

    text = _extract_text(filepath)

    # Extract date
    if not order_date:
        order_date = _parse_date(text)
    if not order_date:
        # Fallback to file modification time
        mtime = os.path.getmtime(filepath)
        order_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

    # Extract order ID
    order_id = _parse_order_id(text)

    # Extract items
    line_items = _parse_items_regex(text)

    # Calculate order total (sum of item prices minus discounts)
    order_total = sum(
        (item["total_price"] or 0) - (item["discount"] or 0)
        for item in line_items
    )

    filename = os.path.basename(filepath)

    return {
        "transaction": {
            "date": order_date,
            "vendor": "Costco Wholesale",
            "amount": round(order_total, 2) if order_total > 0 else None,
            "category": "grocery",
            "source": "upload",
            "file_name": filename,
            "raw_text": text[:3000],  # Store first 3000 chars for reference
        },
        "line_items": line_items,
        "order_id": order_id,
    }


def parse_costco_folder(folder: str) -> list[dict]:
    """
    Parse all Costco receipt PDFs in a folder.

    Returns:
        List of { transaction, line_items } dicts.
    """
    results = []
    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith(".pdf"):
            continue
        filepath = os.path.join(folder, filename)
        try:
            result = parse_costco_receipt(filepath)
            items_count = len(result["line_items"])
            total = result["transaction"]["amount"]
            print(f"  ✓ {filename}: {items_count} items, ${total}")
            results.append(result)
        except Exception as e:
            print(f"  ✗ {filename}: {e}")
    return results
