-- SpendIQ v2 Schema: Layer 1 — Stores
-- Retailers you shop at

CREATE TABLE IF NOT EXISTS stores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,       -- 'Costco', 'Walmart'
    store_type      TEXT NOT NULL,              -- 'warehouse', 'grocery', 'online'
    logo_url        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
