-- SpendIQ v2 Schema: Layer 1 — Product Aliases
-- Store-specific product info WITH package size
-- Same product, different sizes at different stores

CREATE TABLE IF NOT EXISTS product_aliases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL REFERENCES products(id),
    store_id            INTEGER NOT NULL REFERENCES stores(id),
    store_product_name  TEXT NOT NULL,          -- exact name from receipt
    store_item_number   TEXT,                  -- Costco Item 96716

    -- Package size as sold at THIS store
    package_size        REAL,                  -- 5 (for "5 oz"), 1 (for "1 lb")
    package_unit        TEXT,                  -- 'oz', 'lb', 'count', 'loads'
    package_count       INTEGER DEFAULT 1,     -- multi-packs: 10-pack soda = 10

    -- Pre-computed: how many standard units in this package?
    -- e.g. 1 lb = 16 oz, so standard_units_per_package = 16
    standard_units_per_package REAL,

    -- Selling method at this store
    sold_by             TEXT DEFAULT 'unit'    -- 'unit' (1 bag), 'weight' (per lb)
        CHECK(sold_by IN ('unit', 'weight')),

    UNIQUE(store_id, store_product_name)
);
