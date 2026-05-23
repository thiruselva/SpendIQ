-- SpendIQ v2 Schema: Layer 2 — Price History
-- Tracks BOTH raw and unit-normalized prices over time

CREATE TABLE IF NOT EXISTS price_history (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id              INTEGER NOT NULL REFERENCES products(id),
    store_id                INTEGER NOT NULL REFERENCES stores(id),
    alias_id                INTEGER REFERENCES product_aliases(id),
    recorded_date           TEXT NOT NULL,

    -- Raw price as charged
    raw_price               REAL NOT NULL,         -- $2.93 (Walmart 5oz spinach)
    quantity_purchased      REAL DEFAULT 1,        -- 1 bag, or 3.77 lb

    -- Package context
    package_size            REAL,                  -- 5 oz
    package_unit            TEXT,                  -- 'oz'
    package_count           INTEGER DEFAULT 1,     -- multi-pack qty

    -- THE KEY METRIC: price per standard unit
    total_standard_units    REAL,                  -- 5 oz (Walmart) vs 16 oz (Costco)
    price_per_standard_unit REAL,                  -- $0.586/oz vs $0.304/oz

    was_on_sale             INTEGER DEFAULT 0,
    savings_amount          REAL DEFAULT 0,

    UNIQUE(product_id, store_id, recorded_date)
);
