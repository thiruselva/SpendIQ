-- SpendIQ v2 Schema: Layer 3 — Shopping Lists
-- Smart shopping list headers per store per period

CREATE TABLE IF NOT EXISTS shopping_lists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        INTEGER NOT NULL REFERENCES stores(id),
    period_type     TEXT NOT NULL CHECK(period_type IN ('weekly', 'monthly')),
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    status          TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'final', 'shopping', 'completed')),
    estimated_total REAL DEFAULT 0,
    actual_total    REAL,
    created_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT
);
