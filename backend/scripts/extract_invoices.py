"""
Stage 1 — Local PDF text extraction.
Extracts raw text from all PDFs in the invoices directory.
Zero API cost. Outputs extracted.json.
"""

import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parsers.pdf_parser import extract_all_from_directory

INVOICE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "invoices")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "extracted.json")


def main():
    print("=" * 60)
    print("SpendIQ — Stage 1: Local PDF Text Extraction")
    print("=" * 60)
    print(f"\nInvoice directory: {os.path.abspath(INVOICE_DIR)}")

    if not os.path.isdir(INVOICE_DIR):
        os.makedirs(INVOICE_DIR, exist_ok=True)
        print(f"\n⚠ Invoice directory created at {os.path.abspath(INVOICE_DIR)}")
        print("  Copy your PDF invoices there and run this script again.")
        return

    pdf_files = [f for f in os.listdir(INVOICE_DIR) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print("\n⚠ No PDF files found in the invoices directory.")
        print(f"  Copy your PDFs to: {os.path.abspath(INVOICE_DIR)}")
        return

    print(f"Found {len(pdf_files)} PDF files\n")

    results = extract_all_from_directory(INVOICE_DIR)

    # Save results
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    success = sum(1 for r in results if r.get("chars", 0) > 0)
    failed = len(results) - success
    total_chars = sum(r.get("chars", 0) for r in results)

    print(f"\n{'=' * 60}")
    print(f"✓ Extracted {success}/{len(results)} invoices")
    if failed > 0:
        print(f"✗ {failed} files failed")
    print(f"Total characters extracted: {total_chars:,}")
    print(f"Output: {os.path.abspath(OUTPUT_FILE)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
