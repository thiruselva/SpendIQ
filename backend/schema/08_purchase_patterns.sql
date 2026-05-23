-- SpendIQ v2 Schema: Layer 2 — Purchase Patterns
-- Purchase frequency & prediction per product per store

CREATE TABLE IF NOT EXISTS purchase_patterns (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL REFERENCES products(id),
    store_id            INTEGER NOT NULL REFERENCES stores(id),
    total_purchases     INTEGER DEFAULT 0,
    first_purchased     TEXT,
    last_purchased      TEXT,
    avg_frequency_days  REAL,
    median_frequency_days REAL,
    avg_quantity         REAL,                   -- avg purchase qty (in purchase units)
    avg_standard_units_per_trip REAL,           -- avg std units bought per trip
    next_predicted_date TEXT,
    confidence_score    REAL DEFAULT 0,
    is_recurring        INTEGER DEFAULT 0,
    updated_at          TEXT DEFAULT (datetime('now')),
    UNIQUE(product_id, store_id)
);
