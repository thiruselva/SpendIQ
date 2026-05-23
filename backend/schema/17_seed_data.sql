-- SpendIQ v2 Schema: Seed Data
-- Pre-populated reference data for stores, categories, and unit conversions

-- ── Stores ──
INSERT OR IGNORE INTO stores (name, store_type) VALUES
    ('Costco', 'warehouse'),
    ('Walmart', 'grocery');

-- ── Root categories (store-specific) ──
INSERT OR IGNORE INTO categories (name, store_id, level) VALUES
    ('Groceries',  1, 0),    -- Costco Groceries (Same-Day delivery)
    ('Online',     1, 0),    -- Costco Online orders
    ('Warehouse',  1, 0),    -- Costco In-store warehouse
    ('Grocery',    2, 0),    -- Walmart Grocery
    ('General',    2, 0);    -- Walmart General Merchandise

-- ── Sub-categories (universal) ──
INSERT OR IGNORE INTO categories (name, parent_id, store_id, level) VALUES
    ('Produce',     1, NULL, 1),
    ('Dairy',       1, NULL, 1),
    ('Snacks',      1, NULL, 1),
    ('Bakery',      1, NULL, 1),
    ('Household',   1, NULL, 1),
    ('Frozen',      1, NULL, 1);

-- ── Unit Conversions ──
-- Weight conversions -> standard: oz
INSERT OR IGNORE INTO unit_conversions (from_unit, to_standard, multiplier, unit_category) VALUES
    ('oz',      'oz',    1.0,     'weight'),
    ('lb',      'oz',    16.0,    'weight'),
    ('kg',      'oz',    35.274,  'weight'),
    ('g',       'oz',    0.03527, 'weight');

-- Volume conversions -> standard: fl_oz
INSERT OR IGNORE INTO unit_conversions (from_unit, to_standard, multiplier, unit_category) VALUES
    ('fl_oz',   'fl_oz', 1.0,     'volume'),
    ('gallon',  'fl_oz', 128.0,   'volume'),
    ('half_gallon', 'fl_oz', 64.0, 'volume'),
    ('quart',   'fl_oz', 32.0,    'volume'),
    ('pint',    'fl_oz', 16.0,    'volume'),
    ('liter',   'fl_oz', 33.814,  'volume'),
    ('ml',      'fl_oz', 0.03381, 'volume');

-- Count conversions -> standard: each
INSERT OR IGNORE INTO unit_conversions (from_unit, to_standard, multiplier, unit_category) VALUES
    ('each',    'each',  1.0,     'count'),
    ('pack',    'each',  1.0,     'count'),
    ('count',   'each',  1.0,     'count'),
    ('bunch',   'each',  1.0,     'count'),
    ('bag',     'each',  1.0,     'count'),
    ('loads',   'each',  1.0,     'count'),    -- for detergent etc.
    ('ct',      'each',  1.0,     'count');    -- "14 ct" chicken skewers
