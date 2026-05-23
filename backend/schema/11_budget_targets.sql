-- SpendIQ v2 Schema: Layer 2 — Budget Targets
-- Budget tracking and goals

CREATE TABLE IF NOT EXISTS budget_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        INTEGER REFERENCES stores(id),
    period_type     TEXT NOT NULL CHECK(period_type IN ('weekly', 'monthly')),
    budget_amount   REAL,
    avg_actual_spend REAL,
    savings_goal    REAL DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now'))
);
