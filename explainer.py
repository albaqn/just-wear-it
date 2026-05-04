# explainer.py
# Generates the natural language explanation for why an outfit was chosen.
# This is what satisfies the assignment's "explain its decision" requirement.
#
# IMPORTANT: The DECISION is made by recommender.py (pure Python logic).
# This file only EXPLAINS that decision in human-readable language.
# The AI here is a narrator, not a decision-maker.
#
# ── REQUIRES API KEY ──────────────────────────────────────────────────────────
# Set your key in a .env file:   ANTHROPIC_API_KEY=sk-ant-...

import os
import json

try:
    import anthropic
    _client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
    )
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    _client = None

MODEL = "claude-haiku-4-5-20251001"


def explain_outfit(selected_items: list[dict],
                   preferences_summary: str,
                   score_breakdown: dict,
                   theme_profile: dict = None) -> dict:
    """
    Generates a natural language explanation for the recommended outfit.

    Args:
        selected_items:      list of item dicts from recommender.py
        preferences_summary: text from preferences.to_text_summary()
        score_breakdown:     score dict from OutfitScore.to_dict()

    Returns:
        dict with:
        - title:      short punchy headline (e.g. "Classic meets effortless")
        - paragraph:  full explanation paragraph
        - tags:       list of short reason tags (e.g. ["Office-ready", "Neutral palette"])
        - error:      None or error message
    """
    if not API_AVAILABLE or not _client:
        return _mock_explanation(selected_items, preferences_summary)

    outfit_description = _format_outfit_for_prompt(selected_items)
    prompt = _build_prompt(outfit_description, preferences_summary, score_breakdown, theme_profile or {})

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text.strip()
        return _parse_explanation(raw_text)

    except Exception as e:
        return _fallback_explanation(selected_items, preferences_summary, str(e))


def _build_prompt(outfit_description: str,
                  preferences_summary: str,
                  score_breakdown: dict,
                  theme_profile: dict = None) -> str:
    """
    Builds the prompt sent to the API.
    Explicitly tells the model it is EXPLAINING a decision already made,
    not making a new one.
    """
    # Build theme section if a theme was provided
    theme_section = ""
    if theme_profile and theme_profile.get("summary"):
        theme_colors  = ", ".join(theme_profile.get("colors", [])[:4])
        theme_keywords = ", ".join(theme_profile.get("keywords", [])[:4])
        theme_summary  = theme_profile.get("summary", "")
        theme_section = f"""
THEME/AESTHETIC THE USER IS GOING FOR:
Summary: {theme_summary}
Typical colors for this aesthetic: {theme_colors}
Vibe keywords: {theme_keywords}
When writing your explanation, connect the chosen outfit back to this aesthetic.
Tell the user HOW this outfit fits the theme — be specific and enthusiastic.
"""

    return f"""
You are a personal stylist explaining why a specific outfit was chosen for someone.

The outfit was already selected by an algorithm. Your job is ONLY to explain it
in a warm, confident, fashion-forward tone. Do not suggest alternatives or critique the choice.

THE CHOSEN OUTFIT:
{outfit_description}

THE USER'S PREFERENCES:
{preferences_summary}
{theme_section}
ALGORITHM SCORE BREAKDOWN:
- Occasion fit score:    {score_breakdown.get('occasion_score', 0):.0f}/100
- Formality match:       {score_breakdown.get('formality_score', 0):.0f}/100
- Style alignment:       {score_breakdown.get('style_score', 0):.0f}/100
- Color harmony:         {score_breakdown.get('color_score', 0):.0f}/100
- Overall score:         {score_breakdown.get('total', 0):.0f}/100

Respond ONLY with a valid JSON object. No extra text.

JSON format:
{{
  "title": "Short punchy headline capturing the outfit + theme vibe (max 8 words)",
  "paragraph": "2-3 sentences explaining why this outfit works. If there is a theme, specifically connect the outfit to that aesthetic. Mention actual colors and occasion.",
  "tags": ["3 to 6 short tags — include theme-related tags if applicable, e.g. Garden-party ready, Floral moment, Coastal vibes"]
}}
"""


def _format_outfit_for_prompt(selected_items: list[dict]) -> str:
    """Formats the outfit items as a readable list for the prompt."""
    lines = []
    for item in selected_items:
        lines.append(
            f"- {item.get('description', 'item')} "
            f"(category: {item.get('category')}, "
            f"color: {item.get('color')}, "
            f"formality: {item.get('formality')}/10, "
            f"styles: {', '.join(item.get('styles', []))})"
        )
    return "\n".join(lines)


def _parse_explanation(raw_text: str) -> dict:
    """Parses the JSON explanation from the API response."""
    import re

    try:
        data = json.loads(raw_text)
        return _clean_explanation(data)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return _clean_explanation(data)
        except json.JSONDecodeError:
            pass

    # If JSON parsing fails entirely, extract what we can
    return {
        "title":     "Your outfit for today",
        "paragraph": raw_text[:300] if raw_text else "This outfit was selected to match your preferences.",
        "tags":      [],
        "error":     "Could not parse structured response",
    }


def _clean_explanation(data: dict) -> dict:
    """Ensures all fields are present and well-formed."""
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    return {
        "title":     str(data.get("title", "Your outfit for today")),
        "paragraph": str(data.get("paragraph", "")),
        "tags":      [str(t) for t in tags[:6]],  # max 6 tags
        "error":     None,
    }


def _mock_explanation(selected_items: list[dict], preferences_summary: str) -> dict:
    """
    Returns a template explanation when no API key is available.
    Used during development.
    """
    descriptions = [item.get("description", "item") for item in selected_items]
    occasion = "today"
    for line in preferences_summary.split("\n"):
        if "Occasion:" in line:
            occasion = line.split(":")[1].strip()
            break

    return {
        "title":     f"A confident look for {occasion}",
        "paragraph": (
            f"This outfit — {', '.join(descriptions)} — was selected to match your "
            f"preferences for {occasion}. The pieces were chosen based on formality alignment, "
            f"style compatibility, and color harmony."
        ),
        "tags": ["Style-matched", "Formality-calibrated", "Color-harmonious"],
        "error": "API key not set — using mock explanation",
    }


def _fallback_explanation(selected_items: list[dict],
                           preferences_summary: str,
                           error_message: str) -> dict:
    """Returns a graceful fallback if the API call fails."""
    mock = _mock_explanation(selected_items, preferences_summary)
    mock["error"] = f"API call failed: {error_message}"
    return mock

