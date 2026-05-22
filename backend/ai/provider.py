"""
AI Provider — Unified interface for Anthropic Claude and Google Gemini.
Auto-detects which API key is available.
Priority: GEMINI_API_KEY > ANTHROPIC_API_KEY (configurable via AI_PROVIDER env var).
"""

import os
import json

# Provider type constants
ANTHROPIC = "anthropic"
GEMINI = "gemini"
NONE = None


def get_provider() -> str | None:
    """
    Determine which AI provider to use based on available API keys.
    Override with AI_PROVIDER env var ("anthropic" or "gemini").
    """
    forced = os.getenv("AI_PROVIDER", "").lower().strip()
    if forced == ANTHROPIC and os.getenv("ANTHROPIC_API_KEY"):
        return ANTHROPIC
    if forced == GEMINI and os.getenv("GEMINI_API_KEY"):
        return GEMINI

    # Auto-detect: check both, prefer whichever is set
    if os.getenv("GEMINI_API_KEY"):
        return GEMINI
    if os.getenv("ANTHROPIC_API_KEY"):
        return ANTHROPIC
    return NONE


def call_llm(
    prompt: str,
    model_tier: str = "fast",
    max_tokens: int = 800,
) -> str:
    """
    Call the configured LLM provider with a prompt.

    Args:
        prompt: The user prompt text.
        model_tier: "fast" for extraction (Haiku / Flash) or "smart" for insights (Sonnet / Pro).
        max_tokens: Maximum output tokens.

    Returns:
        The model's response text.

    Raises:
        RuntimeError if no AI provider is configured.
    """
    provider = get_provider()
    print(f"[AI] Provider={provider}, tier={model_tier}, GEMINI_KEY={'set' if os.getenv('GEMINI_API_KEY') else 'missing'}, ANTHROPIC_KEY={'set' if os.getenv('ANTHROPIC_API_KEY') else 'missing'}")

    if provider == ANTHROPIC:
        return _call_anthropic(prompt, model_tier, max_tokens)
    elif provider == GEMINI:
        return _call_gemini(prompt, model_tier, max_tokens)
    else:
        raise RuntimeError(
            "No AI provider configured. Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env"
        )


def _call_anthropic(prompt: str, model_tier: str, max_tokens: int) -> str:
    """Call Anthropic Claude API."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = "claude-haiku-4-5"

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _call_gemini(prompt: str, model_tier: str, max_tokens: int) -> str:
    """Call Google Gemini API."""
    from google import genai

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    model = "gemini-2.5-flash-lite"

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=0.3,
        ),
    )
    return response.text.strip()


def clean_json_response(raw: str) -> str:
    """Strip markdown code fences from an LLM JSON response."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


def get_provider_info() -> dict:
    """Return info about the active AI provider for the frontend."""
    provider = get_provider()
    if provider == ANTHROPIC:
        return {"provider": "anthropic", "label": "Claude (Anthropic)", "configured": True}
    elif provider == GEMINI:
        return {"provider": "gemini", "label": "Gemini (Google)", "configured": True}
    else:
        return {"provider": None, "label": "None", "configured": False}
