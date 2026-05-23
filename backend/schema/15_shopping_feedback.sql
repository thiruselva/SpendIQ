-- SpendIQ v2 Schema: Layer 3 — Shopping Feedback
-- Feedback loop: tracks actual vs predicted purchases

CREATE TABLE IF NOT EXISTS shopping_feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id         INTEGER NOT NULL REFERENCES shopping_lists(id),
    product_id      INTEGER NOT NULL REFERENCES products(id),
    was_predicted   INTEGER DEFAULT 1,
    was_purchased   INTEGER DEFAULT 0,
    actual_qty      REAL,
    actual_price    REAL,
    actual_std_units REAL,                     -- for refining consumption rate
    feedback_note   TEXT,
    recorded_at     TEXT DEFAULT (datetime('now'))
);
