"""
Demo Data — Sample transactions for SpendIQ demo mode.
Controlled by DEMO_MODE=true in .env (defaults to false).

All vendor names and transaction data here are fictional examples
and do not represent real personal spending or location data.

To enable:  Set DEMO_MODE=true in backend/.env
To disable: Remove or set DEMO_MODE=false, then delete data/spendiq.db to start fresh.
"""

import os

def is_demo_mode() -> bool:
    """Check if demo mode is enabled via environment variable."""
    return os.getenv("DEMO_MODE", "false").lower().strip() in ("true", "1", "yes")


# ── Demo Transactions ────────────────────────────────────────────────
# Format: (date, vendor, amount, category, source, file_name, is_verified)
# Note: All vendor names are generic examples, not real business names.
DEMO_TRANSACTIONS = [
    ("2026-05-18", "Wellness Clinic", 30.00, "health", "upload", None, 1),
    ("2026-05-17", "Walmart Supercenter", 87.43, "grocery", "upload", None, 1),
    ("2026-05-16", "Costco Wholesale", 214.56, "grocery", "upload", None, 1),
    ("2026-05-15", "DoorDash - Local Restaurant", None, "food", "upload", None, 0),
    ("2026-05-14", "Amazon.com", 34.99, "shopping", "upload", None, 1),
    ("2026-05-13", "Anthropic Claude Pro", 20.00, "subscription", "upload", None, 1),
    ("2026-05-12", "Apple iCloud+", 2.99, "subscription", "upload", None, 1),
    ("2026-05-11", "Netflix Premium", 22.99, "subscription", "upload", None, 1),
    ("2026-05-10", "CVS Pharmacy", 18.47, "health", "manual", None, 1),
    ("2026-05-09", "Costco Wholesale", 156.23, "grocery", "upload", None, 1),
    ("2026-05-08", "Walmart Supercenter", 62.18, "grocery", "upload", None, 1),
    ("2026-05-07", "DoorDash - Local Restaurant", None, "food", "upload", None, 0),
    ("2026-05-06", "Target", 45.67, "shopping", "manual", None, 1),
    ("2026-05-05", "Wellness Clinic", 30.00, "health", "upload", None, 1),
    ("2026-05-04", "Family Dental Care", 170.00, "dental", "upload", None, 1),
    ("2026-05-03", "Walmart Supercenter", 93.21, "grocery", "upload", None, 1),
    ("2026-05-01", "Costco Wholesale", 189.45, "grocery", "upload", None, 1),
    ("2026-04-29", "DoorDash - Local Restaurant", 28.50, "food", "upload", None, 1),
    ("2026-04-28", "Amazon.com", 67.99, "shopping", "upload", None, 1),
    ("2026-04-27", "Spotify Family", 16.99, "subscription", "upload", None, 1),
    ("2026-04-26", "Walmart Supercenter", 78.34, "grocery", "upload", None, 1),
    ("2026-04-25", "Wellness Clinic", 30.00, "health", "upload", None, 1),
    ("2026-04-24", "Costco Wholesale", 201.33, "grocery", "upload", None, 1),
    ("2026-04-22", "Google One Storage", 2.99, "subscription", "upload", None, 1),
    ("2026-04-20", "Uber Eats - Local Restaurant", 35.20, "food", "upload", None, 1),
    ("2026-04-18", "Walmart Supercenter", 55.12, "grocery", "upload", None, 1),
    ("2026-04-15", "Wellness Clinic", 30.00, "health", "upload", None, 1),
    ("2026-04-12", "Costco Wholesale", 178.90, "grocery", "upload", None, 1),
    ("2026-04-10", "Amazon.com", 22.49, "shopping", "upload", None, 1),
    ("2026-04-08", "DoorDash - Local Restaurant", 24.75, "food", "upload", None, 1),
    ("2026-04-05", "Wellness Clinic", 30.00, "health", "upload", None, 1),
    ("2026-04-03", "Walmart Supercenter", 101.56, "grocery", "upload", None, 1),
    ("2026-04-01", "Family Dental Care", 170.00, "dental", "upload", None, 1),
    ("2026-03-28", "Costco Wholesale", 165.78, "grocery", "upload", None, 1),
    ("2026-03-25", "Walmart Supercenter", 72.90, "grocery", "upload", None, 1),
    ("2026-03-22", "Amazon.com", 149.99, "shopping", "upload", None, 1),
    ("2026-03-20", "Wellness Clinic", 30.00, "health", "upload", None, 1),
    ("2026-03-18", "DoorDash - Local Restaurant", 31.40, "food", "upload", None, 1),
    ("2026-03-15", "Costco Wholesale", 192.10, "grocery", "upload", None, 1),
    ("2026-03-10", "Wellness Clinic", 30.00, "health", "upload", None, 1),
    ("2026-03-05", "Walmart Supercenter", 88.45, "grocery", "upload", None, 1),
    ("2026-03-01", "Apple iCloud+", 2.99, "subscription", "upload", None, 1),
    ("2026-02-25", "Costco Wholesale", 210.55, "grocery", "upload", None, 1),
    ("2026-02-20", "Wellness Clinic", 30.00, "health", "upload", None, 1),
    ("2026-02-15", "Walmart Supercenter", 66.78, "grocery", "upload", None, 1),
    ("2026-02-10", "Netflix Premium", 22.99, "subscription", "upload", None, 1),
]


# ── Demo Shopping List ───────────────────────────────────────────────
# Generic household staples — no personal preferences encoded
DEMO_SHOPPING_ITEMS = [
    ("Whole milk (1 gallon)", "Costco", "Every week", 6.00, "weekly"),
    ("Eggs (18-pack)", "Costco", "Every week", 8.00, "weekly"),
    ("Organic bananas", "Walmart", "Every week", 3.00, "weekly"),
    ("Bread (whole wheat)", "Walmart", "Every week", 4.00, "weekly"),
    ("Rice (10 lb)", "Costco", "Monthly", 12.00, "monthly"),
    ("Paper towels (bulk)", "Costco", "Monthly", 22.00, "monthly"),
    ("Netflix Premium", "Netflix", "Monthly", 22.99, "subscriptions"),
    ("Spotify Family", "Spotify", "Monthly", 16.99, "subscriptions"),
]


def seed_demo_data(db):
    """Insert demo transactions and shopping items if DEMO_MODE is on and DB is empty."""
    if not is_demo_mode():
        return

    count = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    if count > 0:
        return

    # Seed transactions and line items
    for row in DEMO_TRANSACTIONS:
        cursor = db.execute(
            """INSERT INTO transactions (date, vendor, amount, category, source, file_name, is_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            row,
        )
        tx_id = cursor.lastrowid
        vendor = row[1]

        # Add sample line items for grocery stores
        if "Walmart" in vendor:
            items = [
                ("Organic Fresh Salad Mix, 5 oz", 1, 2.66, 2.66, "Shopped"),
                ("Whole Wheat Hamburger Buns, 8 count", 1, 3.52, 3.52, "Shopped"),
            ]
            for item in items:
                db.execute(
                    """INSERT INTO line_items (transaction_id, product_name, quantity, unit_price, total_price, item_status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (tx_id, item[0], item[1], item[2], item[3], item[4])
                )
        elif "Costco" in vendor:
            items = [
                ("Organic Baby Spinach, 1 lb", 1, 4.87, 4.87, "Delivered"),
                ("Ultra Clean Laundry Detergent, 150 loads", 1, 19.93, 19.93, "Delivered"),
            ]
            for item in items:
                db.execute(
                    """INSERT INTO line_items (transaction_id, product_name, quantity, unit_price, total_price, item_status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (tx_id, item[0], item[1], item[2], item[3], item[4])
                )

    # Seed shopping list
    for row in DEMO_SHOPPING_ITEMS:
        db.execute(
            """INSERT INTO shopping_lists (item, store, frequency, est_price, list_type)
               VALUES (?, ?, ?, ?, ?)""",
            row,
        )

    db.commit()
    print(f"✓ Demo mode: Seeded {len(DEMO_TRANSACTIONS)} transactions + {len(DEMO_SHOPPING_ITEMS)} shopping items")
