-- SpendIQ v2 Schema: Layer 1 — Products
-- Canonical product catalog with standard unit info

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name  TEXT NOT NULL,              -- 'Organic Baby Spinach'
    brand           TEXT,                       -- 'Marketside', 'Kirkland'
    category_id     INTEGER REFERENCES categories(id),
    -- These describe the STANDARD form of this product
    standard_unit   TEXT,                      -- 'oz', 'fl_oz', 'each'
    unit_category   TEXT,                      -- 'weight', 'volume', 'count'
    is_staple       INTEGER DEFAULT 0,         -- 1 = auto-learned as essential item
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
);
