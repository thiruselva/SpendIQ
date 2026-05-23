-- SpendIQ v2 Schema: Layer 3 — Savings Tips
-- Unit-normalized savings suggestions per shopping list

CREATE TABLE IF NOT EXISTS savings_tips (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id             INTEGER NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
    product_id          INTEGER NOT NULL REFERENCES products(id),
    tip_type            TEXT NOT NULL CHECK(tip_type IN (
                            'switch_store', 'buy_bulk', 'wait_sale',
                            'substitute', 'buy_less'
                        )),
    -- Description includes full unit math
    -- e.g., "Spinach: Costco $0.30/oz (1 lb/$4.87) vs Walmart $0.59/oz (5 oz/$2.93).
    --        Buy 16 oz/week at Costco -> save $4.64/week"
    description         TEXT NOT NULL,

    -- Savings computed per-unit THEN multiplied by consumption
    price_per_unit_current  REAL,              -- what you pay now per std unit
    price_per_unit_alt      REAL,              -- what you'd pay at alt
    std_units_per_period    REAL,              -- how much you consume per period
    estimated_saving        REAL,              -- (diff x units) per period

    alt_store_id        INTEGER REFERENCES stores(id),
    alt_product_id      INTEGER REFERENCES products(id),
    alt_package_desc    TEXT                   -- "1 lb bag" for context
);
