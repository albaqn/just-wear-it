# recommender.py
# THE CORE DECISION SYSTEM.
#
# Every preference slider is now meaningful:
# - Casual↔Formal:       controls target formality level
# - Comfort↔Style:       shifts scoring between practical items vs. stylish ones
# - Minimal↔Layered:     penalizes/rewards outerwear and layering
# - Conservative↔Bold:   penalizes/rewards pattern, color contrast, statement pieces
# - Weather sensitivity: scales weather scoring weight
#
# Style matching is fuzzy (related styles count partially) and
# also reads item description words directly.

from wardrobe import Wardrobe, ClothingItem
from preferences import Preferences
from theme_analyzer import analyze_theme, theme_score_item
from weather import weather_score_item
import math
import random

# ── Occasion constraints ─────────────────────────────────────────────────────
OCCASION_FORMALITY_RANGE = {
    "office":  (40, 100),
    "casual":  (0,  55),
    "dinner":  (55, 100),
    "event":   (60, 100),
    "active":  (0,  25),
    "travel":  (0,  60),
}

OCCASION_STYLE_BOOST = {
    "office":  ["business","classic","minimalist","elegant"],
    "casual":  ["minimalist","streetwear","bohemian","athleisure","preppy"],
    "dinner":  ["elegant","classic","romantic"],
    "event":   ["elegant","romantic","classic","edgy"],
    "active":  ["athleisure","streetwear"],
    "travel":  ["minimalist","casual","classic","athleisure"],
}

OCCASION_BLOCKED_CATEGORIES = {
    "active": ["dress","outerwear"],
}

# ── Style families — fuzzy matching ──────────────────────────────────────────
# If user picks "bohemian", items tagged "romantic" still get partial credit.
# Groups styles that overlap in real-world perception.
STYLE_FAMILIES = {
    "minimalist":  {"minimalist","classic","clean","simple","basic"},
    "classic":     {"classic","preppy","business","minimalist","elegant","timeless"},
    "bohemian":    {"bohemian","romantic","earthy","free","artistic","whimsical"},
    "streetwear":  {"streetwear","edgy","urban","casual","athleisure"},
    "preppy":      {"preppy","classic","business","clean","collegiate"},
    "romantic":    {"romantic","bohemian","elegant","feminine","soft"},
    "edgy":        {"edgy","streetwear","bold","dark","alternative"},
    "business":    {"business","classic","elegant","formal","preppy"},
    "athleisure":  {"athleisure","streetwear","casual","sporty","active"},
    "elegant":     {"elegant","classic","romantic","chic","sophisticated"},
}

# Words in item descriptions that signal style aesthetics
# Used to infer style even when API tags are imprecise
DESC_STYLE_SIGNALS = {
    "minimalist":  ["clean","simple","basic","plain","minimal","structured","crisp"],
    "classic":     ["tailored","structured","classic","crisp","button","oxford","polo","trench"],
    "bohemian":    ["flowy","boho","embroidered","lace","crochet","fringe","wrap","peasant","floral"],
    "streetwear":  ["graphic","oversized","baggy","cargo","hoodie","jogger","sneaker","cap"],
    "preppy":      ["plaid","argyle","blazer","chino","loafer","oxford","stripe","polo","collar"],
    "romantic":    ["floral","ruffle","lace","silk","satin","soft","feminine","wrap","blush"],
    "edgy":        ["leather","moto","studded","ripped","distressed","combat","chain","dark"],
    "business":    ["blazer","trouser","button","collared","formal","suit","pencil","crisp"],
    "athleisure":  ["legging","jogger","track","sweat","sports","athletic","stretch","performance"],
    "elegant":     ["silk","satin","velvet","gown","draped","chiffon","sophisticated","luxe"],
}

# Words that signal comfort-prioritizing items
COMFORT_WORDS = ["stretch","elastic","soft","relaxed","oversized","loose","knit",
                 "jersey","fleece","hoodie","legging","jogger","sweat","cozy",
                 "casual","cotton","easy","breathable"]

# Words that signal style-prioritizing items (form over function)
STYLE_WORDS   = ["tailored","structured","fitted","slim","sharp","crisp","formal",
                 "heels","pencil","blazer","button","collar","pressed","polished"]

# Words that signal bold/statement pieces
BOLD_WORDS    = ["print","pattern","floral","stripe","plaid","graphic","colorful",
                 "sequin","embellished","statement","bold","bright","neon","animal"]

# Words that signal conservative/simple pieces
CONSERVATIVE_WORDS = ["solid","plain","neutral","simple","basic","clean","minimal",
                      "classic","monochrome","understated"]

# ── Color compatibility ──────────────────────────────────────────────────────
COLOR_FAMILIES = {
    "neutral": ["black","white","cream","beige","ivory","grey","gray","charcoal",
                "tan","camel","taupe","off-white","ecru","silver","light grey","dark grey"],
    "earth":   ["brown","rust","terracotta","olive","khaki","sand","chocolate",
                "cognac","burgundy","wine","mustard","amber","ochre"],
    "cool":    ["navy","blue","teal","slate","cobalt","indigo","denim",
                "sky blue","powder blue","steel blue","navy blue"],
    "warm":    ["red","orange","yellow","coral","peach","gold","salmon","tomato"],
    "pastel":  ["blush","lilac","mint","lavender","baby blue","soft pink","mauve",
                "light pink","powder blue"],
    "green":   ["green","olive","sage","forest green","emerald","hunter green",
                "army green","sage green"],
    "dark":    ["black","charcoal","navy","dark green","dark brown","forest green","burgundy"],
}

COMPATIBLE_FAMILIES = [
    ("neutral","neutral"),("neutral","cool"), ("neutral","warm"),
    ("neutral","earth"),  ("neutral","dark"), ("neutral","green"),
    ("earth","earth"),    ("earth","cool"),   ("earth","green"),
    ("cool","cool"),      ("pastel","neutral"),("pastel","pastel"),
    ("dark","neutral"),   ("dark","earth"),   ("green","neutral"),
    ("green","earth"),
]

CLASHING_PATTERNS = [
    ("stripes","plaid"),("floral","stripes"),("floral","plaid"),
    ("print","stripes"),("print","plaid"),("print","floral"),
]


class OutfitScore:
    def __init__(self):
        self.occasion_score   = 0
        self.formality_score  = 0
        self.style_score      = 0
        self.comfort_score    = 0
        self.layering_score   = 0
        self.boldness_score   = 0
        self.color_score      = 0
        self.pattern_score    = 0
        self.preference_score = 0
        self.theme_score      = 0
        self.total            = 0

    def compute_total(self):
        self.total = (
            self.occasion_score   * 0.25 +
            self.formality_score  * 0.20 +
            self.style_score      * 0.18 +
            self.comfort_score    * 0.10 +
            self.layering_score   * 0.08 +
            self.boldness_score   * 0.07 +
            self.color_score      * 0.07 +
            self.preference_score * 0.03 +
            self.pattern_score    * 0.02
        )

    def to_dict(self):
        return {
            "occasion_score":   round(self.occasion_score, 2),
            "formality_score":  round(self.formality_score, 2),
            "style_score":      round(self.style_score, 2),
            "comfort_score":    round(self.comfort_score, 2),
            "layering_score":   round(self.layering_score, 2),
            "boldness_score":   round(self.boldness_score, 2),
            "color_score":      round(self.color_score, 2),
            "preference_score": round(self.preference_score, 2),
            "pattern_score":    round(self.pattern_score, 2),
            "total":            round(self.total, 2),
        }


class Recommender:
    def __init__(self, wardrobe: Wardrobe, preferences: Preferences):
        self.wardrobe         = wardrobe
        self.preferences      = preferences
        self.target_formality = preferences.get_implied_formality()
        self.occasion         = preferences.occasion
        self.theme_profile    = analyze_theme(preferences.event_theme) if preferences.event_theme else {}
        self.weather          = {}
        self.yesterday_ids    = set(preferences.worn_yesterday_ids or [])

        # Pre-compute theme words for direct description matching.
        # These are the raw words from whatever the user typed in the theme box.
        # e.g. "Polka Dot Party" → {"polka", "dot", "party"}
        # We also add item_words from the theme profile if available.
        # Stopwords (common English words) are filtered out.
        STOPWORDS = {"a","an","the","and","or","for","to","in","of","my","party",
                     "night","day","look","style","theme","vibe","inspired"}
        raw_theme = (preferences.event_theme or "").lower()
        raw_words = set(raw_theme.replace("-"," ").replace("_"," ").split())
        meaningful = raw_words - STOPWORDS

        # item_words: keep only SHORT single words (1-2 tokens max) to avoid
        # multi-word phrases like "blue denim" matching unrelated items
        profile_item_words = set()
        for w in self.theme_profile.get("item_words", []):
            w = w.lower().strip()
            tokens = w.split()
            if len(tokens) == 1 and len(w) > 2:
                profile_item_words.add(w)
            elif len(tokens) == 2:
                # Only add 2-word phrases if they are very specific
                # (longer = more specific = less likely to false-match)
                profile_item_words.add(w)

        # keywords: only single-word keywords that are visually descriptive
        profile_keywords = set()
        for kw in self.theme_profile.get("keywords", []):
            kw = kw.lower().strip()
            if " " not in kw and len(kw) > 3 and kw not in STOPWORDS:
                profile_keywords.add(kw)

        self._theme_words = meaningful | profile_item_words | profile_keywords
        # Also store multi-word phrases separately for substring search
        self._theme_phrases = [
            w.lower() for w in self.theme_profile.get("item_words", [])
            if len(w.split()) > 1
        ] + [raw_theme]

    # ── PUBLIC ENTRY POINT ───────────────────────────────────────────────────

    def recommend(self, exclude_ids=None):
        exclude_ids = set(exclude_ids or [])
        warnings    = []
        fully_excluded = exclude_ids | self.yesterday_ids

        candidates = self._get_candidates(fully_excluded, ignore_color_filter=False)

        if not self._can_build_outfit(candidates):
            candidates = self._get_candidates(fully_excluded, ignore_color_filter=True)
            if self._can_build_outfit(candidates):
                warnings.append("Some items were filtered by color preferences. Showing best available.")
            else:
                candidates = self._get_candidates(exclude_ids, ignore_color_filter=True)
                if self.yesterday_ids:
                    warnings.append("Not enough alternatives to avoid yesterday's outfit.")

        if not self._can_build_outfit(candidates):
            return {"selected_items":[],"score_breakdown":{},
                    "warnings":["Not enough items. Upload at least a top/dress, bottom, and shoes."]}

        candidates = self._filter_combo_violations(candidates)
        scored     = {slot: self._score_items(items) for slot, items in candidates.items()}
        outfit     = self._build_outfit(scored)
        outfit_score = self._score_outfit(outfit)
        outfit     = self._add_outerwear(outfit, scored, outfit_score)

        has_shoes = any(i.category == "shoes" for i in outfit)
        has_body  = any(i.category in ["top","bottom","dress"] for i in outfit)
        if not has_shoes or not has_body:
            return {"selected_items":[],"score_breakdown":{},
                    "warnings":["Could not build a valid outfit. Please upload more items."]}

        return {
            "selected_items":  [item.to_dict() for item in outfit],
            "score_breakdown": outfit_score.to_dict(),
            "warnings":        warnings,
        }

    # ── CANDIDATE FILTERING ──────────────────────────────────────────────────

    def _get_candidates(self, exclude_ids, ignore_color_filter=False):
        blocked_cats = OCCASION_BLOCKED_CATEGORIES.get(self.occasion, [])
        candidates = {}
        for slot in ["top","bottom","shoes","outerwear","dress"]:
            if slot in blocked_cats:
                candidates[slot] = []; continue
            items = self.wardrobe.get_by_category(slot)
            items = [i for i in items if i.id not in exclude_ids]
            if not ignore_color_filter:
                items = [i for i in items if not self._is_avoided_color(i)]
            # Formality block — but exempt items that directly match the theme
            # (You asked for a polka dot party outfit: the polka dot top should
            #  not be blocked just because its formality score doesn't fit "event")
            items = [i for i in items if
                     not self._is_formality_blocked(i) or
                     self._direct_description_match(i) > 0]
            candidates[slot] = items
        return candidates

    def _filter_combo_violations(self, candidates):
        avoided_combos = getattr(self.preferences, "avoided_combos", [])
        if not avoided_combos:
            return candidates
        filtered = {}
        for slot, items in candidates.items():
            clean = []
            for item in items:
                ic = item.color.lower()
                violates = False
                for pair in avoided_combos:
                    if len(pair) < 2: continue
                    ca, cb = pair[0].lower(), pair[1].lower()
                    item_is_a = ca in ic or ic in ca
                    item_is_b = cb in ic or ic in cb
                    if not item_is_a and not item_is_b: continue
                    other_color = cb if item_is_a else ca
                    for other_slot, other_items in candidates.items():
                        if other_slot == slot: continue
                        for oi in other_items:
                            oc = oi.color.lower()
                            if other_color in oc or oc in other_color:
                                violates = True; break
                        if violates: break
                    if violates: break
                if not violates:
                    clean.append(item)
            filtered[slot] = clean if clean else items
        return filtered

    def _is_avoided_color(self, item):
        if not self.preferences.avoided_colors: return False
        ic = item.color.lower()
        for avoided in self.preferences.avoided_colors:
            if avoided.lower() in ic or ic in avoided.lower(): return True
        return False

    def _is_formality_blocked(self, item):
        min_f, max_f = OCCASION_FORMALITY_RANGE.get(self.occasion, (0,100))
        item_f = (item.formality - 1) * (100 / 9)
        tolerance = 20
        return item_f < (min_f - tolerance) or item_f > (max_f + tolerance)

    def _can_build_outfit(self, candidates):
        has_dress  = len(candidates.get("dress",[])) > 0
        has_top    = len(candidates.get("top",[])) > 0
        has_bottom = len(candidates.get("bottom",[])) > 0
        has_shoes  = len(candidates.get("shoes",[])) > 0
        return (has_dress or (has_top and has_bottom)) and has_shoes

    # ── ITEM SCORING ─────────────────────────────────────────────────────────

    def _score_items(self, items):
        """
        Scoring priority:
        1. DIRECT DESCRIPTION MATCH against theme words — highest priority
           If any word from the theme input appears in the item description,
           that item jumps to the top regardless of other scores.
        2. Theme profile match (API-analyzed keywords, colors, item_words)
        3. All other preference sliders as base score
        """
        has_theme = bool(getattr(self, "_theme_words", None) or
                         (self.theme_profile and (
                            self.theme_profile.get("item_words") or
                            self.theme_profile.get("keywords") or
                            self.theme_profile.get("colors"))))

        scored = []
        for item in items:
            base = (
                self._occasion_score(item)        * 0.70 +
                self._formality_score(item)       * 0.60 +
                self._style_score(item)           * 0.55 +
                self._comfort_score(item)         * 0.40 +
                self._boldness_score(item)        * 0.35 +
                self._weather_score(item)         * 0.30 +
                self._preferred_color_bonus(item) * 0.40
            )

            if has_theme:
                # ── Direct description match — THE most important signal ──────
                # If theme words appear literally in the item description,
                # give a massive boost that overrides everything else.
                direct_bonus = self._direct_description_match(item)

                # ── Theme profile match — secondary signal ────────────────────
                raw_theme = theme_score_item(item, self.theme_profile)

                s = direct_bonus + raw_theme * 2.0 + base
            else:
                s = base

            s += random.uniform(0, 0.3)
            scored.append((s, item.id, item))

        return [(s, item) for s, _, item in sorted(scored, key=lambda x: x[0], reverse=True)]

    def _direct_description_match(self, item) -> float:
        """
        Directly scans the item description and color for words from the theme input.
        This is the most reliable signal because it bypasses the API entirely.

        Examples:
        - Theme "polka dot party" + item desc "white polka dot top" → +500 (huge boost)
        - Theme "denim" + item desc "dark wash denim jeans" → +500
        - Theme "floral garden" + item desc "floral wrap dress" → +500
        - Theme "red dress" + item color "red" → +300 (color match)

        Returns 0 if no match.
        """
        theme_words = getattr(self, "_theme_words", set())
        if not theme_words:
            return 0

        item_desc  = (getattr(item, "description", "") or "").lower()
        item_color = (item.color or "").lower()
        item_pat   = (item.pattern or "").lower()

        # Tokenize description into words
        desc_words = set(item_desc.replace("-", " ").replace(",", " ").split())
        color_words = set(item_color.replace("-", " ").split())
        pat_words   = set(item_pat.replace("-", " ").split())

        all_item_words = desc_words | color_words | pat_words

        # Check for overlap between theme words and item words
        overlap = theme_words & all_item_words

        if overlap:
            # More matching words = higher boost
            # Even one match gives a massive 500-point boost
            return 500 * len(overlap)

        # Also check for substring matches
        for tw in theme_words:
            if len(tw) > 3 and tw in item_desc:
                return 400

        # Check multi-word phrases (e.g. "polka dot", "dark denim")
        theme_phrases = getattr(self, "_theme_phrases", [])
        for phrase in theme_phrases:
            if len(phrase) > 4 and phrase in item_desc:
                return 450

        return 0

    # ── INDIVIDUAL ITEM SCORES ────────────────────────────────────────────────

    def _occasion_score(self, item):
        """How well does this item fit the chosen occasion?"""
        min_f, max_f = OCCASION_FORMALITY_RANGE.get(self.occasion, (0,100))
        item_f = (item.formality - 1) * (100 / 9)

        formality_fit = 100 if min_f <= item_f <= max_f else max(0, 100 - max(0, item_f - max_f, min_f - item_f) * 2.5)

        occasion_styles = set(OCCASION_STYLE_BOOST.get(self.occasion, []))
        item_styles = set(s.lower() for s in item.styles)
        style_fit = min(100, len(occasion_styles & item_styles) * 35)

        return formality_fit * 0.65 + style_fit * 0.35

    def _formality_score(self, item):
        """How close is this item's formality to the user's slider?"""
        item_f = (item.formality - 1) * (100 / 9)
        diff = abs(item_f - self.target_formality)
        return 100 * math.exp(-(diff ** 2) / (2 * 28 ** 2))

    def _style_score(self, item):
        """
        Fuzzy style matching — uses both style tags AND description words.
        Related styles get partial credit (e.g. 'romantic' counts for 'bohemian').
        """
        if not self.preferences.styles:
            return 50

        desc = (getattr(item, "description", "") or "").lower()
        item_tags = set(s.lower() for s in (item.styles or []))
        score = 0
        max_possible = len(self.preferences.styles) * 100

        for user_style in self.preferences.styles:
            user_style = user_style.lower()
            family = STYLE_FAMILIES.get(user_style, {user_style})

            # Exact tag match → full score
            if user_style in item_tags:
                score += 100
                continue

            # Related tag match → partial score
            overlap = item_tags & family
            if overlap:
                score += 60
                continue

            # Description word match → partial score
            desc_signals = DESC_STYLE_SIGNALS.get(user_style, [])
            if any(word in desc for word in desc_signals):
                score += 40
                continue

            # No match at all
            score += 0

        return (score / max_possible * 100) if max_possible > 0 else 50

    def _comfort_score(self, item):
        """
        Comfort↔Style slider (0=comfort, 100=style).
        At 0: reward comfortable/practical items, penalize restrictive ones.
        At 100: reward polished/styled items, penalize overly casual ones.
        At 50: neutral.
        """
        slider = self.preferences.comfort_vs_style  # 0-100
        if slider == 50:
            return 50  # neutral — no effect

        desc = (getattr(item, "description", "") or "").lower()
        item_words = set(desc.replace("-"," ").split())

        comfort_signal = len(item_words & set(COMFORT_WORDS))
        style_signal   = len(item_words & set(STYLE_WORDS))

        if slider < 50:
            # User wants comfort: reward comfort signals, penalize style signals
            weight = (50 - slider) / 50  # 0-1 scale
            score = 50 + (comfort_signal * 15 - style_signal * 10) * weight
        else:
            # User wants style: reward style signals, penalize comfort signals
            weight = (slider - 50) / 50  # 0-1 scale
            score = 50 + (style_signal * 15 - comfort_signal * 10) * weight

        return max(0, min(100, score))

    def _boldness_score(self, item):
        """
        Conservative↔Bold slider (0=conservative, 100=bold).
        At 0: reward solid neutrals, penalize loud patterns/colors.
        At 100: reward prints, patterns, statement pieces.
        At 50: neutral.
        """
        slider = self.preferences.boldness  # 0-100
        if slider == 50:
            return 50

        desc    = (getattr(item, "description", "") or "").lower()
        color   = (item.color or "").lower()
        pattern = (item.pattern or "solid").lower()

        desc_words = set(desc.replace("-"," ").split())
        bold_signal  = len(desc_words & set(BOLD_WORDS))
        cons_signal  = len(desc_words & set(CONSERVATIVE_WORDS))

        # Pattern itself is a strong bold signal
        if pattern != "solid":
            bold_signal += 2
        else:
            cons_signal += 1

        # Color family: warm/bright = bold, neutral = conservative
        color_family = self._get_color_family(color)
        if color_family in ["warm","pastel"]:
            bold_signal += 1
        elif color_family in ["neutral","dark"]:
            cons_signal += 1

        if slider < 50:
            weight = (50 - slider) / 50
            score = 50 + (cons_signal * 15 - bold_signal * 10) * weight
        else:
            weight = (slider - 50) / 50
            score = 50 + (bold_signal * 15 - cons_signal * 10) * weight

        return max(0, min(100, score))

    def _layering_score(self, item):
        """
        Minimal↔Layered slider (0=minimal, 100=layered).
        Controls whether outerwear and layering pieces are rewarded.
        Called at outfit level, not item level.
        """
        slider = self.preferences.layering  # 0-100
        cat = item.category

        if cat == "outerwear":
            if slider >= 60:
                return 80   # user wants layers → outerwear is welcome
            elif slider <= 30:
                return 20   # user wants minimal → outerwear penalized
            else:
                return 50   # neutral

        # For non-outerwear items: layered items like cardigans/blazers
        desc = (getattr(item, "description", "") or "").lower()
        layer_words = {"cardigan","blazer","jacket","vest","layer","over","wrap","kimono"}
        if any(w in desc for w in layer_words):
            if slider >= 60: return 70
            if slider <= 30: return 30
        return 50

    def _weather_score(self, item):
        return weather_score_item(item, self.weather, self.preferences.weather_sensitivity)

    def _preferred_color_bonus(self, item):
        ic = item.color.lower()
        for preferred in self.preferences.preferred_colors:
            if preferred.lower() in ic or ic in preferred.lower():
                return 20
        return 0

    # ── BUILD OUTFIT ─────────────────────────────────────────────────────────

    def _build_outfit(self, scored):
        dresses = scored.get("dress", [])
        tops    = scored.get("top", [])
        bottoms = scored.get("bottom", [])
        shoes   = scored.get("shoes", [])
        outfit  = []

        best_dress_score   = dresses[0][0] if dresses else -float("inf")
        separates_possible = bool(tops and bottoms)
        best_sep_score     = ((tops[0][0] + bottoms[0][0]) / 2) if separates_possible else -float("inf")

        if dresses and best_dress_score >= best_sep_score:
            outfit.append(dresses[0][1])
        elif separates_possible:
            outfit.append(tops[0][1])
            outfit.append(bottoms[0][1])
        elif dresses:
            outfit.append(dresses[0][1])
        else:
            if tops:    outfit.append(tops[0][1])
            if bottoms: outfit.append(bottoms[0][1])

        if shoes:
            outfit.append(shoes[0][1])

        return outfit

    # ── OUTFIT-LEVEL SCORING ─────────────────────────────────────────────────

    def _score_outfit(self, outfit):
        score = OutfitScore()
        if not outfit: return score

        score.occasion_score   = sum(self._occasion_score(i)  for i in outfit) / len(outfit)
        score.formality_score  = sum(self._formality_score(i) for i in outfit) / len(outfit)
        score.style_score      = sum(self._style_score(i)     for i in outfit) / len(outfit)
        score.comfort_score    = sum(self._comfort_score(i)   for i in outfit) / len(outfit)
        score.boldness_score   = sum(self._boldness_score(i)  for i in outfit) / len(outfit)
        score.layering_score   = sum(self._layering_score(i)  for i in outfit) / len(outfit)
        score.color_score      = self._color_harmony_score(outfit)
        score.pattern_score    = self._pattern_score(outfit)
        score.preference_score = self._preference_color_score(outfit)
        score.compute_total()

        # Combo penalty after total
        combo_pen = self._combo_penalty(outfit)
        score.total = max(0, score.total - combo_pen * 15)
        return score

    def _color_harmony_score(self, outfit):
        if len(outfit) < 2: return 100
        pairs = [(outfit[i], outfit[j]) for i in range(len(outfit)) for j in range(i+1, len(outfit))]
        compatible = sum(1 for a,b in pairs if self._colors_compatible(a.color, b.color))
        return (compatible / len(pairs)) * 100

    def _colors_compatible(self, ca, cb):
        fa, fb = self._get_color_family(ca), self._get_color_family(cb)
        if fa == "neutral" or fb == "neutral": return True
        return (fa,fb) in COMPATIBLE_FAMILIES or (fb,fa) in COMPATIBLE_FAMILIES

    def _get_color_family(self, color):
        color = color.lower()
        for family, colors in COLOR_FAMILIES.items():
            if any(c in color or color in c for c in colors):
                return family
        return "neutral"

    def _pattern_score(self, outfit):
        patterns = [i.pattern.lower() for i in outfit]
        total_pairs = max(1, len(patterns)*(len(patterns)-1)/2)
        clashes = sum(
            1 for i in range(len(patterns)) for j in range(i+1, len(patterns))
            if (patterns[i],patterns[j]) in CLASHING_PATTERNS
            or (patterns[j],patterns[i]) in CLASHING_PATTERNS
        )
        return max(0, 100 - (clashes/total_pairs)*100)

    def _preference_color_score(self, outfit):
        score = 50
        for item in outfit:
            c = item.color.lower()
            for p in self.preferences.preferred_colors:
                if p.lower() in c or c in p.lower(): score += 10
            for a in self.preferences.avoided_colors:
                if a.lower() in c or c in a.lower(): score -= 25
        return max(0, min(100, score))

    def _combo_penalty(self, outfit):
        avoided_combos = getattr(self.preferences, "avoided_combos", [])
        if not avoided_combos: return 0
        outfit_colors = [i.color.lower() for i in outfit]
        penalty = 0
        for pair in avoided_combos:
            if len(pair) < 2: continue
            ca, cb = pair[0].lower(), pair[1].lower()
            has_a = any(ca in oc or oc in ca for oc in outfit_colors)
            has_b = any(cb in oc or oc in cb for oc in outfit_colors)
            if has_a and has_b: penalty += 1
        return penalty

    # ── OUTERWEAR ────────────────────────────────────────────────────────────

    def _add_outerwear(self, outfit, scored, outfit_score):
        """
        Add outerwear only if:
        - Occasion allows it
        - Layering slider is not minimal (>= 25)
        - It doesn't hurt the score
        """
        if self.occasion == "active":
            return outfit

        # If user wants minimal layers, skip outerwear entirely
        if self.preferences.layering < 25:
            return outfit

        candidates = scored.get("outerwear", [])
        if not candidates: return outfit

        best = candidates[0][1]
        trial = outfit + [best]
        trial_score = self._score_outfit(trial)
        if trial_score.total >= outfit_score.total - 3:
            return trial
        return outfit



