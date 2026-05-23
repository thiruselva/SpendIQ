-- SpendIQ v2 Schema: Layer 3 — Shopping List Items
-- Individual items with unit context and savings comparison

CREATE TABLE IF NOT EXISTS shopping_list_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id             INTEGER NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
    product_id          INTEGER NOT NULL REFERENCES products(id),
    alias_id            INTEGER REFERENCES product_aliases(id),

    predicted_qty       REAL NOT NULL,         -- how many packages to buy
    predicted_std_units REAL,                  -- total standard units needed
    estimated_price     REAL,                  -- from price_history avg
    est_price_per_std_unit REAL,               -- for comparison display

    reason              TEXT NOT NULL CHECK(reason IN (
                            'frequency', 'staple', 'seasonal',
                            'manual', 'running_low'
                        )),
    priority            INTEGER DEFAULT 2 CHECK(priority IN (1, 2, 3)),
    is_checked          INTEGER DEFAULT 0,
    actual_qty          REAL,
    actual_price        REAL,
    skipped             INTEGER DEFAULT 0,
    notes               TEXT
);
