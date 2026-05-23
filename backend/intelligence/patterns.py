"""
Purchase Pattern Computation
Analyzes order_items to detect recurring purchases, frequency, and consumption rate.
Populates the purchase_patterns table (Layer 2).
"""

from datetime import datetime, timedelta


def compute_purchase_patterns(conn):
    """
    Recompute all purchase_patterns from order_items.
    Clears existing patterns and rebuilds from scratch.

    This runs the following logic per (product_id, store_id) pair:
    1. Count total purchases
    2. Compute first/last purchase dates
    3. Compute average frequency (days between purchases)
    4. Compute average quantity and standard units per trip
    5. Predict next purchase date
    6. Assign confidence score based on purchase count
    """
    conn.execute("DELETE FROM purchase_patterns")

    # Aggregate order_items grouped by product + store
    rows = conn.execute("""
        SELECT
            oi.product_id,
            o.store_id,
            COUNT(*) as total_purchases,
            MIN(o.order_date) as first_purchased,
            MAX(o.order_date) as last_purchased,
            AVG(oi.quantity) as avg_quantity,
            AVG(oi.total_standard_units) as avg_standard_units_per_trip,
            GROUP_CONCAT(o.order_date, ',') as all_dates
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE oi.product_id IS NOT NULL
        GROUP BY oi.product_id, o.store_id
    """).fetchall()

    for row in rows:
        product_id = row["product_id"]
        store_id = row["store_id"]
        total = row["total_purchases"]
        first = row["first_purchased"]
        last = row["last_purchased"]
        avg_qty = row["avg_quantity"]
        avg_std = row["avg_standard_units_per_trip"]

        # Compute frequency
        avg_freq = None
        median_freq = None
        next_predicted = None

        if total >= 2 and first and last:
            dates = sorted(row["all_dates"].split(","))
            date_objs = [datetime.strptime(d.strip(), "%Y-%m-%d") for d in dates if d.strip()]

            if len(date_objs) >= 2:
                gaps = []
                for i in range(1, len(date_objs)):
                    gap = (date_objs[i] - date_objs[i-1]).days
                    if gap > 0:  # Skip same-day purchases
                        gaps.append(gap)

                if gaps:
                    avg_freq = sum(gaps) / len(gaps)
                    sorted_gaps = sorted(gaps)
                    mid = len(sorted_gaps) // 2
                    median_freq = sorted_gaps[mid] if len(sorted_gaps) % 2 else (sorted_gaps[mid-1] + sorted_gaps[mid]) / 2

                    # Predict next date
                    last_date = datetime.strptime(last, "%Y-%m-%d")
                    next_predicted = (last_date + timedelta(days=avg_freq)).strftime("%Y-%m-%d")

        # Confidence scoring
        confidence = _compute_confidence(total)
        is_recurring = 1 if confidence >= 0.60 and avg_freq and avg_freq <= 45 else 0

        conn.execute("""
            INSERT OR REPLACE INTO purchase_patterns
            (product_id, store_id, total_purchases, first_purchased, last_purchased,
             avg_frequency_days, median_frequency_days, avg_quantity,
             avg_standard_units_per_trip, next_predicted_date,
             confidence_score, is_recurring, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            product_id, store_id, total, first, last,
            round(avg_freq, 1) if avg_freq else None,
            round(median_freq, 1) if median_freq else None,
            round(avg_qty, 2) if avg_qty else None,
            round(avg_std, 2) if avg_std else None,
            next_predicted,
            round(confidence, 2),
            is_recurring,
        ))

    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM purchase_patterns").fetchone()[0]
    print(f"  Computed {count} purchase patterns")
    return count


def _compute_confidence(total_purchases: int) -> float:
    """
    Confidence score based on number of purchases.
    More data = more confident the pattern is real.

    8+ purchases -> 0.95 (very high confidence)
    5-7 purchases -> 0.80 (high confidence)
    3-4 purchases -> 0.60 (moderate confidence)
    2 purchases   -> 0.35 (low confidence)
    1 purchase    -> 0.15 (minimal confidence)
    """
    if total_purchases >= 8:
        return 0.95
    elif total_purchases >= 5:
        return 0.80
    elif total_purchases >= 3:
        return 0.60
    elif total_purchases == 2:
        return 0.35
    else:
        return 0.15


def get_patterns_for_store(conn, store_id: int, min_confidence: float = 0.30) -> list[dict]:
    """
    Get purchase patterns for a specific store, filtered by confidence.
    Returns list of dicts with product info and pattern data.
    """
    rows = conn.execute("""
        SELECT
            pp.*,
            p.canonical_name,
            p.brand,
            p.standard_unit,
            pa.package_size,
            pa.package_unit,
            pa.package_count,
            pa.standard_units_per_package
        FROM purchase_patterns pp
        JOIN products p ON pp.product_id = p.id
        LEFT JOIN product_aliases pa ON pa.product_id = pp.product_id AND pa.store_id = pp.store_id
        WHERE pp.store_id = ?
          AND pp.confidence_score >= ?
        ORDER BY pp.confidence_score DESC, pp.total_purchases DESC
    """, (store_id, min_confidence)).fetchall()

    return [dict(row) for row in rows]


def get_due_items(conn, store_id: int, days_ahead: int = 7) -> list[dict]:
    """
    Get products predicted to be needed within the next N days for a store.
    Used by shopping list generation.
    """
    from datetime import date
    cutoff = (date.today() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today = date.today().strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT
            pp.*,
            p.canonical_name,
            p.brand,
            p.standard_unit,
            pa.id as alias_id,
            pa.package_size,
            pa.package_unit,
            pa.standard_units_per_package
        FROM purchase_patterns pp
        JOIN products p ON pp.product_id = p.id
        LEFT JOIN product_aliases pa ON pa.product_id = pp.product_id AND pa.store_id = pp.store_id
        WHERE pp.store_id = ?
          AND pp.is_recurring = 1
          AND pp.next_predicted_date <= ?
          AND pp.next_predicted_date >= ?
        ORDER BY pp.next_predicted_date ASC
    """, (store_id, cutoff, today)).fetchall()

    return [dict(row) for row in rows]
