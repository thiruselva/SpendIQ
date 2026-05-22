"""
PDF Parser — Extract text from PDF invoices using pdfplumber.
"""

import pdfplumber
import os


def extract_text_from_pdf(filepath: str) -> str:
    """
    Extract all text content from a PDF file.
    Returns concatenated text from all pages.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"PDF not found: {filepath}")

    try:
        with pdfplumber.open(filepath) as pdf:
            text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"Failed to parse PDF {filepath}: {e}")


def extract_all_from_directory(directory: str) -> list[dict]:
    """
    Extract text from all PDFs in a directory.
    Returns list of {file, text, chars} dicts.
    """
    results = []
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    for filename in sorted(os.listdir(directory)):
        if not filename.lower().endswith(".pdf"):
            continue
        filepath = os.path.join(directory, filename)
        try:
            text = extract_text_from_pdf(filepath)
            results.append({
                "file": filename,
                "text": text,
                "chars": len(text),
            })
            print(f"✓ {filename} ({len(text)} chars)")
        except Exception as e:
            print(f"✗ {filename}: {e}")
            results.append({
                "file": filename,
                "text": "",
                "chars": 0,
                "error": str(e),
            })

    return results
