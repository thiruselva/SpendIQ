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

from database import get_db, init_db, categorize_vendor

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
    # Only seed demo data if DEMO_MODE=true in .env
    from demo_data import seed_demo_data
    db = get_db()
    seed_demo_data(db)
    db.close()


# ── Pydantic models ─────────────────────────────────────────────────
class TransactionCreate(BaseModel):
    date: str
    vendor: str
    amount: Optional[float] = None
    category: Optional[str] = None
    source: str = "manual"

class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    is_verified: Optional[int] = None

class ShoppingItemCreate(BaseModel):
    item: str
    store: Optional[str] = None
    frequency: Optional[str] = None
    est_price: Optional[float] = None
    list_type: str = "weekly"

class ShoppingItemUpdate(BaseModel):
    item: Optional[str] = None
    store: Optional[str] = None
    frequency: Optional[str] = None
    est_price: Optional[float] = None
    is_done: Optional[int] = None


# ── Transaction Routes ───────────────────────────────────────────────
@app.get("/api/transactions")
def list_transactions(
    category: Optional[str] = None,
    source: Optional[str] = None,
    month: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    db = get_db()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if source:
        query += " AND source = ?"
        params.append(source)
    if month:
        query += " AND strftime('%Y-%m', date) = ?"
        params.append(month)
    if search:
        query += " AND (vendor LIKE ? OR file_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(query, params).fetchall()
    total = db.execute(
        "SELECT COUNT(*) FROM transactions WHERE 1=1"
        + (" AND category = ?" if category else "")
        + (" AND source = ?" if source else "")
        + (" AND strftime('%Y-%m', date) = ?" if month else "")
        + (" AND (vendor LIKE ? OR file_name LIKE ?)" if search else ""),
        [p for p in params[:-2]],
    ).fetchone()[0]

    db.close()
    return {
        "transactions": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.post("/api/transactions")
def create_transaction(tx: TransactionCreate):
    db = get_db()
    # Auto-categorize if no category provided
    if not tx.category:
        cat, _ = categorize_vendor(tx.vendor)
        tx.category = cat

    cursor = db.execute(
        """INSERT INTO transactions (date, vendor, amount, category, source)
           VALUES (?, ?, ?, ?, ?)""",
        (tx.date, tx.vendor, tx.amount, tx.category, tx.source),
    )
    db.commit()
    new_id = cursor.lastrowid
    row = db.execute("SELECT * FROM transactions WHERE id = ?", (new_id,)).fetchone()
    db.close()
    return dict(row)


@app.put("/api/transactions/{tx_id}")
def update_transaction(tx_id: int, tx: TransactionUpdate):
    db = get_db()
    existing = db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not existing:
        db.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    updates = {}
    if tx.date is not None:
        updates["date"] = tx.date
    if tx.vendor is not None:
        updates["vendor"] = tx.vendor
    if tx.amount is not None:
        updates["amount"] = tx.amount
    if tx.category is not None:
        updates["category"] = tx.category
    if tx.is_verified is not None:
        updates["is_verified"] = tx.is_verified

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(
            f"UPDATE transactions SET {set_clause} WHERE id = ?",
            list(updates.values()) + [tx_id],
        )
        db.commit()

    row = db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    db.close()
    return dict(row)


@app.get("/api/transactions/{tx_id}/items")
def get_transaction_items(tx_id: int):
    """Get all line items for a specific transaction."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM line_items WHERE transaction_id = ? ORDER BY id",
        (tx_id,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int):
    db = get_db()
    existing = db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not existing:
        db.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    db.commit()
    db.close()
    return {"deleted": True, "id": tx_id}


# ── Dashboard Routes ─────────────────────────────────────────────────
@app.get("/api/dashboard/summary")
def dashboard_summary():
    db = get_db()

    total = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE amount IS NOT NULL"
    ).fetchone()[0]

    monthly_avg = db.execute("""
        SELECT COALESCE(AVG(monthly_total), 0) FROM (
            SELECT SUM(amount) as monthly_total
            FROM transactions
            WHERE amount IS NOT NULL
            GROUP BY strftime('%Y-%m', date)
        )
    """).fetchone()[0]

    total_count = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    verified_count = db.execute(
        "SELECT COUNT(*) FROM transactions WHERE amount IS NOT NULL"
    ).fetchone()[0]
    tracked_pct = round((verified_count / total_count * 100) if total_count > 0 else 0, 1)

    subscriptions = db.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM transactions
        WHERE category = 'subscription' AND amount IS NOT NULL
        AND date >= date('now', '-30 days')
    """).fetchone()[0]

    unknown_count = db.execute(
        "SELECT COUNT(*) FROM transactions WHERE amount IS NULL"
    ).fetchone()[0]

    db.close()
    return {
        "total_spent": round(total, 2),
        "monthly_avg": round(monthly_avg, 2),
        "tracked_pct": tracked_pct,
        "subscriptions": round(subscriptions, 2),
        "total_transactions": total_count,
        "unknown_amounts": unknown_count,
    }


@app.get("/api/dashboard/category-breakdown")
def category_breakdown():
    db = get_db()
    rows = db.execute("""
        SELECT category, ROUND(SUM(amount), 2) as total, COUNT(*) as count
        FROM transactions
        WHERE amount IS NOT NULL
        GROUP BY category
        ORDER BY total DESC
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.get("/api/dashboard/monthly-trend")
def monthly_trend():
    db = get_db()
    rows = db.execute("""
        SELECT
            strftime('%Y-%m', date) as month,
            ROUND(SUM(amount), 2) as total,
            COUNT(*) as transactions
        FROM transactions
        WHERE amount IS NOT NULL
        GROUP BY month
        ORDER BY month
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ── Insights Routes ──────────────────────────────────────────────────
@app.get("/api/insights/top-vendors")
def top_vendors(days: int = 90):
    db = get_db()
    rows = db.execute("""
        SELECT vendor, ROUND(SUM(amount), 2) as total, COUNT(*) as visits
        FROM transactions
        WHERE date >= date('now', ? || ' days') AND amount IS NOT NULL
        GROUP BY vendor
        ORDER BY total DESC
        LIMIT 10
    """, (f"-{days}",)).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.get("/api/insights/frequency")
def purchase_frequency():
    db = get_db()
    rows = db.execute("""
        SELECT vendor, COUNT(*) as freq,
               MIN(date) as first_purchase, MAX(date) as last_purchase
        FROM transactions
        GROUP BY vendor
        HAVING COUNT(*) > 1
        ORDER BY freq DESC
        LIMIT 10
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.get("/api/insights/quick")
def quick_insights():
    db = get_db()
    insights = []

    # Unknown amounts
    unknown = db.execute(
        "SELECT COUNT(*) FROM transactions WHERE amount IS NULL"
    ).fetchone()[0]
    total = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    if unknown > 0 and total > 0:
        pct = round(unknown / total * 100)
        insights.append({
            "type": "warning",
            "icon": "⚠",
            "text": f"{pct}% transactions missing amounts ({unknown} of {total})",
        })

    # Repeat vendor patterns
    repeats = db.execute("""
        SELECT vendor, COUNT(*) as freq
        FROM transactions
        WHERE date >= date('now', '-60 days')
        GROUP BY vendor
        HAVING COUNT(*) >= 3
        ORDER BY freq DESC
        LIMIT 3
    """).fetchall()
    for r in repeats:
        insights.append({
            "type": "info",
            "icon": "ℹ",
            "text": f"{r['vendor']} — {r['freq']}× in 60 days. Consider consolidating trips.",
        })

    # Well-tracked categories
    well_tracked = db.execute("""
        SELECT category, ROUND(SUM(amount), 2) as total
        FROM transactions
        WHERE amount IS NOT NULL AND is_verified = 1
        GROUP BY category
        HAVING COUNT(*) >= 3
        ORDER BY total DESC
        LIMIT 2
    """).fetchall()
    for r in well_tracked:
        insights.append({
            "type": "success",
            "icon": "✓",
            "text": f"{r['category'].title()} ${r['total']} — well tracked",
        })

    # Subscription total
    subs = db.execute("""
        SELECT COUNT(DISTINCT vendor) as count, ROUND(SUM(amount), 2) as total
        FROM transactions
        WHERE category = 'subscription' AND amount IS NOT NULL
    """).fetchone()
    if subs and subs["count"] > 0:
        insights.append({
            "type": "tip",
            "icon": "💡",
            "text": f"{subs['count']} subscriptions totaling ${subs['total']} — review for savings",
        })

    db.close()
    return insights


# ── Shopping List Routes ─────────────────────────────────────────────
@app.get("/api/shopping-list")
def list_shopping_items(list_type: Optional[str] = None):
    db = get_db()
    if list_type:
        rows = db.execute(
            "SELECT * FROM shopping_lists WHERE list_type = ? ORDER BY store, created_at",
            (list_type,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM shopping_lists ORDER BY list_type, store, created_at"
        ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.post("/api/shopping-list")
def add_shopping_item(item: ShoppingItemCreate):
    db = get_db()
    cursor = db.execute(
        """INSERT INTO shopping_lists (item, store, frequency, est_price, list_type)
           VALUES (?, ?, ?, ?, ?)""",
        (item.item, item.store, item.frequency, item.est_price, item.list_type),
    )
    db.commit()
    new_id = cursor.lastrowid
    row = db.execute("SELECT * FROM shopping_lists WHERE id = ?", (new_id,)).fetchone()
    db.close()
    return dict(row)


@app.put("/api/shopping-list/{item_id}")
def update_shopping_item(item_id: int, item: ShoppingItemUpdate):
    db = get_db()
    existing = db.execute("SELECT * FROM shopping_lists WHERE id = ?", (item_id,)).fetchone()
    if not existing:
        db.close()
        raise HTTPException(status_code=404, detail="Shopping item not found")

    updates = {}
    if item.item is not None:
        updates["item"] = item.item
    if item.store is not None:
        updates["store"] = item.store
    if item.frequency is not None:
        updates["frequency"] = item.frequency
    if item.est_price is not None:
        updates["est_price"] = item.est_price
    if item.is_done is not None:
        updates["is_done"] = item.is_done

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(
            f"UPDATE shopping_lists SET {set_clause} WHERE id = ?",
            list(updates.values()) + [item_id],
        )
        db.commit()

    row = db.execute("SELECT * FROM shopping_lists WHERE id = ?", (item_id,)).fetchone()
    db.close()
    return dict(row)


@app.delete("/api/shopping-list/{item_id}")
def delete_shopping_item(item_id: int):
    db = get_db()
    existing = db.execute("SELECT * FROM shopping_lists WHERE id = ?", (item_id,)).fetchone()
    if not existing:
        db.close()
        raise HTTPException(status_code=404, detail="Shopping item not found")
    db.execute("DELETE FROM shopping_lists WHERE id = ?", (item_id,))
    db.commit()
    db.close()
    return {"deleted": True, "id": item_id}


# ── Import Routes ────────────────────────────────────────────────────
@app.post("/api/import/pdf")
async def import_pdf(file: UploadFile = File(...)):
    """Upload and parse a single PDF invoice."""
    from parsers.pdf_parser import extract_text_from_pdf
    from ai.extractor import parse_invoice_text

    # Save uploaded file temporarily
    data_dir = os.path.join(os.path.dirname(__file__), "data", "invoices")
    os.makedirs(data_dir, exist_ok=True)
    filepath = os.path.join(data_dir, file.filename)

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    # Extract text
    text = extract_text_from_pdf(filepath)
    if not text.strip():
        return {"error": "Could not extract text from PDF", "file": file.filename}

    # Check if already processed
    db = get_db()
    existing = db.execute(
        "SELECT id FROM transactions WHERE file_name = ?", (file.filename,)
    ).fetchone()
    if existing:
        db.close()
        return {"skipped": True, "file": file.filename, "reason": "Already processed"}

    # Parse with AI
    try:
        parsed = await parse_invoice_text(text, file.filename)
        category = parsed.get("category", "other")
        cat, store = categorize_vendor(parsed.get("vendor", "Unknown"))
        if category == "other":
            category = cat

        db.execute(
            """INSERT INTO transactions (date, vendor, amount, category, source, file_name, raw_text)
               VALUES (?, ?, ?, ?, 'upload', ?, ?)""",
            (
                parsed.get("date"),
                parsed.get("vendor", store),
                parsed.get("amount"),
                category,
                file.filename,
                text[:5000],
            ),
        )
        db.commit()
        db.close()
        return {"success": True, "file": file.filename, "parsed": parsed}
    except Exception as e:
        db.close()
        return {"error": str(e), "file": file.filename}


@app.post("/api/import/csv")
async def import_csv(file: UploadFile = File(...)):
    """Upload and parse a CSV or Excel file (bank statement, Amazon export, etc.)."""
    from parsers.csv_parser import parse_tabular_file

    # Save temporarily
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    filepath = os.path.join(data_dir, f"temp_{file.filename}")

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        transactions = parse_tabular_file(filepath)
        db = get_db()
        inserted = 0
        for tx in transactions:
            cat, store = categorize_vendor(tx.get("vendor", ""))
            db.execute(
                """INSERT INTO transactions (date, vendor, amount, category, source, file_name)
                   VALUES (?, ?, ?, ?, 'upload', ?)""",
                (
                    tx.get("date"),
                    tx.get("vendor", store),
                    tx.get("amount"),
                    tx.get("category", cat),
                    file.filename,
                ),
            )
            inserted += 1
        db.commit()
        db.close()
        # Clean up temp file
        os.remove(filepath)
        return {"success": True, "file": file.filename, "imported": inserted}
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return {"error": str(e), "file": file.filename}


# ── AI Routes ────────────────────────────────────────────────────────
@app.post("/api/ai/analyze")
async def ai_analyze():
    """AI spending coach — sends aggregated summary to AI (Claude or Gemini)."""
    from ai.insights import generate_spending_insights

    db = get_db()
    summary_rows = db.execute("""
        SELECT
            category,
            vendor,
            COUNT(*) as trips,
            ROUND(SUM(amount), 2) as total,
            ROUND(AVG(amount), 2) as avg_order
        FROM transactions
        WHERE date >= date('now', '-90 days')
            AND amount IS NOT NULL
        GROUP BY category, vendor
        ORDER BY total DESC
        LIMIT 20
    """).fetchall()
    db.close()

    if not summary_rows:
        return {"insight": "No spending data found for the last 90 days. Import some transactions first!"}

    summary_text = "\n".join(
        f"{r['vendor']}: ${r['total']} across {r['trips']} trips "
        f"(avg ${r['avg_order']}, category: {r['category']})"
        for r in summary_rows
    )

    try:
        insight = await generate_spending_insights(summary_text)
        return {"insight": insight}
    except Exception as e:
        return {"insight": f"AI analysis unavailable: {str(e)}. Check your GEMINI_API_KEY or ANTHROPIC_API_KEY."}


@app.post("/api/ai/shopping-list")
async def ai_shopping_list():
    """Generate smart shopping list from purchase history."""
    from ai.insights import generate_shopping_suggestions

    db = get_db()
    # Include ALL vendors — no minimum frequency gate so it works with few imports
    freq_rows = db.execute("""
        SELECT vendor, COUNT(*) as freq,
               GROUP_CONCAT(DISTINCT category) as categories
        FROM transactions
        WHERE date >= date('now', '-180 days')
        GROUP BY vendor
        ORDER BY freq DESC
        LIMIT 20
    """).fetchall()

    # Also pull existing line items for richer context
    item_rows = db.execute("""
        SELECT li.product_name, COUNT(*) as times_bought, t.vendor
        FROM line_items li
        JOIN transactions t ON li.transaction_id = t.id
        GROUP BY li.product_name
        ORDER BY times_bought DESC
        LIMIT 30
    """).fetchall()
    db.close()

    # Build context text even if sparse
    if freq_rows:
        freq_text = "\n".join(
            f"{r['vendor']}: {r['freq']}× purchases (categories: {r['categories']})"
            for r in freq_rows
        )
    else:
        freq_text = "No purchase history yet — generate a general household grocery and essentials list."

    if item_rows:
        item_text = "\n".join(
            f"{r['product_name']} (bought {r['times_bought']}× at {r['vendor']})"
            for r in item_rows
        )
        freq_text += f"\n\nActual items purchased:\n{item_text}"

    try:
        items = await generate_shopping_suggestions(freq_text)
        # Save generated items to shopping_lists
        db = get_db()
        saved = 0
        for item in items:
            # Avoid exact duplicates
            exists = db.execute(
                "SELECT id FROM shopping_lists WHERE item = ? AND list_type = ?",
                (item.get("item"), item.get("list_type", "weekly"))
            ).fetchone()
            if not exists:
                db.execute(
                    """INSERT INTO shopping_lists (item, store, frequency, est_price, list_type)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        item.get("item"),
                        item.get("store"),
                        item.get("frequency"),
                        item.get("est_price"),
                        item.get("list_type", "weekly"),
                    ),
                )
                saved += 1
        db.commit()
        db.close()
        return {"items": items, "saved": saved, "message": f"Added {saved} new items to your shopping list."}
    except Exception as e:
        print(f"AI shopping list error: {e}")
        import traceback; traceback.print_exc()
        return {"items": [], "message": f"AI suggestions unavailable: {str(e)}"}


# ── AI Provider Info ─────────────────────────────────────────────────
@app.get("/api/ai/provider")
def ai_provider_info():
    """Return info about which AI provider is configured."""
    from ai.provider import get_provider_info
    return get_provider_info()


# ── Utility Routes ───────────────────────────────────────────────────
@app.get("/api/categories")
def list_categories():
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT category FROM transactions ORDER BY category"
    ).fetchall()
    db.close()
    return [r["category"] for r in rows]


@app.get("/api/sources")
def list_sources():
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT source FROM transactions ORDER BY source"
    ).fetchall()
    db.close()
    return [r["source"] for r in rows]


@app.get("/api/months")
def list_months():
    db = get_db()
    rows = db.execute("""
        SELECT DISTINCT strftime('%Y-%m', date) as month
        FROM transactions
        ORDER BY month DESC
    """).fetchall()
    db.close()
    return [r["month"] for r in rows]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=True)
