"""
AI Insights — Spending coach and smart shopping list.
Supports both Anthropic Claude and Google Gemini via the unified provider.
Only sends aggregated summaries, never raw transaction data.
"""

import json
import os
import traceback
from .provider import call_llm, get_provider, clean_json_response


async def generate_spending_insights(summary_text: str) -> str:
    """
    Send aggregated spending summary to AI for analysis.
    Returns 5 specific, actionable insights.
    """
    if not get_provider():
        return _fallback_insights(summary_text)

    prompt = f"""You are a personal finance coach. Analyze this 90-day spending summary and give
5 specific, actionable insights. Be direct and concrete.
Use bullet points. Keep each insight to 1-2 sentences.

Spending summary:
{summary_text}

Focus on: patterns, bulk-buying opportunities, subscription audit,
and one specific savings tip."""

    try:
        return call_llm(prompt=prompt, model_tier="smart", max_tokens=800)
    except Exception as e:
        print(f"\n❌ AI insights failed: {e}")
        traceback.print_exc()
        return _fallback_insights(summary_text)


def _fallback_insights(summary_text: str) -> str:
    """Generate basic insights without AI when API key is unavailable."""
    lines = summary_text.strip().split("\n")
    insights = ["📊 **Spending Analysis** (generated locally — connect AI for deeper insights)\n"]

    if lines:
        insights.append(f"• You have spending data from {len(lines)} vendors in the last 90 days.")

    # Find highest spender
    max_total = 0
    max_vendor = ""
    for line in lines:
        if "$" in line:
            try:
                parts = line.split("$")
                amount = float(parts[1].split()[0])
                vendor = line.split(":")[0].strip()
                if amount > max_total:
                    max_total = amount
                    max_vendor = vendor
            except (ValueError, IndexError):
                continue

    if max_vendor:
        insights.append(f"• **Top spender:** {max_vendor} at ${max_total:.2f}")

    insights.append("• 💡 Tip: Set up your GEMINI_API_KEY or ANTHROPIC_API_KEY in .env for AI-powered analysis.")
    insights.append("• Review subscriptions monthly — small charges add up.")
    insights.append("• Consider buying bulk items at warehouse stores for frequent purchases.")

    return "\n".join(insights)


async def generate_shopping_suggestions(frequency_text: str) -> list[dict]:
    """
    Generate smart shopping list from purchase frequency data.
    Returns list of {item, store, frequency, est_price, list_type} dicts.
    """
    if not get_provider():
        return _fallback_shopping(frequency_text)

    prompt = f"""Based on this family's purchase frequency at various stores,
suggest a practical weekly shopping list tailored to their actual buying habits.

Return ONLY a valid JSON array with 8-10 items, no explanation:
[
  {{"item": "Whole milk (1 gallon)", "store": "Costco", "frequency": "Every week", "est_price": 6.00, "list_type": "weekly"}},
  ...
]

list_type should be "weekly", "monthly", or "subscriptions".
Include a mix of grocery staples and household essentials based on the purchase patterns below.

Purchase patterns:
{frequency_text}"""

    try:
        raw = call_llm(prompt=prompt, model_tier="smart", max_tokens=800)
        raw = clean_json_response(raw)
        items = json.loads(raw)
        return items if isinstance(items, list) else []

    except Exception as e:
        print(f"AI shopping list failed: {e}")
        return _fallback_shopping(frequency_text)


def _fallback_shopping(frequency_text: str) -> list[dict]:
    """Generate a generic shopping list without AI."""
    return [
        {"item": "Whole milk (1 gallon)", "store": "Costco", "frequency": "Every week", "est_price": 6.00, "list_type": "weekly"},
        {"item": "Eggs (18-pack)", "store": "Costco", "frequency": "Every week", "est_price": 8.00, "list_type": "weekly"},
        {"item": "Rice (10 lb)", "store": "Costco", "frequency": "Monthly", "est_price": 12.00, "list_type": "monthly"},
        {"item": "Organic bananas", "store": "Walmart", "frequency": "Every week", "est_price": 3.00, "list_type": "weekly"},
        {"item": "Bread (whole wheat)", "store": "Walmart", "frequency": "Every week", "est_price": 4.00, "list_type": "weekly"},
        {"item": "Yogurt (Greek, large)", "store": "Costco", "frequency": "Bi-weekly", "est_price": 7.00, "list_type": "weekly"},
        {"item": "Chicken breast (family pack)", "store": "Costco", "frequency": "Bi-weekly", "est_price": 18.00, "list_type": "weekly"},
        {"item": "Paper towels (bulk)", "store": "Costco", "frequency": "Monthly", "est_price": 22.00, "list_type": "monthly"},
    ]
