# vision.py
# Analyzes clothing photos using the Anthropic vision API.
#
# Strategy:
# 1. Try a detailed prompt first (VISION_PROMPT)
# 2. If result is "other" or invalid, retry with a simpler fallback prompt
# 3. Post-process the result to catch common misclassifications
# 4. Extract color from the image directly as last resort

import os
import base64
import json
import re
from pathlib import Path
from typing import Optional, Tuple

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

# ── PRIMARY PROMPT ────────────────────────────────────────────────────────────
VISION_PROMPT = """Look at this clothing item photo.

Your ONLY job is to identify what type of clothing this is and describe it.
Photos may be blurry, on a hanger, on a person, folded, or poorly lit. Do your best.

CATEGORY — choose by physical shape, NOT by color or pattern:
- "top": ANY shirt, t-shirt, blouse, sweater, hoodie, sweatshirt, tank top, crop top, knit top
- "bottom": ANY pants, jeans, denim, trousers, shorts, skirt, leggings (DENIM IS ALWAYS "bottom")
- "dress": one-piece covering torso AND legs together (dress, jumpsuit, romper)
- "outerwear": worn OVER other clothes (jacket, coat, blazer, cardigan)
- "shoes": any footwear
- "accessory": ONLY bags, belts, hats, scarves, jewelry — NOT clothing
- "other": ONLY if you truly cannot tell what this is at all

CRITICAL RULES:
- A t-shirt with polka dots is "top" not "accessory"
- A patterned or printed garment is STILL categorized by its shape
- Jeans = "bottom" always. Hoodie = "top" always.
- If it covers the upper body = "top". If it covers legs = "bottom".

COLOR — name the single most visible/dominant color specifically:
- "white", "black", "grey", "navy blue", "light blue", "olive green", "burgundy", "beige", etc.
- For denim: "light blue denim", "dark blue denim", "black denim"
- For patterns: name the background color (e.g. "white" for white shirt with black dots)
- NEVER say "multicolored" or "colorful" — always pick ONE dominant color

Respond with ONLY this JSON:
{
  "category": "top" or "bottom" or "dress" or "outerwear" or "shoes" or "accessory" or "other",
  "color": "dominant color name",
  "color_hex": "#RRGGBB",
  "formality": 1 to 10,
  "styles": ["1 to 3 of: minimalist, classic, bohemian, streetwear, preppy, romantic, edgy, business, athleisure, elegant"],
  "description": "3-5 words e.g. white polka dot t-shirt",
  "season": ["all"],
  "pattern": "solid" or "stripes" or "plaid" or "floral" or "print" or "other"
}"""

# ── FALLBACK PROMPT — simpler, used when primary returns "other" ─────────────
FALLBACK_PROMPT = """This is a photo of a clothing item. I need just two things:

1. What TYPE is it? Pick ONE:
   - top (shirt, tshirt, blouse, sweater, hoodie, anything covering the upper body)
   - bottom (pants, jeans, shorts, skirt, leggings, anything covering the legs)
   - dress (one piece covering body from top to bottom)
   - outerwear (jacket, coat, blazer)
   - shoes (any footwear)
   - accessory (bag, belt, hat, scarf, jewelry only)

2. What is the main COLOR? One specific color name.

Reply ONLY with this JSON:
{"category": "...", "color": "...", "color_hex": "#......"}"""

# ── COLOR GUESSES by description keywords ────────────────────────────────────
# Used as a final fallback if the API gives no color
COLOR_KEYWORD_MAP = {
    "black": "#1A1612", "white": "#FFFFFF", "grey": "#9E9E9E", "gray": "#9E9E9E",
    "navy": "#2C3E50", "blue": "#3B6FB6", "denim": "#3B6FB6", "jeans": "#3B6FB6",
    "red": "#C0392B", "pink": "#E91E8C", "orange": "#E67E22", "yellow": "#F1C40F",
    "green": "#27AE60", "olive": "#7A8C3C", "purple": "#8E44AD", "brown": "#795548",
    "beige": "#D4C5B0", "cream": "#F5EFE4", "camel": "#C19A6B", "tan": "#D2B48C",
    "burgundy": "#800020", "maroon": "#800000", "teal": "#008080",
}


def analyze_image(image_path: str) -> dict:
    """
    Main entry point. Tries primary prompt, then fallback, then gives up gracefully.
    Never returns a useless result — always provides at least a color and best-guess category.
    """
    if not API_AVAILABLE or not _client:
        return _mock_analysis(image_path)

    image_data, media_type = _load_image(image_path)
    if image_data is None:
        return _error_result(f"Could not read image: {image_path}")

    # ── Attempt 1: Full prompt ────────────────────────────────────────────────
    result = _call_vision(image_data, media_type, VISION_PROMPT, max_tokens=500)

    # ── Attempt 2: If result is "other" or bad, retry with simpler prompt ────
    if result.get("category") == "other" or result.get("error"):
        fallback = _call_vision(image_data, media_type, FALLBACK_PROMPT, max_tokens=150)
        if fallback.get("category") != "other":
            # Merge: use fallback category/color, keep other fields from attempt 1
            result["category"]  = fallback.get("category", result["category"])
            result["color"]     = fallback.get("color", result["color"])
            result["color_hex"] = fallback.get("color_hex", result["color_hex"])
            result["error"]     = None

    # ── Post-processing: catch known misclassifications ───────────────────────
    result = _post_process(result, image_path)

    return result


def _call_vision(image_data: str, media_type: str, prompt: str, max_tokens: int) -> dict:
    """Makes a single API call and returns parsed result."""
    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": media_type,
                            "data":       image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = response.content[0].text.strip()
        return _parse_response(raw)
    except Exception as e:
        return _error_result(str(e))


def _post_process(result: dict, image_path: str) -> dict:
    """
    Catches common misclassifications and fixes them.
    This is the safety net for prompt failures.
    """
    cat = result.get("category", "other")
    desc = result.get("description", "").lower()

    # ── Rule 1: accessory should almost never be the result for clothing ────
    # If something was classified as accessory but the description mentions
    # clear clothing words, override it
    clothing_words_for_top = ["shirt", "tee", "t-shirt", "blouse", "top", "sweater",
                               "hoodie", "sweatshirt", "knit", "tank", "crop", "polo"]
    clothing_words_for_bottom = ["pants", "jeans", "denim", "trousers", "shorts",
                                  "skirt", "leggings", "chinos", "slacks"]
    clothing_words_for_dress = ["dress", "gown", "jumpsuit", "romper", "overalls"]
    clothing_words_for_outer = ["jacket", "coat", "blazer", "cardigan", "parka"]

    if cat == "accessory" or cat == "other":
        if any(w in desc for w in clothing_words_for_top):
            result["category"] = "top"
        elif any(w in desc for w in clothing_words_for_bottom):
            result["category"] = "bottom"
        elif any(w in desc for w in clothing_words_for_dress):
            result["category"] = "dress"
        elif any(w in desc for w in clothing_words_for_outer):
            result["category"] = "outerwear"

    # ── Rule 2: filename hints as last resort ────────────────────────────────
    filename = Path(image_path).stem.lower()
    if result.get("category") == "other":
        for word in clothing_words_for_top:
            if word.replace("-","") in filename:
                result["category"] = "top"; break
        for word in clothing_words_for_bottom:
            if word in filename:
                result["category"] = "bottom"; break
        for word in clothing_words_for_dress:
            if word in filename:
                result["category"] = "dress"; break

    # ── Rule 3: Fix missing or generic colors ────────────────────────────────
    color = result.get("color", "").lower()
    if not color or color in ["unknown", "colorful", "multicolored", "various", "mixed"]:
        # Try to guess from description or filename
        combined = desc + " " + filename
        for keyword, hex_val in COLOR_KEYWORD_MAP.items():
            if keyword in combined:
                result["color"]     = keyword
                result["color_hex"] = hex_val
                break
        if not result.get("color") or result["color"] == "unknown":
            result["color"]     = "mixed colors"
            result["color_hex"] = "#888888"

    # ── Rule 4: Ensure description never shows filename ──────────────────────
    raw_desc = result.get("description", "")
    if not raw_desc or any(ext in raw_desc.lower() for ext in [".jpg",".png",".jpeg",".webp"]):
        result["description"] = f"{result['color']} {result['category']}"

    return result


def _load_image(image_path: str) -> Tuple[Optional[str], str]:
    path = Path(image_path)
    if not path.exists():
        return None, ""
    suffix = path.suffix.lower()
    media_type_map = {
        ".jpg":"image/jpeg", ".jpeg":"image/jpeg",
        ".png":"image/png", ".gif":"image/gif", ".webp":"image/webp",
    }
    media_type = media_type_map.get(suffix, "image/jpeg")
    with open(path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")
    return image_data, media_type


def _parse_response(raw_text: str) -> dict:
    try:
        return _validate_and_clean(json.loads(raw_text))
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match:
        try:
            return _validate_and_clean(json.loads(match.group()))
        except json.JSONDecodeError:
            pass
    return _error_result(f"Could not parse: {raw_text[:80]}")


def _validate_and_clean(data: dict) -> dict:
    valid_categories = ["top","bottom","shoes","outerwear","accessory","dress","other"]
    valid_patterns   = ["solid","stripes","plaid","floral","print","other"]
    valid_seasons    = ["spring","summer","fall","winter","all"]
    valid_styles     = ["minimalist","classic","bohemian","streetwear","preppy",
                        "romantic","edgy","business","athleisure","elegant"]

    cat = data.get("category","other")
    if cat not in valid_categories:
        cat = "other"

    color = str(data.get("color","unknown")).strip()
    if not color or color.lower() in ["null","none",""]:
        color = "unknown"

    return {
        "category":    cat,
        "color":       color,
        "color_hex":   str(data.get("color_hex","#888888")),
        "formality":   max(1, min(10, int(data.get("formality", 5)))),
        "styles":      [s for s in data.get("styles",[]) if s in valid_styles],
        "description": str(data.get("description","clothing item")),
        "season":      [s for s in data.get("season",["all"]) if s in valid_seasons] or ["all"],
        "pattern":     data.get("pattern","solid") if data.get("pattern") in valid_patterns else "solid",
        "error":       None,
    }


def _error_result(message: str) -> dict:
    return {
        "category":"other","color":"unknown","color_hex":"#888888",
        "formality":5,"styles":[],"description":"clothing item",
        "season":["all"],"pattern":"solid","error":message,
    }


def _mock_analysis(image_path: str) -> dict:
    filename = Path(image_path).stem.lower()
    hints = {
        "blazer":("outerwear",8,["classic","business"]),
        "jacket":("outerwear",6,["classic","casual"]),
        "coat":  ("outerwear",7,["classic","elegant"]),
        "blouse":("top",7,["elegant","minimalist"]),
        "shirt": ("top",5,["classic","casual"]),
        "tshirt":("top",2,["casual","minimalist"]),
        "tee":   ("top",2,["casual","minimalist"]),
        "hoodie":("top",2,["casual","athleisure"]),
        "sweater":("top",4,["classic","casual"]),
        "top":   ("top",4,["casual"]),
        "dress": ("dress",7,["elegant","classic"]),
        "skirt": ("bottom",6,["classic","romantic"]),
        "jeans": ("bottom",3,["casual","streetwear"]),
        "denim": ("bottom",3,["casual","streetwear"]),
        "pants": ("bottom",5,["classic"]),
        "trouser":("bottom",7,["classic","business"]),
        "leggings":("bottom",2,["athleisure"]),
        "shorts":("bottom",2,["casual"]),
        "shoes": ("shoes",5,["classic"]),
        "heels": ("shoes",8,["elegant","classic"]),
        "boots": ("shoes",5,["edgy","classic"]),
        "sneaker":("shoes",2,["casual","athleisure"]),
        "loafer":("shoes",6,["classic","preppy"]),
        "sandal":("shoes",4,["casual","bohemian"]),
    }
    for hint, (cat, form, styles) in hints.items():
        if hint in filename:
            return {
                "category":cat,"color":"unknown (mock)","color_hex":"#888888",
                "formality":form,"styles":styles,
                "description":f"{filename.replace('_',' ')} (mock)",
                "season":["all"],"pattern":"solid",
                "error":"API key not set — mock data",
            }
    return _error_result("API key not set")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        r = analyze_image(sys.argv[1])
        print(json.dumps(r, indent=2))
    else:
        print("Usage: python3 vision.py path/to/image.jpg")
