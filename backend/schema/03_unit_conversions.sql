-- SpendIQ v2 Schema: Layer 1 — Unit Conversions
-- Standard unit conversion table for apples-to-apples price comparison
-- Converts all weights to oz, all volumes to fl_oz, all counts to 'each'

CREATE TABLE IF NOT EXISTS unit_conversions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_unit       TEXT NOT NULL,              -- 'lb', 'kg', 'gallon', etc.
    to_standard     TEXT NOT NULL,              -- 'oz', 'fl_oz', 'each'
    multiplier      REAL NOT NULL,             -- lb->oz = 16.0
    unit_category   TEXT NOT NULL              -- 'weight', 'volume', 'count'
        CHECK(unit_category IN ('weight', 'volume', 'count')),
    UNIQUE(from_unit)
);
