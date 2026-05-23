import os
import sys
import re
import sqlite3

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, get_unit_conversions, compute_standard_units, compute_price_per_unit
from intelligence.engine import IntelligenceEngine

def parse_package_info(name):
    name_clean = name.lower()

    # 1. Look for pack count
    count_match = re.search(r'\b(\d+)\s*(?:pack|packs|pk|count|ct|bags|loads)\b', name_clean)
    if not count_match:
        count_match = re.search(r'\b(\d+)-(?:count|pack|ct|pk)\b', name_clean)
        
    package_count = int(count_match.group(1)) if count_match else 1
    
    # 2. Look for weight/volume sizes
    size_match = re.search(r'(\d+(?:\.\d+)?)\s*(oz|fl\s*oz|fl\.?\s*oz|fl\s+oz|lb|g|kg|ml|liter|gallon|quart|pint)\b', name_clean)
    
    if size_match:
        package_size = float(size_match.group(1))
        package_unit = size_match.group(2).replace('.', '').replace(' ', '_')
        if package_unit == 'floz':
            package_unit = 'fl_oz'
        return package_size, package_unit, package_count

    # 3. Check for standalone keywords without numbers
    for unit in ['each', 'bunch', 'bag', 'pack']:
        if re.search(r'\b' + unit + r'\b', name_clean):
            return 1.0, unit, package_count
            
    return None, None, package_count

def merge_products(db, target_id, source_id):
    target = db.execute("SELECT id FROM products WHERE id = ?", (target_id,)).fetchone()
    source = db.execute("SELECT id FROM products WHERE id = ?", (source_id,)).fetchone()
    if not target or not source:
        return False
        
    db.execute("UPDATE product_aliases SET product_id = ? WHERE product_id = ?", (target_id, source_id))
    db.execute("UPDATE order_items SET product_id = ? WHERE product_id = ?", (target_id, source_id))
    db.execute("UPDATE price_history SET product_id = ? WHERE product_id = ?", (target_id, source_id))
    db.execute("DELETE FROM purchase_patterns WHERE product_id = ?", (source_id,))
    db.execute("DELETE FROM products WHERE id = ?", (source_id,))
    return True

def enrich():
    db = get_db()
    conversions = get_unit_conversions(db)
    
    # Mappings list (target_walmart_id, source_costco_id)
    mappings = [
        (214, 600), # Sara Lee Buns
        (9, 615),   # Red Onions
        (184, 622), # Gold Potatoes
        (268, 637), # Thai Jasmine Rice
        (6, 655),   # Bananas
        (257, 676), # Sweet Corn
        (581, 683), # Paneer
    ]
    
    # Align target product categories and standard units in products table
    product_specs = {
        6: ('oz', 'weight'),     # Bananas
        9: ('oz', 'weight'),     # Red Onions
        184: ('oz', 'weight'),   # Gold Potatoes
        214: ('oz', 'weight'),   # Sara Lee Buns
        268: ('oz', 'weight'),   # Thai Jasmine Rice
        257: ('each', 'count'),  # Sweet Corn
        581: ('oz', 'weight'),   # Paneer
    }
    
    for pid, (unit, cat) in product_specs.items():
        db.execute("UPDATE products SET standard_unit = ?, unit_category = ? WHERE id = ?", (unit, cat, pid))
        
    # Merge products
    merged_count = 0
    for target_id, source_id in mappings:
        if merge_products(db, target_id, source_id):
            merged_count += 1
    print(f"Merged {merged_count} Costco products into Walmart counterpart products.")
    db.commit()
    
    # Manual overrides for Costco aliases that don't have package details on receipt
    # (alias_name, store_id) -> (size, unit, count, sold_by)
    manual_aliases = {
        ('SARA LEE HB', 1): (32.0, 'oz', 1, 'unit'),
        ('POTATOES', 1): (10.0, 'lb', 1, 'unit'),
        ('THAI JASMINE', 1): (25.0, 'lb', 1, 'unit'),
        ('BANANAS', 1): (3.0, 'lb', 1, 'unit'),
        ('SWEET CORN', 1): (4.0, 'each', 1, 'unit'),
        ('VERKA PANEER', 1): (32.0, 'oz', 1, 'unit'),
    }
    
    for (name, store_id), (size, unit, count, sold_by) in manual_aliases.items():
        std_units = compute_standard_units(size, unit, count, conversions)
        db.execute("""
            UPDATE product_aliases
            SET package_size = ?, package_unit = ?, package_count = ?, 
                standard_units_per_package = ?, sold_by = ?
            WHERE store_product_name = ? AND store_id = ?
        """, (size, unit, count, std_units, sold_by, name, store_id))
    
    # Step 1: Update product_aliases package info for all other aliases
    aliases = db.execute("SELECT id, store_product_name, package_size, package_unit, package_count FROM product_aliases").fetchall()
    
    updated_aliases = 0
    for alias in aliases:
        if alias["package_size"] is not None and alias["package_unit"] is not None:
            continue
            
        pkg_size, pkg_unit, pkg_count = parse_package_info(alias["store_product_name"])
        if pkg_size is not None and pkg_unit is not None:
            std_units = compute_standard_units(pkg_size, pkg_unit, pkg_count, conversions)
            
            db.execute("""
                UPDATE product_aliases
                SET package_size = ?, package_unit = ?, package_count = ?, standard_units_per_package = ?
                WHERE id = ?
            """, (pkg_size, pkg_unit, pkg_count, std_units, alias["id"]))
            updated_aliases += 1
            
    db.commit()
    print(f"Enriched {updated_aliases} product aliases with parsed package sizes and units.")

    # Step 2: Backfill order_items standard units and price per unit
    order_items = db.execute("""
        SELECT oi.id, oi.quantity, oi.total_price, oi.alias_id,
               pa.standard_units_per_package, pa.package_unit, pa.sold_by,
               o.order_date, o.store_id, oi.product_id
        FROM order_items oi
        JOIN product_aliases pa ON oi.alias_id = pa.id
        JOIN orders o ON oi.order_id = o.id
        WHERE oi.price_per_standard_unit IS NULL
    """).fetchall()

    updated_items = 0
    price_history_entries = 0
    
    for item in order_items:
        std_units_per_pkg = item["standard_units_per_package"]
        pkg_unit = item["package_unit"]
        
        if std_units_per_pkg is not None:
            quantity = item["quantity"] or 1
            total_price = item["total_price"] or 0
            
            if item["sold_by"] == "weight" and pkg_unit and pkg_unit in conversions:
                total_std_units = quantity * conversions[pkg_unit]["multiplier"]
            else:
                total_std_units = quantity * std_units_per_pkg
                
            price_per_std = compute_price_per_unit(total_price, total_std_units)
            
            if price_per_std is not None:
                # Update order_items
                db.execute("""
                    UPDATE order_items
                    SET total_standard_units = ?, price_per_standard_unit = ?
                    WHERE id = ?
                """, (total_std_units, price_per_std, item["id"]))
                
                # Insert/replace into price_history
                db.execute("""
                    INSERT OR REPLACE INTO price_history
                    (product_id, store_id, alias_id, recorded_date,
                     raw_price, quantity_purchased,
                     package_size, package_unit, package_count,
                     total_standard_units, price_per_standard_unit,
                     was_on_sale, savings_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["product_id"], item["store_id"], item["alias_id"],
                    item["order_date"], total_price, quantity,
                    std_units_per_pkg, pkg_unit, 1,
                    total_std_units, price_per_std,
                    0, 0
                ))
                
                updated_items += 1
                price_history_entries += 1

    db.commit()
    print(f"Backfilled {updated_items} order items with standard units.")
    print(f"Inserted {price_history_entries} new price history entries.")

    # Step 3: Run the Intelligence Engine refresh
    print("Running intelligence engine refresh...")
    engine = IntelligenceEngine(db)
    res = engine.refresh()
    print(f"Intelligence refresh complete: {res}")
    
    db.close()

if __name__ == "__main__":
    enrich()
