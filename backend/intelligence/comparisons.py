"""
Store Price Comparison & Savings Tips
Compares price-per-standard-unit across stores for the same product.
Generates actionable savings tips with full unit math.
"""

import json


def compute_store_comparisons(conn):
    """
    Populate store_price_compare table from price_history.
    Only compares products that appear at 2+ stores with valid unit pricing.
    """
    conn.execute("DELETE FROM store_price_compare")

    # Find products with prices at multiple stores
    rows = conn.execute("""
        SELECT
            ph.product_id,
            p.canonical_name,
            p.standard_unit,
            ph.store_id,
            s.name as store_name,
            AVG(ph.raw_price) as avg_raw_price,
            AVG(ph.price_per_standard_unit) as avg_price_per_std_unit,
            COUNT(*) as sample_count,
            -- Get typical package description
            pa.package_size,
            pa.package_unit,
            pa.package_count
        FROM price_history ph
        JOIN products p ON ph.product_id = p.id
        JOIN stores s ON ph.store_id = s.id
        LEFT JOIN product_aliases pa ON pa.product_id = ph.product_id AND pa.store_id = ph.store_id
        WHERE ph.price_per_standard_unit IS NOT NULL
          AND ph.price_per_standard_unit > 0
        GROUP BY ph.product_id, ph.store_id
    """).fetchall()

    # Group by product
    products = {}
    for row in rows:
        pid = row["product_id"]
        if pid not in products:
            products[pid] = {
                "canonical_name": row["canonical_name"],
                "standard_unit": row["standard_unit"],
                "stores": {},
            }
        # Build package description
        pkg_parts = []
        if row["package_count"] and row["package_count"] > 1:
            pkg_parts.append(f"{row['package_count']}x")
        if row["package_size"]:
            pkg_parts.append(f"{row['package_size']}")
        if row["package_unit"]:
            pkg_parts.append(row["package_unit"])
        pkg_desc = " ".join(pkg_parts) if pkg_parts else "unknown"

        products[pid]["stores"][str(row["store_id"])] = {
            "store_name": row["store_name"],
            "avg_raw_price": round(row["avg_raw_price"], 2),
            "package_desc": pkg_desc,
            "avg_price_per_std_unit": round(row["avg_price_per_std_unit"], 4),
            "sample_count": row["sample_count"],
        }

    # Insert comparisons for products at 2+ stores
    count = 0
    for pid, pdata in products.items():
        if len(pdata["stores"]) < 2:
            continue

        store_breakdown = json.dumps(pdata["stores"])

        # Find cheapest and most expensive
        stores_sorted = sorted(
            pdata["stores"].items(),
            key=lambda x: x[1]["avg_price_per_std_unit"]
        )
        cheapest = stores_sorted[0]
        expensive = stores_sorted[-1]

        cheapest_id = int(cheapest[0])
        cheapest_price = cheapest[1]["avg_price_per_std_unit"]
        expensive_id = int(expensive[0])
        expensive_price = expensive[1]["avg_price_per_std_unit"]

        unit_diff = round(expensive_price - cheapest_price, 4)
        diff_pct = round((unit_diff / expensive_price) * 100, 1) if expensive_price > 0 else 0

        # Estimate monthly consumption from purchase_patterns
        monthly_units = _estimate_monthly_units(conn, pid)
        monthly_saving = round(unit_diff * monthly_units, 2) if monthly_units else None

        conn.execute("""
            INSERT OR REPLACE INTO store_price_compare
            (product_id, standard_unit, store_breakdown,
             cheapest_store_id, cheapest_price_per_unit,
             most_expensive_store_id, most_expensive_price_per_unit,
             unit_price_diff, price_diff_pct,
             avg_monthly_std_units, potential_monthly_saving, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            pid, pdata["standard_unit"], store_breakdown,
            cheapest_id, cheapest_price,
            expensive_id, expensive_price,
            unit_diff, diff_pct,
            monthly_units, monthly_saving,
        ))
        count += 1

    conn.commit()
    print(f"  Computed {count} store price comparisons")
    return count


def _estimate_monthly_units(conn, product_id: int) -> float | None:
    """
    Estimate monthly consumption in standard units for a product.
    Uses purchase_patterns avg_standard_units_per_trip and avg_frequency_days.
    """
    row = conn.execute("""
        SELECT
            avg_standard_units_per_trip,
            avg_frequency_days
        FROM purchase_patterns
        WHERE product_id = ?
          AND avg_standard_units_per_trip IS NOT NULL
          AND avg_frequency_days IS NOT NULL
          AND avg_frequency_days > 0
        ORDER BY total_purchases DESC
        LIMIT 1
    """, (product_id,)).fetchone()

    if not row:
        return None

    trips_per_month = 30.0 / row["avg_frequency_days"]
    return round(row["avg_standard_units_per_trip"] * trips_per_month, 2)


def generate_savings_tips(conn, list_id: int, store_id: int):
    """
    Generate savings_tips for a shopping list.
    Reads from store_price_compare and attaches tips to list items.

    Only generates tips when:
    - Price difference > 10%
    - Potential monthly saving > $1.00
    """
    conn.execute("DELETE FROM savings_tips WHERE list_id = ?", (list_id,))

    # Get items on this list
    list_items = conn.execute("""
        SELECT sli.product_id, sli.est_price_per_std_unit, sli.predicted_std_units
        FROM shopping_list_items sli
        WHERE sli.list_id = ?
    """, (list_id,)).fetchall()

    tips_added = 0
    for item in list_items:
        pid = item["product_id"]

        # Check if there's a cheaper option at another store
        compare = conn.execute("""
            SELECT spc.*, p.canonical_name, p.standard_unit
            FROM store_price_compare spc
            JOIN products p ON spc.product_id = p.id
            WHERE spc.product_id = ?
              AND spc.cheapest_store_id != ?
              AND spc.price_diff_pct > 10.0
              AND spc.potential_monthly_saving > 1.0
        """, (pid, store_id)).fetchone()

        if not compare:
            continue

        # Build description with full unit math
        breakdown = json.loads(compare["store_breakdown"])
        current_store_data = breakdown.get(str(store_id), {})
        best_store_data = breakdown.get(str(compare["cheapest_store_id"]), {})

        current_pkg = current_store_data.get("package_desc", "?")
        current_ppu = current_store_data.get("avg_price_per_std_unit", 0)
        best_pkg = best_store_data.get("package_desc", "?")
        best_ppu = best_store_data.get("avg_price_per_std_unit", 0)
        best_raw = best_store_data.get("avg_raw_price", 0)
        current_raw = current_store_data.get("avg_raw_price", 0)
        best_name = best_store_data.get("store_name", "?")
        current_name = current_store_data.get("store_name", "?")
        unit = compare["standard_unit"] or "unit"

        weekly_units = (compare["avg_monthly_std_units"] or 0) / 4.33
        weekly_saving = compare["unit_price_diff"] * weekly_units if weekly_units else 0

        description = (
            f"{compare['canonical_name']}: {best_name} ${best_ppu:.2f}/{unit} "
            f"({best_pkg}/${best_raw:.2f}) vs {current_name} ${current_ppu:.2f}/{unit} "
            f"({current_pkg}/${current_raw:.2f}). "
            f"Buy {weekly_units:.0f} {unit}/week at {best_name} -> save ${weekly_saving:.2f}/week"
        )

        # Get alias for alt store
        alt_alias = conn.execute(
            "SELECT id, package_size, package_unit, package_count FROM product_aliases WHERE product_id = ? AND store_id = ?",
            (pid, compare["cheapest_store_id"])
        ).fetchone()

        alt_pkg_desc = None
        if alt_alias:
            parts = []
            if alt_alias["package_count"] and alt_alias["package_count"] > 1:
                parts.append(f"{alt_alias['package_count']}x")
            if alt_alias["package_size"]:
                parts.append(f"{alt_alias['package_size']}")
            if alt_alias["package_unit"]:
                parts.append(alt_alias["package_unit"])
            alt_pkg_desc = " ".join(parts) if parts else None

        conn.execute("""
            INSERT INTO savings_tips
            (list_id, product_id, tip_type, description,
             price_per_unit_current, price_per_unit_alt,
             std_units_per_period, estimated_saving,
             alt_store_id, alt_product_id, alt_package_desc)
            VALUES (?, ?, 'switch_store', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            list_id, pid, description,
            current_ppu, best_ppu,
            weekly_units, weekly_saving,
            compare["cheapest_store_id"], pid, alt_pkg_desc,
        ))
        tips_added += 1

    conn.commit()
    print(f"  Generated {tips_added} savings tips for list {list_id}")
    return tips_added


def get_top_savings_opportunities(conn, limit: int = 10) -> list[dict]:
    """
    Get the top savings opportunities across all products.
    Returns products where switching stores saves the most money.
    """
    rows = conn.execute("""
        SELECT
            spc.*,
            p.canonical_name,
            p.standard_unit,
            s_cheap.name as cheapest_store_name,
            s_exp.name as most_expensive_store_name
        FROM store_price_compare spc
        JOIN products p ON spc.product_id = p.id
        JOIN stores s_cheap ON spc.cheapest_store_id = s_cheap.id
        JOIN stores s_exp ON spc.most_expensive_store_id = s_exp.id
        WHERE spc.potential_monthly_saving IS NOT NULL
          AND spc.potential_monthly_saving > 0
        ORDER BY spc.potential_monthly_saving DESC
        LIMIT ?
    """, (limit,)).fetchall()

    return [dict(row) for row in rows]
