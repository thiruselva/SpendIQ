"""
AI Bill Parser — Unified parser for Costco and Walmart bills.
Extracts structured data INCLUDING package sizes and units for
unit-normalized price comparison.

Replaces: parsers/walmart_parser.py, parsers/costco_parser.py
"""

import json
import os
from typing import Optional
from .provider import call_llm, get_provider, clean_json_response

# ── Extraction prompt ──
BILL_EXTRACTION_PROMPT = """You are a receipt parser. Extract structured data from this grocery bill.

Return ONLY valid JSON with this exact structure:
{{
  "store": "Costco" or "Walmart" (detect from receipt content),
  "order_number": "order/confirmation number or null",
  "order_date": "YYYY-MM-DD",
  "payment_method": "payment info or null",
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "savings": 0.00,
  "delivery_charges": 0.00,
  "tip": 0.00,
  "items": [
    {{
      "product_name": "exact product name from receipt",
      "brand": "brand name if visible (omit if null)",
      "quantity": 1.0,
      "unit_price": 0.00,
      "total_price": 0.00,
      "package_size": 5.0,  # (omit if null)
      "package_unit": "oz", # (omit if null)
      "package_count": 1,   # (omit if 1)
      "sold_by": "unit",    # (omit if "unit")
      "savings_amount": 0.00, # (omit if 0.00)
      "was_on_sale": false,  # (omit if false)
      "delivery_status": "Delivered" # (omit if null or "Delivered")
    }}
  ]
}}

CRITICAL rules for package extraction:
1. "Organic Baby Spinach, 1 lb" -> package_size: 1.0, package_unit: "lb", package_count: 1
2. "Marketside Baby Spinach, 5 oz" -> package_size: 5.0, package_unit: "oz", package_count: 1
3. "Kirkland Whole Milk, 3 x 1/2 gallon" -> package_size: 1, package_unit: "half_gallon", package_count: 3
4. "Bounty Paper Towels 12-pack" -> package_size: 12, package_unit: "count", package_count: 1
5. "Bananas, 3.77 lb" priced per lb -> sold_by: "weight", quantity: 3.77
6. For items where size is not on receipt, omit package_size and package_unit
7. package_unit values: oz, lb, kg, g, fl_oz, gallon, half_gallon, quart, pint, liter, ml, each, pack, count, ct, loads, bag, bunch
8. sold_by: "unit" = buy 1 package at fixed price, "weight" = priced per lb/oz
9. COMPACTNESS: To fit within output limits, omit any key in the "items" array if its value is null, 0.00, false, 1 (for package_count), or "unit" (for sold_by). Only include fields with non-default values.

Bill content:
{bill_text}"""

# ── Walmart Excel extraction prompt ──
WALMART_PRODUCT_ENRICHMENT_PROMPT = """Given these Walmart product names from an order, extract package size information.

Return ONLY a valid JSON array. For each product, determine:
- brand: the brand name if identifiable
- package_size: numeric size value (5 for "5 oz bag")
- package_unit: unit string (oz, lb, fl_oz, gallon, count, etc.)
- package_count: number of items in multi-pack (default 1)
- sold_by: "unit" or "weight"

If you cannot determine the size from the name, use null values.

Products:
{products_json}"""


async def parse_bill(bill_text: str, source_type: str = "pdf",
                     filename: str = "") -> dict:
    """
    Parse a bill using AI extraction.

    Args:
        bill_text: Extracted text from PDF (via pdfplumber) or Excel (via pandas)
        source_type: "pdf" or "excel"
        filename: Original filename for logging

    Returns:
        Structured dict matching the JSON schema above.
    """
    if not get_provider():
        return _fallback_parse(bill_text, filename)

    try:
        model_tier = "vision" if source_type == "pdf" else "fast"
        raw = call_llm(
            prompt=BILL_EXTRACTION_PROMPT.format(bill_text=bill_text[:6000]),
            model_tier=model_tier,
            max_tokens=8192,
        )
        raw = clean_json_response(raw)
        data = json.loads(raw)

        # Validate required fields
        if "items" not in data or not isinstance(data["items"], list):
            print(f"[BillParser] No items array in response for {filename}")
            return _fallback_parse(bill_text, filename)

        return data

    except json.JSONDecodeError as e:
        print(f"[BillParser] JSON decode error for {filename}: {e}")
        return _fallback_parse(bill_text, filename)
    except Exception as e:
        print(f"[BillParser] AI extraction failed for {filename}: {e}")
        return _fallback_parse(bill_text, filename)


async def enrich_walmart_products(product_names: list[str]) -> list[dict]:
    """
    Use AI to extract package sizes from Walmart product names.
    Called after pandas reads the Excel, since Walmart columns lack size info.

    Args:
        product_names: List of product name strings from the Excel.

    Returns:
        List of dicts with brand, package_size, package_unit, package_count, sold_by.
    """
    if not get_provider() or not product_names:
        return [{"brand": None, "package_size": None, "package_unit": None,
                 "package_count": 1, "sold_by": "unit"} for _ in product_names]

    try:
        products_json = json.dumps(product_names, indent=2)
        raw = call_llm(
            prompt=WALMART_PRODUCT_ENRICHMENT_PROMPT.format(products_json=products_json),
            model_tier="fast",
            max_tokens=3000,
        )
        raw = clean_json_response(raw)
        enriched = json.loads(raw)
        if isinstance(enriched, list) and len(enriched) == len(product_names):
            return enriched
    except Exception as e:
        print(f"[BillParser] Walmart enrichment failed: {e}")

    return [{"brand": None, "package_size": None, "package_unit": None,
             "package_count": 1, "sold_by": "unit"} for _ in product_names]


def _fallback_parse(bill_text: str, filename: str) -> dict:
    """Basic fallback when AI is unavailable."""
    import re
    from datetime import datetime

    result = {
        "store": None,
        "order_number": None,
        "order_date": None,
        "payment_method": None,
        "subtotal": 0, "tax": 0, "total": 0,
        "savings": 0, "delivery_charges": 0, "tip": 0,
        "items": [],
    }

    # Detect store
    text_lower = bill_text.lower()
    if "costco" in text_lower:
        result["store"] = "Costco"
    elif "walmart" in text_lower:
        result["store"] = "Walmart"

    # Try date extraction
    for pattern, fmt in [
        (r"(\d{1,2}/\d{1,2}/\d{2}),", "%m/%d/%y"),
        (r"(\d{1,2}/\d{1,2}/\d{4})", "%m/%d/%Y"),
        (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
    ]:
        match = re.search(pattern, bill_text)
        if match:
            try:
                result["order_date"] = datetime.strptime(match.group(1), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    # Try order number
    match = re.search(r"Order\s*(?:ID|#|Number)[:\s#]*(\d+)", bill_text, re.IGNORECASE)
    if match:
        result["order_number"] = match.group(1)

    # Basic item extraction: "N x Product Name $price"
    for match in re.finditer(r"(\d+)\s+x\s+(.+?)\s+\$(\d+\.?\d*)", bill_text, re.DOTALL):
        qty = float(match.group(1))
        name = re.sub(r"\s+", " ", match.group(2).strip())
        price = float(match.group(3))
        result["items"].append({
            "product_name": name,
            "brand": None,
            "quantity": qty,
            "unit_price": price,
            "total_price": price,
            "package_size": None,
            "package_unit": None,
            "package_count": 1,
            "sold_by": "unit",
            "savings_amount": 0,
            "was_on_sale": False,
            "delivery_status": None,
        })

    return result
