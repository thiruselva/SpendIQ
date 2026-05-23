-- SpendIQ v2 Schema: Layer 1 — Orders
-- Order header (one per receipt/bill)

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        INTEGER NOT NULL REFERENCES stores(id),
    category_id     INTEGER REFERENCES categories(id),  -- Costco subcategory
    order_number    TEXT NOT NULL,              -- '19169187152450000'
    order_date      TEXT NOT NULL,              -- ISO format: '2025-08-20'
    payment_method  TEXT,                      -- 'Discover ending in 9822'
    subtotal_before_savings REAL DEFAULT 0,
    savings         REAL DEFAULT 0,
    subtotal        REAL DEFAULT 0,
    delivery_charges REAL DEFAULT 0,
    bag_fee         REAL DEFAULT 0,
    tax             REAL DEFAULT 0,
    tip             REAL DEFAULT 0,
    order_total     REAL DEFAULT 0,
    source_file     TEXT,                      -- original filename for traceability
    imported_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(store_id, order_number)
);
