# CLAUDE_V2.md — SpendIQ v2 Implementation Guide

> **Purpose**: Self-contained Claude Code integration guide for migrating SpendIQ from v1 (flat schema) to v2 (normalized 3-layer schema with unit-normalized pricing).
> **Tech Stack**: React 18 + Vite 5 + Tailwind 3 + shadcn/ui | FastAPI + SQLite3 + AI (Gemini / Claude)
> **Database**: v2 schema lives in `backend/schema/*.sql` (files 00-17, already created)

---

## 1. Project Overview & Vision

### What SpendIQ Does
Local-first personal spending intelligence for families. Import grocery bills from Costco and Walmart, track spending, get AI-powered insights, and generate smart shopping lists.

### The v2 Breakthrough: Unit-Normalized Price Comparison

**The core insight**: raw price comparison is meaningless for groceries. You MUST compare price-per-standard-unit ($/oz, $/fl_oz) to find real savings.

#### Example 1: Spinach
| Store | Product | Package | Raw Price | $/oz |
|-------|---------|---------|-----------|------|
| Costco | Organic Baby Spinach | 1 lb (16 oz) | $4.87 | **$0.304/oz** |
| Walmart | Marketside Baby Spinach | 5 oz | $2.93 | $0.586/oz |

Costco is **48% cheaper per oz** despite costing more per package. At ~16 oz/week consumption, that saves **$4.51/week**.

#### Example 2: Milk
| Store | Product | Package | Raw Price | $/fl_oz |
|-------|---------|---------|-----------|---------|
| Costco | Kirkland Whole Milk | 3 x half-gallon (192 fl_oz) | $14.74 | **$0.0768/fl_oz** |
| Walmart | Great Value Whole Milk | 59 fl_oz | $5.36 | $0.0908/fl_oz |

Costco is **15.4% cheaper per fl_oz**. The `package_count = 3` and `package_unit = half_gallon` together yield 192 fl_oz total.

### v2 Architecture Layers

```
Layer 1: CORE DATA         stores, categories, products, product_aliases,
                           unit_conversions, orders, order_items
                           --- raw imported data with unit normalization ---

Layer 2: INTELLIGENCE      purchase_patterns, price_history,
                           store_price_compare, budget_targets
                           --- computed from Layer 1, drives decisions ---

Layer 3: SMART OUTPUT      shopping_lists, shopping_list_items,
                           savings_tips, shopping_feedback
                           --- user-facing, generated from Layer 2 ---
```

---

## 2. V2 Schema Reference

All schema files are at `backend/schema/` and numbered 00-17. They must be executed in order.

### 2.1 Pragmas — `00_pragmas.sql`
```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
```

### 2.2 Layer 1: Core Data (Tables 01-07)

#### `stores` — `01_stores.sql`
Retailers you shop at.
| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT UNIQUE | 'Costco', 'Walmart' |
| `store_type` | TEXT | 'warehouse', 'grocery', 'online' |
| `logo_url` | TEXT | Optional store logo |
| `created_at` | TEXT | ISO timestamp |

#### `categories` — `02_categories.sql`
Hierarchical categories. Store-specific at level 0, universal sub-categories below.
| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT | 'Groceries', 'Produce', 'Dairy' |
| `parent_id` | INTEGER FK | Self-referencing for hierarchy |
| `store_id` | INTEGER FK | NULL = universal category |
| `level` | INTEGER | 0=root, 1=sub, 2=sub-sub |

Unique constraint: `(name, parent_id, store_id)`.

#### `unit_conversions` — `03_unit_conversions.sql`
The foundation of price comparison. Converts all weights to `oz`, all volumes to `fl_oz`, all counts to `each`.
| Column | Type | Purpose |
|--------|------|---------|
| `from_unit` | TEXT UNIQUE | 'lb', 'kg', 'gallon', 'ml', etc. |
| `to_standard` | TEXT | Always 'oz', 'fl_oz', or 'each' |
| `multiplier` | REAL | lb->oz = 16.0, gallon->fl_oz = 128.0 |
| `unit_category` | TEXT | 'weight', 'volume', or 'count' |

**Key conversions seeded in `17_seed_data.sql`:**
- Weight: oz(1), lb(16), kg(35.274), g(0.03527)
- Volume: fl_oz(1), gallon(128), half_gallon(64), quart(32), pint(16), liter(33.814), ml(0.03381)
- Count: each(1), pack(1), count(1), bunch(1), bag(1), loads(1), ct(1)

**How `standard_units_per_package` is computed:**
```python
def compute_standard_units(package_size, package_unit, package_count, unit_conversions):
    """
    Compute total standard units in a package.

    Examples:
      - Spinach 1 lb, count=1:   1 * 16.0 * 1 = 16.0 oz
      - Spinach 5 oz, count=1:   5 * 1.0 * 1 = 5.0 oz
      - Milk 3x half_gallon:     1 * 64.0 * 3 = 192.0 fl_oz
      - Soda 12-pack cans:       12 * 1.0 * 12 = 144.0 fl_oz (if package_unit=fl_oz, size=12, count=12)
    """
    if not package_size or not package_unit:
        return None
    conv = unit_conversions.get(package_unit)
    if not conv:
        return None
    return package_size * conv['multiplier'] * (package_count or 1)
```

#### `products` — `04_products.sql`
Canonical product catalog. One entry per logical product (e.g., "Organic Baby Spinach").
| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Auto-increment |
| `canonical_name` | TEXT | 'Organic Baby Spinach' |
| `brand` | TEXT | 'Marketside', 'Kirkland' — nullable |
| `category_id` | INTEGER FK | Links to categories |
| `standard_unit` | TEXT | 'oz', 'fl_oz', 'each' |
| `unit_category` | TEXT | 'weight', 'volume', 'count' |
| `is_staple` | INTEGER | 1 = auto-learned essential item |
| `is_active` | INTEGER | 1 = still tracking |

#### `product_aliases` — `05_product_aliases.sql`
Store-specific product info WITH package size. Same product may appear differently at each store.
| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Auto-increment |
| `product_id` | INTEGER FK | Links to products |
| `store_id` | INTEGER FK | Links to stores |
| `store_product_name` | TEXT | Exact name from receipt |
| `store_item_number` | TEXT | Costco Item 96716 |
| `package_size` | REAL | 5 (for "5 oz"), 1 (for "1 lb") |
| `package_unit` | TEXT | 'oz', 'lb', 'count', 'loads' |
| `package_count` | INTEGER | Multi-packs: 3 for "3x half-gallon" |
| `standard_units_per_package` | REAL | Pre-computed: size * multiplier * count |
| `sold_by` | TEXT | 'unit' (1 bag) or 'weight' (per lb) |

**`sold_by` distinction:**
- `'unit'`: You buy 1 package at a fixed price. Quantity on receipt = number of packages.
  - Example: "1 x Organic Baby Spinach, 1 lb — $4.87" → qty=1, unit_price=$4.87
- `'weight'`: Price is per-lb (or per-oz), quantity is the actual weight.
  - Example: "Bananas 3.77 lb @ $0.64/lb — $2.41" → qty=3.77, unit_price=$0.64

**`package_count` for multi-packs:**
- Kirkland Whole Milk = 3 x half-gallon → package_size=1, package_unit='half_gallon', package_count=3
- The standard_units_per_package = 1 * 64.0 * 3 = 192 fl_oz

Unique constraint: `(store_id, store_product_name)`.

#### `orders` — `06_orders.sql`
Order header — one per receipt/bill. Replaces v1 `transactions` table.
| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Auto-increment |
| `store_id` | INTEGER FK | Links to stores |
| `category_id` | INTEGER FK | Costco subcategory (Groceries, Online, etc.) |
| `order_number` | TEXT | '19169187152450000' |
| `order_date` | TEXT | 'YYYY-MM-DD' |
| `payment_method` | TEXT | 'Discover ending in 9822' |
| `subtotal_before_savings` | REAL | Before discounts |
| `savings` | REAL | Total savings on order |
| `subtotal` | REAL | After discounts, before tax |
| `delivery_charges` | REAL | Delivery fee |
| `bag_fee` | REAL | Bag fee |
| `tax` | REAL | Sales tax |
| `tip` | REAL | Delivery tip |
| `order_total` | REAL | Final charge |
| `source_file` | TEXT | Original filename |
| `imported_at` | TEXT | ISO timestamp |

Unique constraint: `(store_id, order_number)`.

#### `order_items` — `07_order_items.sql`
Line items with unit-normalized pricing. Replaces v1 `line_items` table.
| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Auto-increment |
| `order_id` | INTEGER FK | Links to orders (CASCADE delete) |
| `product_id` | INTEGER FK | Links to products |
| `alias_id` | INTEGER FK | Links to product_aliases |
| `raw_product_name` | TEXT | Exact text from bill |
| `quantity` | REAL | 1 bag, or 3.77 lb by weight |
| `unit_price` | REAL | Price charged |
| `total_price` | REAL | quantity x unit_price (or line total) |
| `total_standard_units` | REAL | Computed: how many oz/fl_oz you got |
| `price_per_standard_unit` | REAL | **THE KEY METRIC**: $/oz or $/fl_oz |
| `savings_amount` | REAL | "Save $3.60" |
| `was_on_sale` | INTEGER | 0 or 1 |
| `delivery_status` | TEXT | 'Shopped', 'Delivered', etc. |

**Computing `total_standard_units` and `price_per_standard_unit`:**
```python
def compute_order_item_units(quantity, unit_price, total_price, alias):
    """
    Compute normalized units for an order item.

    For sold_by='unit':
      total_std_units = quantity * alias.standard_units_per_package
      price_per_std = total_price / total_std_units

    For sold_by='weight':
      # quantity IS the weight (e.g., 3.77 lb)
      # Need to convert to standard unit
      conv = get_conversion(alias.package_unit)  # lb -> oz: 16
      total_std_units = quantity * conv.multiplier
      price_per_std = total_price / total_std_units
    """
    if not alias or not alias.standard_units_per_package:
        return None, None

    if alias.sold_by == 'weight':
        conv = get_conversion(alias.package_unit)
        total_std = quantity * conv['multiplier'] if conv else None
    else:
        total_std = quantity * alias.standard_units_per_package

    if total_std and total_std > 0:
        price_per_std = (total_price or unit_price) / total_std
    else:
        price_per_std = None

    return total_std, price_per_std
```

### 2.3 Layer 2: Intelligence (Tables 08-11)

#### `purchase_patterns` — `08_purchase_patterns.sql`
Purchase frequency and prediction per product per store.
| Column | Type | Purpose |
|--------|------|---------|
| `product_id` | INTEGER FK | Which product |
| `store_id` | INTEGER FK | At which store |
| `total_purchases` | INTEGER | How many times bought |
| `first_purchased` | TEXT | First purchase date |
| `last_purchased` | TEXT | Most recent purchase date |
| `avg_frequency_days` | REAL | Average days between purchases |
| `median_frequency_days` | REAL | Median days between purchases |
| `avg_quantity` | REAL | Avg qty per trip (in purchase units) |
| `avg_standard_units_per_trip` | REAL | Avg standard units per trip |
| `next_predicted_date` | TEXT | last_purchased + avg_frequency_days |
| `confidence_score` | REAL | 0.0 to 1.0 based on purchase count |
| `is_recurring` | INTEGER | 1 if confidently recurring |

Unique constraint: `(product_id, store_id)`.

#### `price_history` — `09_price_history.sql`
Tracks both raw and unit-normalized prices over time.
| Column | Type | Purpose |
|--------|------|---------|
| `product_id` | INTEGER FK | Which product |
| `store_id` | INTEGER FK | At which store |
| `alias_id` | INTEGER FK | Which package variant |
| `recorded_date` | TEXT | When this price was observed |
| `raw_price` | REAL | $2.93 as charged |
| `quantity_purchased` | REAL | 1 bag or 3.77 lb |
| `package_size` | REAL | 5 oz |
| `package_unit` | TEXT | 'oz' |
| `package_count` | INTEGER | Multi-pack qty |
| `total_standard_units` | REAL | 5 oz (Walmart) vs 16 oz (Costco) |
| `price_per_standard_unit` | REAL | **$0.586/oz vs $0.304/oz** |
| `was_on_sale` | INTEGER | 0 or 1 |
| `savings_amount` | REAL | Discount amount |

Unique constraint: `(product_id, store_id, recorded_date)`.

#### `store_price_compare` — `10_store_price_compare.sql`
Cross-store comparison using price-per-standard-unit. This is what savings tips read from.
| Column | Type | Purpose |
|--------|------|---------|
| `product_id` | INTEGER FK | Which product (UNIQUE) |
| `standard_unit` | TEXT | 'oz', 'fl_oz', 'each' |
| `store_breakdown` | TEXT (JSON) | Per-store avg prices and sample counts |
| `cheapest_store_id` | INTEGER FK | Best deal store |
| `cheapest_price_per_unit` | REAL | Best $/unit |
| `most_expensive_store_id` | INTEGER FK | Worst deal store |
| `most_expensive_price_per_unit` | REAL | Worst $/unit |
| `unit_price_diff` | REAL | $/unit difference |
| `price_diff_pct` | REAL | Percentage cheaper |
| `avg_monthly_std_units` | REAL | Your monthly consumption |
| `potential_monthly_saving` | REAL | unit_price_diff x monthly_units |

**JSON format for `store_breakdown`:**
```json
{
  "1": {
    "store_name": "Costco",
    "avg_raw_price": 4.87,
    "package_desc": "1 lb",
    "avg_price_per_std_unit": 0.304,
    "sample_count": 8
  },
  "2": {
    "store_name": "Walmart",
    "avg_raw_price": 2.93,
    "package_desc": "5 oz",
    "avg_price_per_std_unit": 0.586,
    "sample_count": 13
  }
}
```

#### `budget_targets` — `11_budget_targets.sql`
Budget tracking and goals per store per period.
| Column | Type | Purpose |
|--------|------|---------|
| `store_id` | INTEGER FK | Optional: per-store budget |
| `period_type` | TEXT | 'weekly' or 'monthly' |
| `budget_amount` | REAL | Target spend |
| `avg_actual_spend` | REAL | Computed actual |
| `savings_goal` | REAL | Target savings |

### 2.4 Layer 3: Smart Output (Tables 12-15)

#### `shopping_lists` — `12_shopping_lists.sql`
Smart shopping list headers. Per store, per period. Replaces v1 flat `shopping_lists`.
| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Auto-increment |
| `store_id` | INTEGER FK | Which store |
| `period_type` | TEXT | 'weekly' or 'monthly' |
| `period_start` | TEXT | Period start date |
| `period_end` | TEXT | Period end date |
| `status` | TEXT | 'draft', 'final', 'shopping', 'completed' |
| `estimated_total` | REAL | Sum of estimated item prices |
| `actual_total` | REAL | Filled after shopping |
| `created_at` | TEXT | ISO timestamp |
| `completed_at` | TEXT | When marked completed |

#### `shopping_list_items` — `13_shopping_list_items.sql`
Individual items with unit context and savings comparison.
| Column | Type | Purpose |
|--------|------|---------|
| `list_id` | INTEGER FK | Parent list (CASCADE delete) |
| `product_id` | INTEGER FK | Which product |
| `alias_id` | INTEGER FK | Which package variant |
| `predicted_qty` | REAL | How many packages to buy |
| `predicted_std_units` | REAL | Total standard units needed |
| `estimated_price` | REAL | From price_history average |
| `est_price_per_std_unit` | REAL | For comparison display |
| `reason` | TEXT | 'frequency', 'staple', 'seasonal', 'manual', 'running_low' |
| `priority` | INTEGER | 1 (must-buy), 2 (should-buy), 3 (nice-to-have) |
| `is_checked` | INTEGER | Checkbox state |
| `actual_qty` | REAL | What was actually bought |
| `actual_price` | REAL | What was actually paid |
| `skipped` | INTEGER | 1 if explicitly skipped |
| `notes` | TEXT | User notes |

#### `savings_tips` — `14_savings_tips.sql`
Unit-normalized savings suggestions attached to shopping lists.
| Column | Type | Purpose |
|--------|------|---------|
| `list_id` | INTEGER FK | Parent list (CASCADE delete) |
| `product_id` | INTEGER FK | Which product |
| `tip_type` | TEXT | 'switch_store', 'buy_bulk', 'wait_sale', 'substitute', 'buy_less' |
| `description` | TEXT | Human-readable with full unit math |
| `price_per_unit_current` | REAL | What you pay now per std unit |
| `price_per_unit_alt` | REAL | What you'd pay at alternative |
| `std_units_per_period` | REAL | Your consumption per period |
| `estimated_saving` | REAL | (diff x units) per period |
| `alt_store_id` | INTEGER FK | Suggested alternative store |
| `alt_product_id` | INTEGER FK | Suggested alternative product |
| `alt_package_desc` | TEXT | "1 lb bag" for context |

**Example description:**
```
Spinach: Costco $0.30/oz (1 lb/$4.87) vs Walmart $0.59/oz (5 oz/$2.93).
Buy 16 oz/week at Costco -> save $4.64/week
```

#### `shopping_feedback` — `15_shopping_feedback.sql`
Feedback loop: tracks actual vs predicted purchases to improve future lists.
| Column | Type | Purpose |
|--------|------|---------|
| `list_id` | INTEGER FK | Which shopping list |
| `product_id` | INTEGER FK | Which product |
| `was_predicted` | INTEGER | 1 if system predicted it |
| `was_purchased` | INTEGER | 1 if actually bought |
| `actual_qty` | REAL | Actual quantity purchased |
| `actual_price` | REAL | Actual price paid |
| `actual_std_units` | REAL | For refining consumption rate |
| `feedback_note` | TEXT | User note |

### 2.5 Indexes — `16_indexes.sql`

```sql
-- Layer 1
idx_orders_store_date       ON orders(store_id, order_date)
idx_orders_date             ON orders(order_date)
idx_order_items_product     ON order_items(product_id)
idx_order_items_order       ON order_items(order_id)
idx_products_category       ON products(category_id)
idx_product_aliases_store   ON product_aliases(store_id, store_product_name)
idx_product_aliases_product ON product_aliases(product_id)

-- Layer 2
idx_patterns_product        ON purchase_patterns(product_id)
idx_patterns_next_date      ON purchase_patterns(next_predicted_date)
idx_patterns_recurring      ON purchase_patterns(is_recurring)
idx_price_history_product   ON price_history(product_id, store_id, recorded_date)
idx_price_history_per_unit  ON price_history(product_id, price_per_standard_unit)
idx_store_compare_cheapest  ON store_price_compare(cheapest_store_id)

-- Layer 3
idx_lists_store_period      ON shopping_lists(store_id, period_type, period_start)
idx_list_items_list         ON shopping_list_items(list_id)
idx_list_items_product      ON shopping_list_items(product_id)
idx_feedback_list           ON shopping_feedback(list_id, product_id)
```

### 2.6 Seed Data — `17_seed_data.sql`

Pre-populates:
- 2 stores: Costco (warehouse), Walmart (grocery)
- 5 root categories: Costco Groceries, Costco Online, Costco Warehouse, Walmart Grocery, Walmart General
- 6 universal sub-categories: Produce, Dairy, Snacks, Bakery, Household, Frozen
- 14 weight conversions (oz, lb, kg, g)
- 7 volume conversions (fl_oz, gallon, half_gallon, quart, pint, liter, ml)
- 7 count conversions (each, pack, count, bunch, bag, loads, ct)

---

## 3. File-by-File Migration Map

### 3.1 REWRITE (complete replacement)

| File | Reason |
|------|--------|
| `backend/database.py` | New schema init from SQL files, v2 DB path, unit computation helpers |
| `backend/ai/extractor.py` → `backend/ai/bill_parser.py` | Unified AI bill parser replacing store-specific parsers |
| `backend/ai/insights.py` | Now driven by intelligence engine data, not raw AI |
| `backend/scripts/import_bills.py` | Inserts into v2 schema (orders + order_items + products + aliases + price_history) |
| `frontend/src/components/ShoppingList.jsx` | Complete redesign with unit prices, savings tips, feedback |

### 3.2 UPDATE (modify existing)

| File | Changes |
|------|---------|
| `backend/main.py` | Add v2 API routes alongside v1 routes |
| `backend/ai/provider.py` | Add "vision" model tier for PDF bill parsing |
| `frontend/src/api/client.js` | Add all v2 endpoint methods |
| `frontend/src/components/Overview.jsx` | Add savings KPI card, price-per-unit trend option |
| `frontend/src/components/Insights.jsx` | Add price comparison section, savings tips |
| `frontend/src/App.jsx` | Add route for PriceCompare component |

### 3.3 KEEP (no changes)

| File | Reason |
|------|--------|
| `backend/parsers/pdf_parser.py` | Still used for raw PDF text extraction (pdfplumber) |
| `backend/parsers/csv_parser.py` | Still used for CSV/Excel column reading |
| `frontend/src/components/ui/*` | All shadcn/ui primitives unchanged |
| `frontend/src/lib/utils.js` | cn() helper unchanged |
| `frontend/src/index.css` | Theme tokens unchanged |
| `frontend/vite.config.js` | Build config unchanged |
| `frontend/tailwind.config.js` | Tailwind config unchanged |
| `electron/*` | Desktop packaging unchanged |

### 3.4 RETIRE (remove after migration)

| File | Replaced By |
|------|-------------|
| `backend/parsers/walmart_parser.py` | `backend/ai/bill_parser.py` |
| `backend/parsers/costco_parser.py` | `backend/ai/bill_parser.py` |
| `backend/demo_data.py` | New v2 demo seeding in `database.py` |

### 3.5 NEW (create)

| File | Purpose |
|------|---------|
| `backend/schema/*.sql` (00-17) | Already created. v2 schema definition files |
| `backend/scripts/migrate_v2.py` | Migration script: re-imports from resources/ into v2 schema |
| `backend/ai/bill_parser.py` | Unified AI-powered bill parser |
| `backend/intelligence/__init__.py` | Package init |
| `backend/intelligence/engine.py` | Orchestrator: pattern computation, price comparison, list generation |
| `backend/intelligence/patterns.py` | SQL queries for purchase_patterns computation |
| `backend/intelligence/comparisons.py` | SQL for store_price_compare and savings_tips |
| `frontend/src/components/PriceCompare.jsx` | Side-by-side cross-store price comparison |

---

## 4. Backend Implementation Guide

### 4a. database.py Rewrite

**File**: `backend/database.py`

Replace the entire file. The new version:
1. Reads and executes schema SQL files from `backend/schema/` in order
2. Points to `data/spendiq_v2.db` (or `spendiq_v2_demo.db`)
3. Provides unit computation helpers

```python
"""
SpendIQ v2 Database Module
SQLite connection manager with schema initialization from SQL files.
Uses separate database files for demo mode vs real data.
"""

import sqlite3
import os
import glob

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schema")


def _get_db_path() -> str:
    """Return the active database path based on DEMO_MODE."""
    demo = os.getenv("DEMO_MODE", "false").lower() == "true"
    filename = "spendiq_v2_demo.db" if demo else "spendiq_v2.db"
    return os.path.join(DB_DIR, filename)


def get_db():
    """Get a database connection with row factory enabled."""
    os.makedirs(DB_DIR, exist_ok=True)
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """
    Create all tables by executing schema SQL files in order.
    Files are named 00_pragmas.sql through 17_seed_data.sql.
    Safe to run multiple times (all CREATE TABLE IF NOT EXISTS, INSERT OR IGNORE).
    """
    conn = get_db()
    cursor = conn.cursor()

    schema_files = sorted(glob.glob(os.path.join(SCHEMA_DIR, "*.sql")))
    for sql_file in schema_files:
        with open(sql_file, "r") as f:
            sql = f.read()
        cursor.executescript(sql)
        print(f"  Applied: {os.path.basename(sql_file)}")

    conn.commit()
    conn.close()
    db_path = _get_db_path()
    mode = "demo" if "demo" in db_path else "production"
    print(f"Database initialized at {db_path} ({mode} mode)")


def get_unit_conversions(conn=None) -> dict:
    """
    Load unit_conversions table into a lookup dict.
    Returns: { 'lb': {'to_standard': 'oz', 'multiplier': 16.0, 'category': 'weight'}, ... }
    """
    close = False
    if conn is None:
        conn = get_db()
        close = True

    rows = conn.execute("SELECT from_unit, to_standard, multiplier, unit_category FROM unit_conversions").fetchall()
    result = {}
    for row in rows:
        result[row["from_unit"]] = {
            "to_standard": row["to_standard"],
            "multiplier": row["multiplier"],
            "category": row["unit_category"],
        }

    if close:
        conn.close()
    return result


def compute_standard_units(package_size: float, package_unit: str,
                           package_count: int, conversions: dict) -> float | None:
    """
    Compute total standard units in a package.

    Args:
        package_size: Size value (e.g., 5 for "5 oz", 1 for "1 lb")
        package_unit: Unit string (e.g., 'oz', 'lb', 'half_gallon')
        package_count: Multi-pack count (e.g., 3 for "3x half-gallon")
        conversions: Dict from get_unit_conversions()

    Returns:
        Total standard units (e.g., 16.0 oz, 192.0 fl_oz) or None.

    Examples:
        compute_standard_units(1, 'lb', 1, conv)          -> 16.0 oz
        compute_standard_units(5, 'oz', 1, conv)          -> 5.0 oz
        compute_standard_units(1, 'half_gallon', 3, conv)  -> 192.0 fl_oz
        compute_standard_units(1, 'gallon', 1, conv)       -> 128.0 fl_oz
    """
    if not package_size or not package_unit:
        return None
    conv = conversions.get(package_unit)
    if not conv:
        return None
    return package_size * conv["multiplier"] * (package_count or 1)


def compute_price_per_unit(total_price: float, total_standard_units: float) -> float | None:
    """
    Compute price per standard unit.

    Args:
        total_price: Total price paid for this line item
        total_standard_units: Total oz/fl_oz/each in this purchase

    Returns:
        Price per standard unit (e.g., $0.304/oz) or None.
    """
    if not total_price or not total_standard_units or total_standard_units <= 0:
        return None
    return round(total_price / total_standard_units, 6)


def find_or_create_store(conn, store_name: str) -> int:
    """Find store by name or create it. Returns store_id."""
    row = conn.execute("SELECT id FROM stores WHERE name = ?", (store_name,)).fetchone()
    if row:
        return row["id"]
    # Infer store type
    store_type = "warehouse" if "costco" in store_name.lower() else "grocery"
    cursor = conn.execute(
        "INSERT INTO stores (name, store_type) VALUES (?, ?)",
        (store_name, store_type)
    )
    conn.commit()
    return cursor.lastrowid


def find_or_create_product(conn, canonical_name: str, brand: str | None,
                           standard_unit: str | None, unit_category: str | None) -> int:
    """Find product by canonical name or create it. Returns product_id."""
    row = conn.execute(
        "SELECT id FROM products WHERE canonical_name = ?",
        (canonical_name,)
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        """INSERT INTO products (canonical_name, brand, standard_unit, unit_category)
           VALUES (?, ?, ?, ?)""",
        (canonical_name, brand, standard_unit, unit_category)
    )
    return cursor.lastrowid


def find_or_create_alias(conn, product_id: int, store_id: int,
                         store_product_name: str, package_info: dict,
                         conversions: dict) -> int:
    """
    Find or create a product_alias. Computes standard_units_per_package.
    Returns alias_id.

    package_info: {
        'package_size': 5.0, 'package_unit': 'oz', 'package_count': 1,
        'store_item_number': '96716', 'sold_by': 'unit'
    }
    """
    row = conn.execute(
        "SELECT id FROM product_aliases WHERE store_id = ? AND store_product_name = ?",
        (store_id, store_product_name)
    ).fetchone()
    if row:
        return row["id"]

    std_units = compute_standard_units(
        package_info.get("package_size"),
        package_info.get("package_unit"),
        package_info.get("package_count", 1),
        conversions,
    )

    cursor = conn.execute(
        """INSERT INTO product_aliases
           (product_id, store_id, store_product_name, store_item_number,
            package_size, package_unit, package_count,
            standard_units_per_package, sold_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            product_id, store_id, store_product_name,
            package_info.get("store_item_number"),
            package_info.get("package_size"),
            package_info.get("package_unit"),
            package_info.get("package_count", 1),
            std_units,
            package_info.get("sold_by", "unit"),
        )
    )
    return cursor.lastrowid


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    init_db()
```

### 4b. AI Bill Parser — `backend/ai/bill_parser.py`

**File**: `backend/ai/bill_parser.py` (NEW)

Single unified parser replacing `walmart_parser.py` and `costco_parser.py`. Uses AI for structured extraction with package size and unit information.

```python
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
# This prompt instructs the AI to extract package size information
# that the v1 parsers ignored completely.

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
      "brand": "brand name if visible, else null",
      "quantity": 1.0,
      "unit_price": 0.00,
      "total_price": 0.00,
      "package_size": 5.0,
      "package_unit": "oz",
      "package_count": 1,
      "sold_by": "unit",
      "savings_amount": 0.00,
      "was_on_sale": false,
      "delivery_status": "Delivered"
    }}
  ]
}}

CRITICAL rules for package extraction:
1. "Organic Baby Spinach, 1 lb" -> package_size: 1.0, package_unit: "lb", package_count: 1
2. "Marketside Baby Spinach, 5 oz" -> package_size: 5.0, package_unit: "oz", package_count: 1
3. "Kirkland Whole Milk, 3 x 1/2 gallon" -> package_size: 1, package_unit: "half_gallon", package_count: 3
4. "Bounty Paper Towels 12-pack" -> package_size: 12, package_unit: "count", package_count: 1
5. "Bananas, 3.77 lb" priced per lb -> sold_by: "weight", quantity: 3.77
6. For items where size is not on receipt, use package_size: null, package_unit: null
7. package_unit values: oz, lb, kg, g, fl_oz, gallon, half_gallon, quart, pint, liter, ml, each, pack, count, ct, loads, bag, bunch
8. sold_by: "unit" = buy 1 package at fixed price, "weight" = priced per lb/oz

Bill content:
{bill_text}"""

# ── Walmart Excel extraction prompt ──
# Walmart Excel files don't have package sizes in the columns,
# but product names often contain size info like "Great Value Whole Milk, 1 gallon"

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
            max_tokens=4000,
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
```

### 4c. Intelligence Engine — `backend/intelligence/`

Create three files in a new `backend/intelligence/` directory.

#### `backend/intelligence/__init__.py`

```python
"""SpendIQ v2 Intelligence Engine — Pattern computation, price comparison, shopping list generation."""
from .engine import IntelligenceEngine
from .patterns import compute_purchase_patterns, get_patterns_for_store
from .comparisons import compute_store_comparisons, generate_savings_tips
```

#### `backend/intelligence/patterns.py`

Computes `purchase_patterns` from `order_items` data.

```python
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
```

#### `backend/intelligence/comparisons.py`

Computes `store_price_compare` and generates `savings_tips`.

```python
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
```

#### `backend/intelligence/engine.py`

Orchestrator that ties patterns, comparisons, and list generation together.

```python
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

        Steps:
        1. Get items predicted to be needed (from purchase_patterns)
        2. Add staple items that may be running low
        3. Create shopping_list + shopping_list_items
        4. Attach savings_tips from store_price_compare
        5. Return the complete list with tips

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
            "products_compared": row["products_compared"] if row else 0,
            "total_monthly_savings": round(row["total_monthly_savings"], 2) if row and row["total_monthly_savings"] else 0,
            "avg_price_diff_pct": round(row["avg_price_diff_pct"], 1) if row and row["avg_price_diff_pct"] else 0,
            "top_opportunities": top_opportunities,
        }
```

### 4d. Updated API Routes — `backend/main.py`

Add v2 routes alongside existing v1 routes. Do NOT remove v1 routes (they still work for existing frontend pages during migration).

Add these v2 route groups to `main.py`:

```python
# ── v2 API Routes ──
# Add these BELOW existing v1 routes in main.py

from intelligence.engine import IntelligenceEngine
from intelligence.patterns import get_patterns_for_store
from intelligence.comparisons import get_top_savings_opportunities

# ── v2: Orders ──

@app.get("/api/v2/orders")
async def v2_list_orders(
    store: str | None = None,
    month: str | None = None,
    limit: int = 50,
    offset: int = 0
):
    """List orders with filters."""
    db = get_db()
    query = """
        SELECT o.*, s.name as store_name
        FROM orders o
        JOIN stores s ON o.store_id = s.id
        WHERE 1=1
    """
    params = []

    if store:
        query += " AND s.name = ?"
        params.append(store)
    if month:
        query += " AND strftime('%Y-%m', o.order_date) = ?"
        params.append(month)

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
    from parsers.pdf_parser import extract_text as pdf_extract_text

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
    from datetime import date, timedelta

    thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
    ninety_days_ago = (date.today() - timedelta(days=90)).isoformat()

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
    Expects: [{ product_id, was_purchased, actual_qty, actual_price }]
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
```

### 4e. Import Bills Script Rewrite — `backend/scripts/import_bills.py`

Rewrite to insert into v2 schema. Uses the existing parsers for text extraction but routes data through v2 tables.

```python
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

    # Insert order
    cursor = db.execute("""
        INSERT INTO orders (store_id, order_number, order_date, payment_method,
                           subtotal_before_savings, savings, subtotal,
                           delivery_charges, tax, tip, order_total, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        store_id, order_number,
        parsed.get("order_date"),
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
                parsed.get("order_date"),
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
    from parsers.pdf_parser import extract_text as pdf_extract_text
    import pandas as pd

    inserted = 0
    skipped = 0
    items = 0

    for filename in sorted(os.listdir(folder)):
        filepath = os.path.join(folder, filename)
        ext = filename.lower().rsplit(".", 1)[-1]

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

        was_inserted = insert_v2_order(db, parsed, conversions, dry_run)
        if was_inserted:
            inserted += 1
            items += len(parsed.get("items", []))
            print(f"  + {filename}: {len(parsed['items'])} items")
        else:
            skipped += 1
            print(f"  = {filename}: duplicate, skipped")

    return inserted, skipped, items


def main():
    parser = argparse.ArgumentParser(description="Import bills into SpendIQ v2")
    parser.add_argument("--source", choices=["walmart", "costco"], help="Import only one source")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    args = parser.parse_args()

    init_db()
    db = get_db()
    conversions = get_unit_conversions(db)

    total_inserted = 0
    total_skipped = 0
    total_items = 0

    sources = []
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
```

---

## 5. Frontend Implementation Guide

### 5a. API Client Updates — `frontend/src/api/client.js`

Add v2 endpoint methods to the existing `api` object. Do NOT remove v1 methods.

```javascript
// Add to the existing api object in client.js:

  // ── v2: Orders ──
  v2GetOrders: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([,v]) => v)).toString();
    return request(`/v2/orders${q ? '?' + q : ''}`);
  },
  v2GetOrderItems: (id) => request(`/v2/orders/${id}/items`),

  // ── v2: Import ──
  v2ImportBill: (file) => {
    const form = new FormData();
    form.append('file', file);
    return fetch(`${BASE}/v2/import/bills`, { method: 'POST', body: form }).then(r => r.json());
  },

  // ── v2: Products ──
  v2GetProducts: (search = '') => request(`/v2/products${search ? '?search=' + encodeURIComponent(search) : ''}`),
  v2GetProductPrices: (id) => request(`/v2/products/${id}/prices`),

  // ── v2: Dashboard ──
  v2GetSummary: () => request('/v2/dashboard/summary'),
  v2GetCategoryBreakdown: () => request('/v2/dashboard/category-breakdown'),
  v2GetMonthlyTrend: () => request('/v2/dashboard/monthly-trend'),

  // ── v2: Insights ──
  v2GetPatterns: (store = '') => request(`/v2/insights/patterns${store ? '?store=' + encodeURIComponent(store) : ''}`),
  v2GetComparisons: () => request('/v2/insights/comparisons'),
  v2GetSavings: () => request('/v2/insights/savings'),

  // ── v2: Shopping Lists ──
  v2GenerateShoppingList: (store = 'Costco', periodType = 'weekly') =>
    request(`/v2/shopping-list/generate?store=${encodeURIComponent(store)}&period_type=${periodType}`, { method: 'POST' }),
  v2GetShoppingList: (listId) => request(`/v2/shopping-list/${listId}`),
  v2SubmitFeedback: (listId, feedback) =>
    request(`/v2/shopping-list/${listId}/feedback`, { method: 'PUT', body: JSON.stringify(feedback) }),
```

### 5b. Overview.jsx Updates

Add a savings KPI card and optional price-per-unit trend chart.

**Changes to make:**
1. Call `api.v2GetSummary()` instead of (or alongside) `api.getSummary()`
2. Add a new KPI card showing potential monthly savings from the response's `savings` field
3. Add a "Price per unit trend" chart option using `api.v2GetProductPrices(productId)`

**New KPI Card snippet** (add alongside existing KPI cards):
```jsx
{/* Savings Potential KPI */}
{summary?.savings && summary.savings.total_monthly_savings > 0 && (
  <Card>
    <CardContent className="pt-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Potential Monthly Savings</p>
        <TrendingDown size={18} className="text-emerald-500" />
      </div>
      <p className="text-2xl font-bold font-mono text-emerald-600">
        ${summary.savings.total_monthly_savings.toFixed(2)}
      </p>
      <p className="text-xs text-muted-foreground mt-1">
        across {summary.savings.products_compared} products compared
      </p>
    </CardContent>
  </Card>
)}
```

### 5c. Insights.jsx Updates

Add a "Price Comparison" section showing cross-store unit-normalized prices.

**Changes to make:**
1. Add a new tab or section: "Price Comparison"
2. Call `api.v2GetComparisons()` to get cross-store data
3. Display each product with visual bars showing $/unit at each store
4. Show savings tips from `api.v2GetSavings()`

**Price Comparison Card snippet:**
```jsx
{/* Price Comparison Section */}
<Card>
  <CardHeader>
    <CardTitle className="flex items-center gap-2">
      <Scale size={18} /> Price Comparison ($/unit)
    </CardTitle>
  </CardHeader>
  <CardContent className="space-y-4">
    {comparisons.map(item => (
      <div key={item.product_id} className="space-y-2 p-3 rounded-lg border">
        <div className="flex items-center justify-between">
          <span className="font-medium text-sm">{item.canonical_name}</span>
          <Badge variant="outline" className="text-emerald-600">
            Save ${item.potential_monthly_saving?.toFixed(2)}/mo
          </Badge>
        </div>
        {/* Per-store bars */}
        {Object.entries(JSON.parse(item.store_breakdown)).map(([storeId, data]) => (
          <div key={storeId} className="flex items-center gap-3">
            <span className="text-xs w-20 text-muted-foreground">{data.store_name}</span>
            <div className="flex-1 bg-muted rounded-full h-4 overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  data.avg_price_per_std_unit === item.cheapest_price_per_unit
                    ? 'bg-emerald-500' : 'bg-orange-400'
                }`}
                style={{ width: `${(data.avg_price_per_std_unit / item.most_expensive_price_per_unit) * 100}%` }}
              />
            </div>
            <span className="text-xs font-mono w-24 text-right">
              ${data.avg_price_per_std_unit.toFixed(3)}/{item.standard_unit}
            </span>
          </div>
        ))}
      </div>
    ))}
  </CardContent>
</Card>
```

### 5d. ShoppingList.jsx REWRITE

Complete redesign. The v2 shopping list is:
- Generated per-store (not global)
- Each item has unit context (package size, $/unit, confidence)
- Savings tips are inline
- Feedback loop: after shopping, mark what was bought/skipped

**Key structural changes:**
- Tabs: **Weekly** | **Monthly** (each per store)
- Store selector: dropdown to pick Costco/Walmart
- Generate button calls `api.v2GenerateShoppingList(store, periodType)`
- Items show: product name, suggested qty, package desc, estimated price, $/unit, confidence badge, priority indicator
- Savings tips appear inline under relevant items
- "Complete Shopping" flow: checkbox items, enter actual qty/price, submit feedback

**Component structure:**
```jsx
export default function ShoppingList() {
  const [store, setStore] = useState('Costco');
  const [periodType, setPeriodType] = useState('weekly');
  const [currentList, setCurrentList] = useState(null);
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const result = await api.v2GenerateShoppingList(store, periodType);
      setCurrentList(result);
    } catch (e) { console.error(e); }
    finally { setGenerating(false); }
  };

  const handleFeedback = async () => {
    // Collect feedback from item checkboxes and actual values
    const feedback = currentList.items.map(item => ({
      product_id: item.product_id,
      was_purchased: item.is_checked ? true : false,
      actual_qty: item.actual_qty || null,
      actual_price: item.actual_price || null,
    }));
    await api.v2SubmitFeedback(currentList.list.id, feedback);
  };

  // Render: store selector, period tabs, generate button,
  // item list with unit info, savings tips, feedback submit
}
```

**Item row layout:**
```
[checkbox] Product Name                    Qty  Package    Est Price  $/unit   [confidence]
           Brand if available              2    1 lb bag   $4.87      $0.30/oz [high]
           Savings tip: Buy at Costco...
```

**Confidence badges:**
| Score | Label | Badge Color |
|-------|-------|-------------|
| >= 0.80 | High | `bg-emerald-100 text-emerald-800` |
| >= 0.50 | Medium | `bg-amber-100 text-amber-800` |
| < 0.50 | Low | `bg-gray-100 text-gray-700` |

### 5e. New Component: PriceCompare.jsx

Side-by-side comparison for a single product across stores.

**File**: `frontend/src/components/PriceCompare.jsx`

**Features:**
- Product search/selection
- Shows all stores where the product is available
- For each store: package size, raw price, $/standard_unit, trend chart
- Visual "winner" indicator (green highlight for cheapest)
- Historical price chart (using Recharts LineChart)
- Monthly cost comparison based on typical consumption

**Route**: Add to `App.jsx` router as `/price-compare` or `/price-compare/:productId`

```jsx
// Component structure
export default function PriceCompare() {
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);

  // Search products -> select one -> load comparison + price history
  // Display side-by-side cards per store
  // Show Recharts LineChart for price history per standard unit
}
```

### 5f. App.jsx Route Addition

Add the PriceCompare route to the router:

```jsx
import PriceCompare from '@/components/PriceCompare';

// In the router:
{ path: '/price-compare', element: <PriceCompare /> }

// In the sidebar nav:
{ icon: Scale, label: 'Price Compare', path: '/price-compare' }
```

---

## 6. AI Provider Updates — `backend/ai/provider.py`

Add a "vision" model tier for bill parsing that handles image/PDF input.

**Changes to `provider.py`:**

```python
# Update the model tier mapping in _call_anthropic:
def _call_anthropic(prompt: str, model_tier: str, max_tokens: int) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    models = {
        "fast": "claude-haiku-4-5",
        "smart": "claude-sonnet-4-20250514",
        "vision": "claude-sonnet-4-20250514",  # Supports image input
    }
    model = models.get(model_tier, "claude-haiku-4-5")

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# Update the model tier mapping in _call_gemini:
def _call_gemini(prompt: str, model_tier: str, max_tokens: int) -> str:
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    models = {
        "fast": "gemini-2.5-flash-lite",
        "smart": "gemini-2.5-flash-lite",
        "vision": "gemini-2.5-flash",  # Full flash for PDF/image parsing
    }
    model = models.get(model_tier, "gemini-2.5-flash-lite")

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=0.3,
        ),
    )
    return response.text.strip()
```

**Updated Model Tiers:**
| Tier | Use Case | Gemini | Claude |
|------|----------|--------|--------|
| `fast` | Quick extraction, enrichment | `gemini-2.5-flash-lite` | `claude-haiku-4-5` |
| `smart` | Spending insights, complex analysis | `gemini-2.5-flash-lite` | `claude-sonnet-4-20250514` |
| `vision` | PDF bill parsing with package extraction | `gemini-2.5-flash` | `claude-sonnet-4-20250514` |

---

## 7. Implementation Phases

### Phase 1: Database & Import (Week 1)
**Goal**: v2 schema active, bills imported with unit-normalized data.

1. **Rewrite `database.py`** (Section 4a)
   - New `init_db()` that reads schema SQL files in order
   - `get_db()` returns connection to `data/spendiq_v2.db`
   - Helper functions: `compute_standard_units`, `compute_price_per_unit`, `find_or_create_*`
   - Test: `python database.py` creates empty v2 DB with all tables

2. **Create `ai/bill_parser.py`** (Section 4b)
   - Unified AI parser with package extraction prompt
   - Walmart product enrichment prompt
   - Fallback regex parser
   - Test: parse a sample Costco PDF and Walmart Excel

3. **Create `intelligence/` module** (Section 4c)
   - `__init__.py`, `engine.py`, `patterns.py`, `comparisons.py`
   - Test: manually insert test data, run `engine.refresh()`, verify patterns

4. **Update `ai/provider.py`** (Section 6)
   - Add "vision" model tier
   - Test: `call_llm(prompt, model_tier="vision")` works

5. **Rewrite `scripts/import_bills.py`** (Section 4e)
   - Import from resources/ into v2 schema with AI extraction
   - Test: `python scripts/import_bills.py --dry-run` then without `--dry-run`
   - Verify unit-normalized prices in DB

### Phase 2: API Layer (Week 1-2)
**Goal**: All v2 API routes working, tested with Postman/curl.

1. **Add v2 routes to `main.py`** (Section 4d)
   - Keep all v1 routes intact
   - Add v2 routes under `/api/v2/` prefix
   - Wire intelligence engine to insight/shopping endpoints

2. **Test all endpoints:**
   - `GET /api/v2/orders` — list orders
   - `GET /api/v2/orders/1/items` — items with $/unit
   - `POST /api/v2/import/bills` — upload a PDF
   - `GET /api/v2/products` — product catalog
   - `GET /api/v2/products/1/prices` — price history
   - `GET /api/v2/dashboard/summary` — KPIs with savings
   - `GET /api/v2/insights/comparisons` — cross-store data
   - `POST /api/v2/shopping-list/generate` — smart list

### Phase 3: Frontend (Week 2-3)
**Goal**: UI updated to use v2 data, new components working.

1. **Update `api/client.js`** (Section 5a)
2. **Update `Overview.jsx`** (Section 5b) — savings KPI card
3. **Update `Insights.jsx`** (Section 5c) — price comparison section
4. **Rewrite `ShoppingList.jsx`** (Section 5d) — full v2 redesign
5. **Create `PriceCompare.jsx`** (Section 5e) — new component
6. **Update `App.jsx`** (Section 5f) — new route

### Phase 4: Polish (Week 3-4)
**Goal**: Feedback loop, demo mode, edge cases.

1. **Feedback loop** — after shopping, mark items bought/skipped, refine patterns
2. **Budget targets UI** — set weekly/monthly budgets per store
3. **Demo mode** — create v2 demo data seeding (similar to current `demo_data.py`)
4. **Price alert notifications** — flag when a product price spikes
5. **Edge cases** — handle items without package info, unknown units, weight-based items

---

## 8. Key SQL Queries Reference

These are the building blocks for the intelligence engine. Each is used in `intelligence/patterns.py` or `intelligence/comparisons.py`.

### Query 1: Compute Purchase Patterns
```sql
-- Groups order_items by product+store, aggregates frequency data
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
GROUP BY oi.product_id, o.store_id;
```

### Query 2: Cross-Store Price Comparison
```sql
-- Averages price_per_standard_unit across all observations per product+store
SELECT
    ph.product_id,
    p.canonical_name,
    p.standard_unit,
    ph.store_id,
    s.name as store_name,
    AVG(ph.raw_price) as avg_raw_price,
    AVG(ph.price_per_standard_unit) as avg_price_per_std_unit,
    COUNT(*) as sample_count,
    pa.package_size,
    pa.package_unit,
    pa.package_count
FROM price_history ph
JOIN products p ON ph.product_id = p.id
JOIN stores s ON ph.store_id = s.id
LEFT JOIN product_aliases pa ON pa.product_id = ph.product_id AND pa.store_id = ph.store_id
WHERE ph.price_per_standard_unit IS NOT NULL
  AND ph.price_per_standard_unit > 0
GROUP BY ph.product_id, ph.store_id;
```

### Query 3: Weekly Shopping List Generation (Due Items)
```sql
-- Products predicted to be needed within the next 7 days
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
  AND pp.next_predicted_date <= date('now', '+7 days')
  AND pp.next_predicted_date >= date('now')
ORDER BY pp.next_predicted_date ASC;
```

### Query 4: Top Savings Opportunities
```sql
-- Products where switching stores saves the most money
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
LIMIT 10;
```

### Query 5: Bulk-Buy Analysis
```sql
-- Compare same product at different package sizes
-- Shows whether buying larger packages saves money per unit
SELECT
    p.canonical_name,
    s.name as store_name,
    pa.package_size,
    pa.package_unit,
    pa.package_count,
    pa.standard_units_per_package,
    AVG(ph.price_per_standard_unit) as avg_ppu,
    AVG(ph.raw_price) as avg_raw_price,
    COUNT(*) as observations
FROM price_history ph
JOIN products p ON ph.product_id = p.id
JOIN stores s ON ph.store_id = s.id
JOIN product_aliases pa ON ph.alias_id = pa.id
WHERE ph.price_per_standard_unit IS NOT NULL
GROUP BY p.id, ph.store_id, pa.id
HAVING COUNT(*) >= 2
ORDER BY p.canonical_name, avg_ppu ASC;
```

### Query 6: Price Volatility Detection
```sql
-- Products with high price variation (potential sale opportunities)
SELECT
    p.canonical_name,
    s.name as store_name,
    p.standard_unit,
    MIN(ph.price_per_standard_unit) as min_ppu,
    MAX(ph.price_per_standard_unit) as max_ppu,
    AVG(ph.price_per_standard_unit) as avg_ppu,
    MAX(ph.price_per_standard_unit) - MIN(ph.price_per_standard_unit) as ppu_range,
    ROUND(
        (MAX(ph.price_per_standard_unit) - MIN(ph.price_per_standard_unit))
        / AVG(ph.price_per_standard_unit) * 100, 1
    ) as volatility_pct,
    COUNT(*) as samples
FROM price_history ph
JOIN products p ON ph.product_id = p.id
JOIN stores s ON ph.store_id = s.id
WHERE ph.price_per_standard_unit IS NOT NULL
GROUP BY ph.product_id, ph.store_id
HAVING COUNT(*) >= 3 AND volatility_pct > 10
ORDER BY volatility_pct DESC;
```

### Query 7: Monthly Unit Cost Trend
```sql
-- Track how $/unit changes over time for a product
SELECT
    strftime('%Y-%m', ph.recorded_date) as month,
    s.name as store_name,
    p.standard_unit,
    AVG(ph.price_per_standard_unit) as avg_ppu,
    SUM(ph.total_standard_units) as total_units_bought,
    SUM(ph.raw_price * ph.quantity_purchased) as total_spent
FROM price_history ph
JOIN products p ON ph.product_id = p.id
JOIN stores s ON ph.store_id = s.id
WHERE ph.product_id = ?
  AND ph.price_per_standard_unit IS NOT NULL
GROUP BY month, ph.store_id
ORDER BY month;
```

### Query 8: Staple Detection
```sql
-- Auto-detect staple items: bought at 3+ stores or 5+ times total
UPDATE products
SET is_staple = 1
WHERE id IN (
    SELECT product_id
    FROM purchase_patterns
    GROUP BY product_id
    HAVING SUM(total_purchases) >= 5
       OR COUNT(DISTINCT store_id) >= 2
);
```

---

## 9. Testing Strategy

### Unit Tests

#### Test: Unit Conversion Math
```python
def test_standard_units_weight():
    conv = {'oz': {'multiplier': 1.0}, 'lb': {'multiplier': 16.0}}
    assert compute_standard_units(1, 'lb', 1, conv) == 16.0
    assert compute_standard_units(5, 'oz', 1, conv) == 5.0

def test_standard_units_volume():
    conv = {'half_gallon': {'multiplier': 64.0}, 'fl_oz': {'multiplier': 1.0}}
    assert compute_standard_units(1, 'half_gallon', 3, conv) == 192.0  # Kirkland Milk

def test_price_per_unit():
    assert compute_price_per_unit(4.87, 16.0) == pytest.approx(0.304375, rel=1e-3)
    assert compute_price_per_unit(2.93, 5.0) == pytest.approx(0.586, rel=1e-3)
    assert compute_price_per_unit(14.74, 192.0) == pytest.approx(0.076771, rel=1e-3)
```

#### Test: Kirkland Milk 3x half-gallon
```python
def test_kirkland_milk():
    """
    Kirkland Whole Milk: 3 x 1/2 gallon at $14.74
    Expected: 192 fl_oz, $0.0768/fl_oz
    """
    conv = {'half_gallon': {'to_standard': 'fl_oz', 'multiplier': 64.0, 'category': 'volume'}}

    std_units = compute_standard_units(1, 'half_gallon', 3, conv)
    assert std_units == 192.0

    ppu = compute_price_per_unit(14.74, std_units)
    assert ppu == pytest.approx(0.0768, rel=1e-2)
```

#### Test: Walmart Spinach 5oz
```python
def test_walmart_spinach():
    """
    Marketside Baby Spinach: 5 oz at $2.93
    Expected: 5 oz, $0.586/oz
    """
    conv = {'oz': {'to_standard': 'oz', 'multiplier': 1.0, 'category': 'weight'}}

    std_units = compute_standard_units(5, 'oz', 1, conv)
    assert std_units == 5.0

    ppu = compute_price_per_unit(2.93, std_units)
    assert ppu == pytest.approx(0.586, rel=1e-3)
```

#### Test: Confidence Scoring
```python
def test_confidence_scoring():
    assert _compute_confidence(8) == 0.95
    assert _compute_confidence(5) == 0.80
    assert _compute_confidence(3) == 0.60
    assert _compute_confidence(2) == 0.35
    assert _compute_confidence(1) == 0.15
```

### Integration Tests

#### Test: Bill Parser -> DB Insertion -> Pattern Computation
```python
async def test_full_import_pipeline():
    """
    1. Parse a Costco PDF with AI
    2. Insert into v2 schema
    3. Compute patterns
    4. Verify price_per_standard_unit in order_items
    5. Verify purchase_patterns has correct frequency
    """
    db = get_db()  # use test DB
    init_db()
    conversions = get_unit_conversions(db)

    # Parse bill
    bill_text = "... sample Costco receipt text ..."
    parsed = await parse_bill(bill_text, source_type="pdf", filename="test.pdf")

    # Insert
    insert_v2_order(db, parsed, conversions)
    db.commit()

    # Verify order_items have normalized pricing
    items = db.execute("SELECT * FROM order_items").fetchall()
    for item in items:
        if item["total_standard_units"]:
            assert item["price_per_standard_unit"] > 0

    # Compute patterns
    engine = IntelligenceEngine(db)
    engine.refresh()

    # Verify patterns
    patterns = db.execute("SELECT * FROM purchase_patterns").fetchall()
    assert len(patterns) > 0

    db.close()
```

#### Test: Cross-Store Comparison Output
```python
def test_cross_store_comparison():
    """
    Insert same product at two stores with different package sizes.
    Verify store_price_compare picks the correct cheapest store.
    """
    # Insert Spinach at Costco (1 lb/$4.87 = $0.304/oz)
    # Insert Spinach at Walmart (5 oz/$2.93 = $0.586/oz)
    # Run compute_store_comparisons()
    # Verify cheapest_store = Costco, price_diff_pct ~ 48%
```

### Manual Test Checklist
- [ ] `python database.py` creates v2 DB with all 15 tables
- [ ] `python scripts/import_bills.py --dry-run` lists all importable files
- [ ] `python scripts/import_bills.py` imports all bills into v2 schema
- [ ] `sqlite3 data/spendiq_v2.db "SELECT COUNT(*) FROM orders"` shows imported orders
- [ ] `sqlite3 data/spendiq_v2.db "SELECT * FROM order_items WHERE price_per_standard_unit IS NOT NULL LIMIT 5"` shows normalized prices
- [ ] `sqlite3 data/spendiq_v2.db "SELECT * FROM purchase_patterns WHERE is_recurring = 1"` shows detected recurring items
- [ ] `sqlite3 data/spendiq_v2.db "SELECT * FROM store_price_compare ORDER BY potential_monthly_saving DESC LIMIT 5"` shows top savings
- [ ] Backend starts: `uvicorn main:app --port 8765 --reload`
- [ ] `curl localhost:8765/api/v2/dashboard/summary` returns KPIs
- [ ] `curl localhost:8765/api/v2/insights/comparisons` returns cross-store data
- [ ] `curl -X POST 'localhost:8765/api/v2/shopping-list/generate?store=Costco'` returns smart list
- [ ] Frontend builds: `npm run dev` and loads at `localhost:5173`
- [ ] Shopping list generate button works and shows items with $/unit
- [ ] Price comparison section shows visual bars

---

## 10. Updated Folder Structure (v2)

```
SpendIQ/
├── CLAUDE.md                    # v1 project guide (keep for reference)
├── CLAUDE_V2.md                 # ← THIS FILE: v2 implementation guide
├── .gitignore
│
├── backend/
│   ├── .env / .env.example
│   ├── requirements.txt
│   ├── main.py                  # FastAPI app — v1 + v2 API routes
│   ├── database.py              # REWRITTEN: v2 schema init + unit helpers
│   ├── demo_data.py             # RETIRE after v2 demo seeding
│   │
│   ├── schema/                  # NEW: SQL schema files (already created)
│   │   ├── 00_pragmas.sql
│   │   ├── 01_stores.sql
│   │   ├── 02_categories.sql
│   │   ├── 03_unit_conversions.sql
│   │   ├── 04_products.sql
│   │   ├── 05_product_aliases.sql
│   │   ├── 06_orders.sql
│   │   ├── 07_order_items.sql
│   │   ├── 08_purchase_patterns.sql
│   │   ├── 09_price_history.sql
│   │   ├── 10_store_price_compare.sql
│   │   ├── 11_budget_targets.sql
│   │   ├── 12_shopping_lists.sql
│   │   ├── 13_shopping_list_items.sql
│   │   ├── 14_savings_tips.sql
│   │   ├── 15_shopping_feedback.sql
│   │   ├── 16_indexes.sql
│   │   └── 17_seed_data.sql
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── provider.py          # UPDATED: +vision tier
│   │   ├── bill_parser.py       # NEW: unified AI bill parser
│   │   ├── extractor.py         # KEEP: v1 fallback
│   │   └── insights.py          # REWRITE: data-driven insights
│   │
│   ├── intelligence/            # NEW: intelligence engine
│   │   ├── __init__.py
│   │   ├── engine.py            # Orchestrator
│   │   ├── patterns.py          # Purchase pattern computation
│   │   └── comparisons.py       # Store price comparison + savings tips
│   │
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py        # KEEP: pdfplumber text extraction
│   │   ├── csv_parser.py        # KEEP: CSV/Excel column reading
│   │   ├── email_parser.py      # KEEP: future
│   │   ├── walmart_parser.py    # RETIRE: replaced by bill_parser.py
│   │   └── costco_parser.py     # RETIRE: replaced by bill_parser.py
│   │
│   ├── scripts/
│   │   ├── import_bills.py      # REWRITE: v2 schema import
│   │   ├── migrate_v2.py        # NEW: migration from v1 data
│   │   ├── extract_invoices.py  # KEEP
│   │   └── parse_invoices.py    # KEEP
│   │
│   ├── resources/               # Unchanged
│   │   ├── walmart/
│   │   └── costco/
│   │
│   └── data/
│       ├── spendiq.db           # v1 real data (keep)
│       ├── spendiq_demo.db      # v1 demo data (keep)
│       ├── spendiq_v2.db        # NEW: v2 real data
│       ├── spendiq_v2_demo.db   # NEW: v2 demo data
│       └── invoices/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── index.css
│       ├── App.jsx              # UPDATED: +PriceCompare route
│       ├── lib/utils.js
│       ├── api/
│       │   └── client.js        # UPDATED: +v2 methods
│       ├── components/
│       │   ├── ui/              # KEEP all
│       │   ├── Overview.jsx     # UPDATED: +savings KPI
│       │   ├── Transactions.jsx # KEEP (reads v1 for now)
│       │   ├── Insights.jsx     # UPDATED: +price comparison
│       │   ├── ShoppingList.jsx # REWRITE: v2 smart list
│       │   ├── PriceCompare.jsx # NEW: cross-store comparison
│       │   └── Import.jsx       # UPDATED: uses v2 import endpoint
│       └── hooks/
│           ├── useTransactions.js
│           └── useInsights.js
│
└── electron/                    # Unchanged
```

---

## 11. Configuration Updates

### .env additions
```bash
# ── Demo Mode ──
DEMO_MODE=false          # true = demo DB, false = real DB
# Note: v2 uses spendiq_v2.db / spendiq_v2_demo.db

# ── AI Provider ──
GEMINI_API_KEY=...       # Google Gemini (preferred)
ANTHROPIC_API_KEY=...    # Anthropic Claude (alternative)
AI_PROVIDER=gemini       # Force specific provider (optional)
```

### requirements.txt additions
No new Python dependencies needed. All existing packages support v2:
- `pdfplumber` for PDF text extraction (used by bill_parser)
- `pandas` + `openpyxl` for Excel reading (used by bill_parser)
- `google-genai` / `anthropic` for AI calls (used by bill_parser)

---

## 12. Migration Path (v1 -> v2)

### Option A: Fresh Import (Recommended)
1. Run `init_db()` to create v2 tables
2. Run `scripts/import_bills.py` to re-import all bills from `resources/` with AI extraction
3. Intelligence engine auto-refreshes after import

### Option B: Data Migration Script
Create `scripts/migrate_v2.py` that:
1. Reads v1 `transactions` + `line_items` from `spendiq.db`
2. Maps vendors to v2 `stores`
3. Creates products + aliases (without package info — AI enrichment needed)
4. Inserts into v2 `orders` + `order_items`
5. Runs intelligence refresh

**Note**: Option A is preferred because the AI bill parser extracts package sizes that the v1 parsers never captured. Option B would leave `package_size`, `package_unit`, and all normalized pricing as NULL.

---

## 13. Privacy & Data Handling (Same as v1)

- All data stays in local SQLite files
- Only **aggregated summaries** sent to AI for insights
- Bill text capped at 6000 chars for AI extraction (up from 3000 in v1)
- No personal financial data leaves the device
- AI bill parsing sends receipt text for structured extraction only
- `invoice/` directory stores uploaded PDFs locally

---

## 14. Troubleshooting

### Common Issues

**"No items extracted from bill"**
- Check AI provider is configured (`GEMINI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`)
- Try the "vision" tier explicitly if PDF parsing fails
- Fall back to regex parser for Costco PDFs (existing pattern works well)

**`package_size` is NULL for imported items**
- The AI prompt did not extract size info from the receipt text
- Check the receipt text quality — some PDFs have garbled text
- Manually update `product_aliases` with correct package info

**`price_per_standard_unit` is NULL**
- Requires both `package_size` and `package_unit` to be set on the alias
- Check `unit_conversions` table has the relevant unit
- For unknown units, add a row to `unit_conversions`

**Intelligence engine shows 0 patterns**
- Ensure `order_items.product_id` is populated (not NULL)
- Run `IntelligenceEngine(conn).refresh()` after importing
- Check that there are at least 2 orders for the same product to detect frequency

**Gemini returns 503**
- High demand — switch `vision` tier to `gemini-2.5-flash` (non-lite) in provider.py
- Or switch to Anthropic: set `AI_PROVIDER=anthropic` in `.env`
