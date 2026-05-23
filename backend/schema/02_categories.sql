-- SpendIQ v2 Schema: Layer 1 — Categories
-- Hierarchical categories (Groceries -> Produce -> Vegetables)

CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,              -- 'Groceries', 'Produce', 'Dairy'
    parent_id       INTEGER REFERENCES categories(id),
    store_id        INTEGER REFERENCES stores(id),  -- NULL = universal category
    level           INTEGER DEFAULT 0,         -- 0=root, 1=sub, 2=sub-sub
    UNIQUE(name, parent_id, store_id)
);
