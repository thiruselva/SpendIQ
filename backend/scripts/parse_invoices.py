"""
Stage 2 — Structured parsing with Claude Haiku.
Reads extracted.json and parses each invoice into structured data.
Inserts into SQLite, skipping already-processed files.
Estimated cost: ~$0.15–$0.50 for 190 invoices.
"""

import os
import sys
import json
import sqlite3
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from anthropic import Anthropic
from database import get_db, init_db, categorize_vendor

EXTRACTED_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "extracted.json")

PROMPT_TEMPLATE = """Extract transaction details from this invoice.
Return ONLY valid JSON, no explanation, no markdown:

{{
  "date": "YYYY-MM-DD",
  "vendor": "store or service name",
  "amount": 0.00,
  "category": "grocery|food|subscription|health|dental|shopping|other",
  "items": ["item1", "item2"]
}}

If any field cannot be determined, use null.

Invoice text:
{text}"""


def main():
    print("=" * 60)
    print("SpendIQ — Stage 2: AI Invoice Parsing (Haiku)")
    print("=" * 60)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n✗ ANTHROPIC_API_KEY not found in .env")
        print("  Create a .env file in the backend/ directory with:")
        print("  ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx")
        return

    if not os.path.exists(EXTRACTED_FILE):
        print(f"\n✗ {EXTRACTED_FILE} not found.")
        print("  Run extract_invoices.py first (Stage 1).")
        return

    with open(EXTRACTED_FILE) as f:
        invoices = json.load(f)

    print(f"Loaded {len(invoices)} invoices from extracted.json")

    # Initialize database
    init_db()
    db = get_db()
    client = Anthropic(api_key=api_key)

    processed = 0
    skipped = 0
    failed = 0
    total_input_tokens = 0
    total_output_tokens = 0

    for i, inv in enumerate(invoices, 1):
        filename = inv.get("file", "unknown")
        text = inv.get("text", "")

        if not text.strip():
            print(f"  [{i}/{len(invoices)}] ✗ {filename}: empty text, skipping")
            failed += 1
            continue

        # Check if already processed
        existing = db.execute(
            "SELECT id FROM transactions WHERE file_name = ?", (filename,)
        ).fetchone()
        if existing:
            print(f"  [{i}/{len(invoices)}] → Skip (already processed): {filename}")
            skipped += 1
            continue

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": PROMPT_TEMPLATE.format(text=text[:3000]),
                }],
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            raw = response.content[0].text.strip()
            # Clean markdown wrapping if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            data = json.loads(raw)

            # Auto-categorize if AI didn't determine category
            category = data.get("category", "other")
            if category == "other":
                cat, _ = categorize_vendor(data.get("vendor", ""))
                if cat != "other":
                    category = cat

            db.execute("""
                INSERT INTO transactions
                    (date, vendor, amount, category, source, file_name, raw_text)
                VALUES (?, ?, ?, ?, 'upload', ?, ?)
            """, (
                data.get("date"),
                data.get("vendor", filename),
                data.get("amount"),
                category,
                filename,
                text[:5000],
            ))
            db.commit()
            processed += 1

            vendor = data.get("vendor", "?")
            amount = data.get("amount", "?")
            print(f"  [{i}/{len(invoices)}] ✓ {filename} → {vendor} ${amount}")

            # Small delay to avoid rate limits
            time.sleep(0.1)

        except json.JSONDecodeError as e:
            print(f"  [{i}/{len(invoices)}] ✗ {filename}: JSON parse error — {e}")
            failed += 1
        except Exception as e:
            print(f"  [{i}/{len(invoices)}] ✗ {filename}: {e}")
            failed += 1

    db.close()

    # Cost estimate
    input_cost = total_input_tokens / 1_000_000 * 0.25
    output_cost = total_output_tokens / 1_000_000 * 1.25
    total_cost = input_cost + output_cost

    print(f"\n{'=' * 60}")
    print(f"✓ Processed: {processed}")
    print(f"→ Skipped:   {skipped}")
    print(f"✗ Failed:    {failed}")
    print(f"\nToken usage:")
    print(f"  Input:  {total_input_tokens:,} tokens (${input_cost:.4f})")
    print(f"  Output: {total_output_tokens:,} tokens (${output_cost:.4f})")
    print(f"  Total cost: ${total_cost:.4f}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
