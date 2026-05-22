"""
Tabular Parser — Parse CSV and Excel (.xlsx/.xls) files using pandas.
Auto-detects common column formats for bank statements, Amazon exports, etc.
"""

import pandas as pd
import os
from datetime import datetime

# Common column name mappings for different CSV exports
COLUMN_MAPS = {
    "date": ["date", "transaction date", "trans date", "posted date", "order date", "Date"],
    "vendor": [
        "description", "merchant", "vendor", "name", "payee",
        "transaction description", "merchant name", "store", "title",
        "Description", "Merchant",
    ],
    "amount": [
        "amount", "total", "charge", "debit", "price",
        "transaction amount", "order total", "Amount", "Total",
    ],
    "category": ["category", "type", "transaction type", "Category"],
}


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find the first matching column name from candidates."""
    df_cols_lower = {c.lower().strip(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in df_cols_lower:
            return df_cols_lower[candidate.lower()]
    return None


def _normalize_date(date_str: str) -> str | None:
    """Try to parse a date string into YYYY-MM-DD format."""
    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y",
        "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y", "%m-%d-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return None


def _normalize_amount(amount) -> float | None:
    """Clean and convert amount to float."""
    if pd.isna(amount):
        return None
    try:
        # Remove currency symbols, commas, whitespace
        cleaned = str(amount).replace("$", "").replace(",", "").replace(" ", "").strip()
        # Handle parentheses for negative (accounting format)
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]
        val = float(cleaned)
        return abs(val)  # We track spending as positive
    except (ValueError, TypeError):
        return None


def parse_csv_file(filepath: str) -> list[dict]:
    """
    Parse a CSV file and return a list of transaction dicts.
    Auto-detects column mappings for common bank/store export formats.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV not found: {filepath}")

    # Try reading with different encodings
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            df = pd.read_csv(filepath, encoding=encoding)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    else:
        raise RuntimeError(f"Could not read CSV file: {filepath}")

    if df.empty:
        return []

    # Find column mappings
    date_col = _find_column(df, COLUMN_MAPS["date"])
    vendor_col = _find_column(df, COLUMN_MAPS["vendor"])
    amount_col = _find_column(df, COLUMN_MAPS["amount"])
    category_col = _find_column(df, COLUMN_MAPS["category"])

    if not date_col or not vendor_col:
        raise ValueError(
            f"Could not detect date and vendor columns. "
            f"Found columns: {list(df.columns)}. "
            f"Expected at least a date column ({COLUMN_MAPS['date']}) "
            f"and a vendor column ({COLUMN_MAPS['vendor']})."
        )

    transactions = []
    for _, row in df.iterrows():
        date = _normalize_date(row.get(date_col))
        vendor = str(row.get(vendor_col, "Unknown")).strip()
        amount = _normalize_amount(row.get(amount_col)) if amount_col else None
        category = str(row.get(category_col, "other")).strip().lower() if category_col else "other"

        if not date or not vendor or vendor == "nan":
            continue

        transactions.append({
            "date": date,
            "vendor": vendor,
            "amount": amount,
            "category": category,
        })

    return transactions


def parse_excel_file(filepath: str, sheet_name: int | str = 0) -> list[dict]:
    """
    Parse an Excel (.xlsx/.xls) file and return a list of transaction dicts.
    Auto-detects column mappings just like CSV parsing.

    Args:
        filepath: Path to Excel file.
        sheet_name: Sheet to read (0 = first sheet, or name as string).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Excel file not found: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()
    engine = "openpyxl" if ext == ".xlsx" else "xlrd" if ext == ".xls" else None

    try:
        df = pd.read_excel(filepath, sheet_name=sheet_name, engine=engine)
    except Exception as e:
        raise RuntimeError(f"Could not read Excel file: {filepath} — {e}")

    if df.empty:
        return []

    # Reuse the same column detection + normalization logic as CSV
    date_col = _find_column(df, COLUMN_MAPS["date"])
    vendor_col = _find_column(df, COLUMN_MAPS["vendor"])
    amount_col = _find_column(df, COLUMN_MAPS["amount"])
    category_col = _find_column(df, COLUMN_MAPS["category"])

    if not date_col or not vendor_col:
        raise ValueError(
            f"Could not detect date and vendor columns in Excel file. "
            f"Found columns: {list(df.columns)}. "
            f"Expected at least a date column ({COLUMN_MAPS['date']}) "
            f"and a vendor column ({COLUMN_MAPS['vendor']})."
        )

    transactions = []
    for _, row in df.iterrows():
        # Excel dates may already be datetime objects
        raw_date = row.get(date_col)
        if isinstance(raw_date, (pd.Timestamp, datetime)):
            date = raw_date.strftime("%Y-%m-%d")
        else:
            date = _normalize_date(raw_date)

        vendor = str(row.get(vendor_col, "Unknown")).strip()
        amount = _normalize_amount(row.get(amount_col)) if amount_col else None
        category = str(row.get(category_col, "other")).strip().lower() if category_col else "other"

        if not date or not vendor or vendor == "nan":
            continue

        transactions.append({
            "date": date,
            "vendor": vendor,
            "amount": amount,
            "category": category,
        })

    return transactions


def parse_tabular_file(filepath: str) -> list[dict]:
    """
    Auto-detect file type and parse accordingly.
    Supports: .csv, .xlsx, .xls
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        return parse_csv_file(filepath)
    elif ext in (".xlsx", ".xls"):
        return parse_excel_file(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Supported: .csv, .xlsx, .xls")
