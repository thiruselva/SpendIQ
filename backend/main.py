"""
SpendIQ — FastAPI Backend
All API routes for the SpendIQ personal spending intelligence app.
Runs on port 8765, connects to local SQLite database.
"""

import os
import json
import shutil
import tempfile
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from database import (
    get_db, init_db,
    get_unit_conversions, compute_price_per_unit,
    find_or_create_store, find_or_create_product, find_or_create_alias,
)
from datetime import date
from intelligence.engine import IntelligenceEngine
from intelligence.patterns import get_patterns_for_store
from intelligence.comparisons import get_top_savings_opportunities

load_dotenv(override=True)

app = FastAPI(title="SpendIQ API", version="1.0.0")

# CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ──────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()



# ── v2: Orders ──

@app.get("/api/v2/orders")
async def v2_list_orders(
    store: str | None = None,
    category: str | None = None,
    month: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0
):
    """List orders with filters."""
    db = get_db()
    query = """
        SELECT o.*, s.name as store_name, c.name as category_name
        FROM orders o
        JOIN stores s ON o.store_id = s.id
        LEFT JOIN categories c ON o.category_id = c.id
        WHERE 1=1
    """
    params = []

    if store:
        query += " AND s.name = ?"
        params.append(store)
    if category:
        query += " AND LOWER(c.name) = ?"
        params.append(category.lower())
    if month:
        query += " AND strftime('%Y-%m', o.order_date) = ?"
        params.append(month)
    if search:
        query += " AND (s.name LIKE ? OR o.order_number LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    query += " ORDER BY o.order_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(row) for row in rows]


@app.get("/api/v2/orders/{order_id}/items")
async def v2_order_items(order_id: int):
    """Get order items with unit-normalized pricing."""
    db = get_db()
    rows = db.execute("""
        SELECT oi.*, p.canonical_name, p.standard_unit,
               pa.package_size, pa.package_unit, pa.package_count,
               pa.standard_units_per_package
        FROM order_items oi
        LEFT JOIN products p ON oi.product_id = p.id
        LEFT JOIN product_aliases pa ON oi.alias_id = pa.id
        WHERE oi.order_id = ?
        ORDER BY oi.id
    """, (order_id,)).fetchall()
    db.close()
    return [dict(row) for row in rows]


# ── v2: Import ──

@app.post("/api/v2/import/bills")
async def v2_import_bills(file: UploadFile):
    """
    Upload a bill (PDF or Excel) for AI-powered parsing into v2 schema.
    Extracts package sizes and computes unit-normalized prices.
    """
    from ai.bill_parser import parse_bill, enrich_walmart_products
    from parsers.pdf_parser import extract_text_from_pdf as pdf_extract_text

    db = get_db()
    conversions = get_unit_conversions(db)
    filename = file.filename or "unknown"
    ext = filename.lower().rsplit(".", 1)[-1]

    # Extract text based on file type
    if ext == "pdf":
        # Save temp file, extract text with pdfplumber
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        bill_text = pdf_extract_text(tmp_path)
        parsed = await parse_bill(bill_text, source_type="pdf", filename=filename)
        os.unlink(tmp_path)

    elif ext in ("xlsx", "xls", "csv"):
        import tempfile, pandas as pd
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        if ext == "csv":
            df = pd.read_csv(tmp_path)
        else:
            df = pd.read_excel(tmp_path, engine="openpyxl")

        # Convert DataFrame to text for AI parsing
        bill_text = df.to_string()
        parsed = await parse_bill(bill_text, source_type="excel", filename=filename)
        os.unlink(tmp_path)
    else:
        db.close()
        return {"error": f"Unsupported file type: {ext}"}

    if not parsed or not parsed.get("items"):
        db.close()
        return {"error": "No items extracted from bill", "parsed": parsed}

    # Insert into v2 schema
    store_name = parsed.get("store") or "Unknown"
    store_id = find_or_create_store(db, store_name)

    order_number = parsed.get("order_number") or f"import_{filename}"

    # Check for duplicate order
    existing = db.execute(
        "SELECT id FROM orders WHERE store_id = ? AND order_number = ?",
        (store_id, order_number)
    ).fetchone()
    if existing:
        db.close()
        return {"status": "skipped", "reason": "duplicate order", "order_id": existing["id"]}

    # Insert order
    cursor = db.execute("""
        INSERT INTO orders (store_id, order_number, order_date, payment_method,
                           subtotal_before_savings, savings, subtotal,
                           delivery_charges, tax, tip, order_total, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        store_id, order_number,
        parsed.get("order_date") or date.today().isoformat(),
        parsed.get("payment_method"),
        parsed.get("subtotal", 0), parsed.get("savings", 0), parsed.get("subtotal", 0),
        parsed.get("delivery_charges", 0), parsed.get("tax", 0),
        parsed.get("tip", 0), parsed.get("total", 0), filename,
    ))
    order_id = cursor.lastrowid

    # Insert items
    items_inserted = 0
    for item in parsed["items"]:
        product_name = item.get("product_name", "Unknown")
        brand = item.get("brand")
        pkg_unit = item.get("package_unit")
        pkg_size = item.get("package_size")

        # Determine standard unit from package_unit
        standard_unit = None
        unit_category = None
        if pkg_unit and pkg_unit in conversions:
            standard_unit = conversions[pkg_unit]["to_standard"]
            unit_category = conversions[pkg_unit]["category"]

        # Find or create product
        product_id = find_or_create_product(db, product_name, brand, standard_unit, unit_category)

        # Find or create alias
        alias_id = find_or_create_alias(db, product_id, store_id, product_name, {
            "package_size": pkg_size,
            "package_unit": pkg_unit,
            "package_count": item.get("package_count", 1),
            "store_item_number": None,
            "sold_by": item.get("sold_by", "unit"),
        }, conversions)

        # Compute unit-normalized pricing
        alias = db.execute("SELECT * FROM product_aliases WHERE id = ?", (alias_id,)).fetchone()
        quantity = item.get("quantity", 1)
        unit_price = item.get("unit_price", 0)
        total_price = item.get("total_price") or (quantity * unit_price)

        total_std_units = None
        price_per_std = None
        if alias and alias["standard_units_per_package"]:
            sold_by = alias["sold_by"]
            if sold_by == "weight" and pkg_unit and pkg_unit in conversions:
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

        # Record price history
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

        items_inserted += 1

    db.commit()

    # Refresh intelligence after import
    engine = IntelligenceEngine(db)
    engine.refresh()
    db.close()

    return {
        "status": "imported",
        "order_id": order_id,
        "store": store_name,
        "items_count": items_inserted,
        "order_total": parsed.get("total", 0),
    }


# ── v2: Products ──

@app.get("/api/v2/products")
async def v2_list_products(search: str | None = None, limit: int = 50):
    """Product catalog with search."""
    db = get_db()
    query = """
        SELECT p.*, COUNT(DISTINCT pa.store_id) as store_count
        FROM products p
        LEFT JOIN product_aliases pa ON pa.product_id = p.id
    """
    params = []
    if search:
        query += " WHERE p.canonical_name LIKE ?"
        params.append(f"%{search}%")
    query += " GROUP BY p.id ORDER BY p.canonical_name LIMIT ?"
    params.append(limit)
    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(row) for row in rows]


@app.get("/api/v2/products/{product_id}/prices")
async def v2_product_prices(product_id: int):
    """Price history for a product across stores, with $/unit."""
    db = get_db()
    rows = db.execute("""
        SELECT ph.*, s.name as store_name
        FROM price_history ph
        JOIN stores s ON ph.store_id = s.id
        WHERE ph.product_id = ?
        ORDER BY ph.recorded_date DESC
    """, (product_id,)).fetchall()
    db.close()
    return [dict(row) for row in rows]


# ── v2: Dashboard ──

@app.get("/api/v2/dashboard/summary")
async def v2_dashboard_summary():
    """Dashboard KPIs including savings potential."""
    db = get_db()
    from datetime import date as dt, timedelta as td

    thirty_days_ago = (dt.today() - td(days=30)).isoformat()
    ninety_days_ago = (dt.today() - td(days=90)).isoformat()

    summary_30 = db.execute("""
        SELECT COALESCE(SUM(order_total), 0) as total, COUNT(*) as count
        FROM orders WHERE order_date >= ?
    """, (thirty_days_ago,)).fetchone()

    summary_90 = db.execute("""
        SELECT COALESCE(SUM(order_total), 0) as total, COUNT(*) as count
        FROM orders WHERE order_date >= ?
    """, (ninety_days_ago,)).fetchone()

    # Savings potential
    engine = IntelligenceEngine(db)
    savings = engine.get_savings_summary()

    db.close()
    return {
        "total_30d": round(summary_30["total"], 2),
        "count_30d": summary_30["count"],
        "total_90d": round(summary_90["total"], 2),
        "count_90d": summary_90["count"],
        "avg_order": round(summary_90["total"] / max(summary_90["count"], 1), 2),
        "savings": savings,
    }


@app.get("/api/v2/dashboard/category-breakdown")
async def v2_category_breakdown():
    """Spend per store (v2 uses stores, not categories like v1)."""
    db = get_db()
    rows = db.execute("""
        SELECT s.name as store, ROUND(SUM(o.order_total), 2) as total, COUNT(*) as count
        FROM orders o
        JOIN stores s ON o.store_id = s.id
        WHERE o.order_total IS NOT NULL
        GROUP BY s.name
        ORDER BY total DESC
    """).fetchall()
    db.close()
    return [dict(row) for row in rows]


@app.get("/api/v2/dashboard/monthly-trend")
async def v2_monthly_trend():
    """Monthly spending totals."""
    db = get_db()
    rows = db.execute("""
        SELECT strftime('%Y-%m', order_date) as month,
               ROUND(SUM(order_total), 2) as total,
               COUNT(*) as orders
        FROM orders
        WHERE order_total IS NOT NULL
        GROUP BY month
        ORDER BY month
    """).fetchall()
    db.close()
    return [dict(row) for row in rows]


# ── v2: Insights ──

@app.get("/api/v2/insights/patterns")
async def v2_patterns(store: str | None = None, min_confidence: float = 0.30):
    """Purchase patterns, optionally filtered by store."""
    db = get_db()
    if store:
        store_row = db.execute("SELECT id FROM stores WHERE name = ?", (store,)).fetchone()
        if not store_row:
            db.close()
            return []
        patterns = get_patterns_for_store(db, store_row["id"], min_confidence)
    else:
        rows = db.execute("""
            SELECT pp.*, p.canonical_name, p.brand, p.standard_unit, s.name as store_name
            FROM purchase_patterns pp
            JOIN products p ON pp.product_id = p.id
            JOIN stores s ON pp.store_id = s.id
            WHERE pp.confidence_score >= ?
            ORDER BY pp.confidence_score DESC
        """, (min_confidence,)).fetchall()
        patterns = [dict(row) for row in rows]
    db.close()
    return patterns


@app.get("/api/v2/insights/comparisons")
async def v2_comparisons():
    """Cross-store price comparisons with unit-normalized pricing."""
    db = get_db()
    rows = db.execute("""
        SELECT spc.*, p.canonical_name, p.standard_unit,
               s_cheap.name as cheapest_store_name,
               s_exp.name as most_expensive_store_name
        FROM store_price_compare spc
        JOIN products p ON spc.product_id = p.id
        JOIN stores s_cheap ON spc.cheapest_store_id = s_cheap.id
        JOIN stores s_exp ON spc.most_expensive_store_id = s_exp.id
        ORDER BY spc.potential_monthly_saving DESC NULLS LAST
    """).fetchall()
    db.close()
    return [dict(row) for row in rows]


@app.get("/api/v2/insights/savings")
async def v2_savings():
    """Actionable savings tips — top opportunities to save money."""
    db = get_db()
    opportunities = get_top_savings_opportunities(db, limit=15)
    db.close()
    return opportunities


# ── v2: Shopping Lists ──

@app.post("/api/v2/shopping-list/generate")
async def v2_generate_shopping_list(store: str = "Costco", period_type: str = "weekly"):
    """Generate a smart shopping list using intelligence engine."""
    db = get_db()
    store_row = db.execute("SELECT id FROM stores WHERE name = ?", (store,)).fetchone()
    if not store_row:
        db.close()
        return {"error": f"Store '{store}' not found"}

    engine = IntelligenceEngine(db)
    result = engine.generate_shopping_list(store_row["id"], period_type)
    db.close()
    return result


@app.get("/api/v2/shopping-list/{list_id}")
async def v2_get_shopping_list(list_id: int):
    """Get a shopping list with items and savings tips."""
    db = get_db()
    engine = IntelligenceEngine(db)
    result = engine._get_list_detail(list_id)
    db.close()
    if not result.get("list"):
        return {"error": "List not found"}
    return result


@app.put("/api/v2/shopping-list/{list_id}/feedback")
async def v2_shopping_feedback(list_id: int, feedback: list[dict]):
    """
    Record what was actually bought/skipped after shopping.
    Expects: [{ product_id, was_purchased, actual_qty, actual_price, note }]
    """
    db = get_db()
    for fb in feedback:
        db.execute("""
            INSERT INTO shopping_feedback
            (list_id, product_id, was_predicted, was_purchased,
             actual_qty, actual_price, feedback_note)
            VALUES (?, ?, 1, ?, ?, ?, ?)
        """, (
            list_id, fb["product_id"],
            1 if fb.get("was_purchased") else 0,
            fb.get("actual_qty"),
            fb.get("actual_price"),
            fb.get("note"),
        ))

    # Mark list as completed
    db.execute(
        "UPDATE shopping_lists SET status = 'completed', completed_at = datetime('now') WHERE id = ?",
        (list_id,)
    )
    db.commit()

    # Refresh intelligence with new data
    engine = IntelligenceEngine(db)
    engine.refresh()
    db.close()

    return {"status": "feedback recorded", "items": len(feedback)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=True)
