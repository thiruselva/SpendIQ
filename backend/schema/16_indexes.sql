-- SpendIQ v2 Schema: Indexes
-- Performance indexes for all three layers

-- Layer 1: Core Data
CREATE INDEX IF NOT EXISTS idx_orders_store_date ON orders(store_id, order_date);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_product_aliases_store ON product_aliases(store_id, store_product_name);
CREATE INDEX IF NOT EXISTS idx_product_aliases_product ON product_aliases(product_id);

-- Layer 2: Intelligence
CREATE INDEX IF NOT EXISTS idx_patterns_product ON purchase_patterns(product_id);
CREATE INDEX IF NOT EXISTS idx_patterns_next_date ON purchase_patterns(next_predicted_date);
CREATE INDEX IF NOT EXISTS idx_patterns_recurring ON purchase_patterns(is_recurring);
CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id, store_id, recorded_date);
CREATE INDEX IF NOT EXISTS idx_price_history_per_unit ON price_history(product_id, price_per_standard_unit);
CREATE INDEX IF NOT EXISTS idx_store_compare_cheapest ON store_price_compare(cheapest_store_id);

-- Layer 3: Smart Output
CREATE INDEX IF NOT EXISTS idx_lists_store_period ON shopping_lists(store_id, period_type, period_start);
CREATE INDEX IF NOT EXISTS idx_list_items_list ON shopping_list_items(list_id);
CREATE INDEX IF NOT EXISTS idx_list_items_product ON shopping_list_items(product_id);
CREATE INDEX IF NOT EXISTS idx_feedback_list ON shopping_feedback(list_id, product_id);
