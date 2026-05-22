"""Quick script to analyze sample bill formats in resources/"""
import pandas as pd
import pdfplumber
import os

BASE = os.path.dirname(__file__)

# === Walmart Excel ===
walmart_file = os.path.join(BASE, "resources/walmart/Order_55469595358245856835.xlsx")
if os.path.exists(walmart_file):
    df = pd.read_excel(walmart_file)
    print("=" * 60)
    print("WALMART EXCEL ANALYSIS")
    print("=" * 60)
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"\nDtypes:\n{df.dtypes}")
    print(f"\nFirst 3 rows:")
    for i, row in df.head(3).iterrows():
        print(f"  Row {i}: {dict(row)}")
    print()

# === Costco PDF ===
costco_file = os.path.join(BASE, "resources/costco/Order_19169187152450000.pdf")
if os.path.exists(costco_file):
    print("=" * 60)
    print("COSTCO PDF ANALYSIS")
    print("=" * 60)
    with pdfplumber.open(costco_file) as pdf:
        print(f"Pages: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages[:2]):
            text = page.extract_text()
            print(f"\n--- Page {i+1} (first 1500 chars) ---")
            print(text[:1500] if text else "(no text)")
