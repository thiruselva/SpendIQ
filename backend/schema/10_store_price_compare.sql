-- SpendIQ v2 Schema: Layer 2 — Store Price Compare
-- Cross-store comparison using PRICE-PER-STANDARD-UNIT
-- This is the table savings tips read from

CREATE TABLE IF NOT EXISTS store_price_compare (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id                  INTEGER NOT NULL REFERENCES products(id),
    standard_unit               TEXT,               -- 'oz', 'fl_oz', 'each'

    -- Per-store breakdown (JSON for flexibility)
    -- Format: {"store_id": {"avg_raw_price": 2.93, "package_size": "5 oz",
    --          "avg_price_per_std_unit": 0.586, "sample_count": 13}}
    store_breakdown             TEXT NOT NULL,       -- JSON

    -- Winner
    cheapest_store_id           INTEGER REFERENCES stores(id),
    cheapest_price_per_unit     REAL,               -- $0.304/oz (Costco)
    most_expensive_store_id     INTEGER REFERENCES stores(id),
    most_expensive_price_per_unit REAL,             -- $0.586/oz (Walmart)

    -- Savings math (accounts for HOW MUCH you buy)
    unit_price_diff             REAL,               -- $0.282/oz difference
    price_diff_pct              REAL,               -- 48.1% cheaper at Costco
    avg_monthly_std_units       REAL,               -- how many oz/month you consume
    potential_monthly_saving    REAL,               -- $0.282 x monthly_units

    updated_at                  TEXT DEFAULT (datetime('now')),
    UNIQUE(product_id)
);
