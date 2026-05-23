-- SpendIQ v2 Schema: Layer 1 — Order Items
-- Line items with unit-normalized pricing

CREATE TABLE IF NOT EXISTS order_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id            INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id          INTEGER REFERENCES products(id),
    alias_id            INTEGER REFERENCES product_aliases(id),
    raw_product_name    TEXT NOT NULL,          -- exact text from bill

    -- What was actually purchased
    quantity            REAL NOT NULL DEFAULT 1,-- 1 bag, or 3.77 lb by weight
    unit_price          REAL NOT NULL,         -- price charged
    total_price         REAL,                  -- quantity x unit_price (or line total)

    -- Normalized pricing computed at import time
    -- "How much product did I actually get in standard units?"
    total_standard_units REAL,                 -- qty=1 x 16oz/lb = 16 oz
                                               -- or qty=3.77lb x 16 = 60.32 oz
    price_per_standard_unit REAL,              -- $4.87 / 16 oz = $0.304/oz
                                               -- vs $2.93 / 5 oz = $0.586/oz

    savings_amount      REAL DEFAULT 0,        -- Costco "Save $3.60"
    was_on_sale         INTEGER DEFAULT 0,
    delivery_status     TEXT                    -- 'Shopped', etc.
);
