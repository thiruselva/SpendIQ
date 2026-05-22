"""
AI Extractor — Parse invoice text into structured data.
Supports both Anthropic Claude and Google Gemini via the unified provider.
Uses the cheapest/fastest model tier for structured JSON extraction.
"""

import json
import os
from .provider import call_llm, get_provider, clean_json_response

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


async def parse_invoice_text(text: str, filename: str = "") -> dict:
    """
    Send extracted PDF text to AI (Claude Haiku or Gemini Flash) for structured parsing.
    Returns dict with: date, vendor, amount, category, items.
    """
    if not get_provider():
        return _fallback_parse(text, filename)

    try:
        raw = call_llm(
            prompt=PROMPT_TEMPLATE.format(text=text[:3000]),
            model_tier="fast",
            max_tokens=300,
        )
        raw = clean_json_response(raw)
        data = json.loads(raw)
        return data

    except json.JSONDecodeError:
        return _fallback_parse(text, filename)
    except Exception as e:
        print(f"AI extraction failed for {filename}: {e}")
        return _fallback_parse(text, filename)


def _fallback_parse(text: str, filename: str) -> dict:
    """
    Basic text-based parsing when AI is unavailable.
    Extracts what it can from the raw text.
    """
    import re
    from datetime import datetime

    result = {
        "date": None,
        "vendor": filename.replace(".pdf", "").replace("_", " ") if filename else "Unknown",
        "amount": None,
        "category": "other",
        "items": [],
    }

    # Try to find a date
    date_patterns = [
        r"(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\w+ \d{1,2},? \d{4})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            for fmt in ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"]:
                try:
                    result["date"] = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if result["date"]:
                break

    # Try to find a total amount
    amount_patterns = [
        r"(?:total|amount|due|charged|grand total)[:\s]*\$?([\d,]+\.?\d*)",
        r"\$\s*([\d,]+\.\d{2})",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                result["amount"] = float(match.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    return result
