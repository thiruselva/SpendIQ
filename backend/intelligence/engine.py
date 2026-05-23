"""
Intelligence Engine — Orchestrates pattern computation, price comparison,
and shopping list generation.
"""

from datetime import date, timedelta
from .patterns import compute_purchase_patterns, get_due_items, get_patterns_for_store
from .comparisons import compute_store_comparisons, generate_savings_tips, get_top_savings_opportunities


class IntelligenceEngine:
    """
    Main entry point for all intelligence operations.
    Call refresh() after importing new orders to recompute everything.
    """

    def __init__(self, conn):
        self.conn = conn

    def refresh(self):
        """
        Recompute all intelligence data.
        Call after importing new orders.
        """
        print("[Intelligence] Refreshing patterns...")
        pattern_count = compute_purchase_patterns(self.conn)

        print("[Intelligence] Refreshing store comparisons...")
        compare_count = compute_store_comparisons(self.conn)

        print(f"[Intelligence] Refresh complete: {pattern_count} patterns, {compare_count} comparisons")
        return {"patterns": pattern_count, "comparisons": compare_count}

    def generate_shopping_list(self, store_id: int, period_type: str = "weekly") -> dict:
        """
        Generate a smart shopping list for a store.

        Returns:
            { 'list_id': int, 'items': [...], 'tips': [...], 'estimated_total': float }
        """
        today = date.today()
        if period_type == "weekly":
            period_start = today.strftime("%Y-%m-%d")
            period_end = (today + timedelta(days=7)).strftime("%Y-%m-%d")
            days_ahead = 7
        else:
            period_start = today.strftime("%Y-%m-%d")
            period_end = (today + timedelta(days=30)).strftime("%Y-%m-%d")
            days_ahead = 30

        # Step 1: Get due items
        due_items = get_due_items(self.conn, store_id, days_ahead=days_ahead)

        # Step 2: Get staples that haven't been bought recently
        staples = self._get_stale_staples(store_id, days_ahead)

        # Step 3: Create the list
        cursor = self.conn.execute("""
            INSERT INTO shopping_lists (store_id, period_type, period_start, period_end, status)
            VALUES (?, ?, ?, ?, 'draft')
        """, (store_id, period_type, period_start, period_end))
        list_id = cursor.lastrowid

        estimated_total = 0.0
        items_added = []

        # Add due items
        for item in due_items:
            est_price = self._estimate_price(item["product_id"], store_id)
            est_ppu = self._estimate_price_per_unit(item["product_id"], store_id)

            predicted_qty = max(1.0, round(item.get("avg_quantity") or 1.0))
            predicted_std = item.get("avg_standard_units_per_trip")

            self.conn.execute("""
                INSERT INTO shopping_list_items
                (list_id, product_id, alias_id, predicted_qty, predicted_std_units,
                 estimated_price, est_price_per_std_unit, reason, priority)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'frequency', ?)
            """, (
                list_id, item["product_id"], item.get("alias_id"),
                predicted_qty, predicted_std, est_price, est_ppu,
                1 if item.get("confidence_score", 0) >= 0.80 else 2,
            ))

            if est_price:
                estimated_total += est_price * predicted_qty
            items_added.append(item["product_id"])

        # Add staples not already in list
        for staple in staples:
            if staple["product_id"] in items_added:
                continue
            est_price = self._estimate_price(staple["product_id"], store_id)
            est_ppu = self._estimate_price_per_unit(staple["product_id"], store_id)

            self.conn.execute("""
                INSERT INTO shopping_list_items
                (list_id, product_id, alias_id, predicted_qty, predicted_std_units,
                 estimated_price, est_price_per_std_unit, reason, priority)
                VALUES (?, ?, ?, 1, ?, ?, ?, 'staple', 2)
            """, (
                list_id, staple["product_id"], staple.get("alias_id"),
                staple.get("avg_standard_units_per_trip"), est_price, est_ppu,
            ))

            if est_price:
                estimated_total += est_price
            items_added.append(staple["product_id"])

        # Update estimated total
        self.conn.execute(
            "UPDATE shopping_lists SET estimated_total = ? WHERE id = ?",
            (round(estimated_total, 2), list_id)
        )

        # Step 4: Generate savings tips
        generate_savings_tips(self.conn, list_id, store_id)

        self.conn.commit()

        # Step 5: Return complete list
        return self._get_list_detail(list_id)

    def _estimate_price(self, product_id: int, store_id: int) -> float | None:
        """Get the average recent price for a product at a store."""
        row = self.conn.execute("""
            SELECT AVG(raw_price) as avg_price
            FROM price_history
            WHERE product_id = ? AND store_id = ?
            ORDER BY recorded_date DESC
            LIMIT 5
        """, (product_id, store_id)).fetchone()
        return round(row["avg_price"], 2) if row and row["avg_price"] else None

    def _estimate_price_per_unit(self, product_id: int, store_id: int) -> float | None:
        """Get the average recent price per standard unit."""
        row = self.conn.execute("""
            SELECT AVG(price_per_standard_unit) as avg_ppu
            FROM price_history
            WHERE product_id = ? AND store_id = ?
              AND price_per_standard_unit IS NOT NULL
            ORDER BY recorded_date DESC
            LIMIT 5
        """, (product_id, store_id)).fetchone()
        return round(row["avg_ppu"], 4) if row and row["avg_ppu"] else None

    def _get_stale_staples(self, store_id: int, days_threshold: int) -> list[dict]:
        """Get staple products that haven't been purchased recently."""
        cutoff = (date.today() - timedelta(days=days_threshold * 2)).strftime("%Y-%m-%d")
        rows = self.conn.execute("""
            SELECT
                pp.product_id,
                pp.avg_standard_units_per_trip,
                pa.id as alias_id
            FROM purchase_patterns pp
            JOIN products p ON pp.product_id = p.id
            LEFT JOIN product_aliases pa ON pa.product_id = pp.product_id AND pa.store_id = pp.store_id
            WHERE pp.store_id = ?
              AND p.is_staple = 1
              AND pp.last_purchased < ?
        """, (store_id, cutoff)).fetchall()
        return [dict(row) for row in rows]

    def _get_list_detail(self, list_id: int) -> dict:
        """Get complete list with items and tips."""
        lst = dict(self.conn.execute(
            "SELECT * FROM shopping_lists WHERE id = ?", (list_id,)
        ).fetchone())

        items = [dict(row) for row in self.conn.execute("""
            SELECT sli.*, p.canonical_name, p.brand, p.standard_unit,
                   pa.package_size, pa.package_unit, pa.package_count
            FROM shopping_list_items sli
            JOIN products p ON sli.product_id = p.id
            LEFT JOIN product_aliases pa ON sli.alias_id = pa.id
            WHERE sli.list_id = ?
            ORDER BY sli.priority ASC, p.canonical_name ASC
        """, (list_id,)).fetchall()]

        tips = [dict(row) for row in self.conn.execute("""
            SELECT st.*, p.canonical_name, s.name as alt_store_name
            FROM savings_tips st
            JOIN products p ON st.product_id = p.id
            LEFT JOIN stores s ON st.alt_store_id = s.id
            WHERE st.list_id = ?
            ORDER BY st.estimated_saving DESC
        """, (list_id,)).fetchall()]

        return {
            "list": lst,
            "items": items,
            "tips": tips,
            "estimated_total": lst.get("estimated_total", 0),
        }

    def get_savings_summary(self) -> dict:
        """
        Get overall savings summary for dashboard KPI.
        Returns total potential monthly savings and top opportunities.
        """
        row = self.conn.execute("""
            SELECT
                COUNT(*) as products_compared,
                SUM(potential_monthly_saving) as total_monthly_savings,
                AVG(price_diff_pct) as avg_price_diff_pct
            FROM store_price_compare
            WHERE potential_monthly_saving > 0
        """).fetchone()

        top_opportunities = get_top_savings_opportunities(self.conn, limit=5)

        return {
            "products_compared": row["products_compared"] if row and row["products_compared"] else 0,
            "total_monthly_savings": round(row["total_monthly_savings"], 2) if row and row["total_monthly_savings"] else 0,
            "avg_price_diff_pct": round(row["avg_price_diff_pct"], 1) if row and row["avg_price_diff_pct"] else 0,
            "top_opportunities": top_opportunities,
        }
