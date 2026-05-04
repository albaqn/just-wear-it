# theme_analyzer.py
import os, json, re

try:
    import anthropic
    _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY","YOUR_API_KEY_HERE"))
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    _client = None

MODEL = "claude-haiku-4-5-20251001"
_theme_cache = {}


def analyze_theme(theme: str) -> dict:
    if not theme or not theme.strip():
        return _empty_theme()
    cache_key = theme.strip().lower()
    if cache_key in _theme_cache:
        return _theme_cache[cache_key]
    if not API_AVAILABLE or not _client:
        result = _offline_profile(cache_key)
    else:
        try:
            result = _call_api(theme.strip())
        except Exception as e:
            result = _offline_profile(cache_key)
            result["error"] = str(e)
    _theme_cache[cache_key] = result
    return result


def _call_api(theme: str) -> dict:
    prompt = f"""
You are a fashion and visual culture expert. A user wants to dress inspired by: "{theme}"

This could be: a Pinterest aesthetic, movie, TV show, celebrity, historical era,
fictional character, pattern style (polka dots, stripes, denim), fabric style,
or any cultural reference.

If the theme is a PATTERN OR FABRIC (e.g. "denim", "polka dots", "stripes", "floral"):
- Set patterns to include that pattern
- Add the pattern/fabric name explicitly in keywords AND in item_words
- item_words should include what you would find in a clothing item description

If the theme is a PERSON, MOVIE, or AESTHETIC:
- Think about their signature colors, patterns, and silhouettes
- Be specific about what garment types they wear

Respond ONLY with JSON:
{{
  "colors": ["4-6 specific colors typical for this aesthetic"],
  "patterns": ["1-3 patterns from: solid, stripes, plaid, floral, print, other"],
  "formality": integer 1-10,
  "silhouettes": ["2-4 words about shapes/fits"],
  "fabrics": ["2-3 typical fabrics or textures"],
  "avoid": ["3-4 things that clash with this aesthetic"],
  "keywords": ["5-8 style/visual keywords — include pattern and fabric names if relevant"],
  "item_words": ["4-8 words that would appear in a clothing item DESCRIPTION for this aesthetic, e.g. for denim: denim, jeans, chambray, jean; for polka dots: polka, dot, spotted, print"],
  "summary": "2-3 sentences describing what wearing this aesthetic looks like."
}}
"""
    response = _client.messages.create(
        model=MODEL, max_tokens=500,
        messages=[{"role":"user","content":prompt}]
    )
    return _parse(_clean_json(response.content[0].text.strip()))


def _clean_json(raw):
    try: return json.loads(raw)
    except:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return {}


def _parse(data: dict) -> dict:
    return {
        "colors":      [str(c) for c in data.get("colors",[])],
        "patterns":    [str(p) for p in data.get("patterns",[])],
        "formality":   max(1,min(10,int(data.get("formality",5)))),
        "silhouettes": [str(s) for s in data.get("silhouettes",[])],
        "fabrics":     [str(f) for f in data.get("fabrics",[])],
        "avoid":       [str(a) for a in data.get("avoid",[])],
        "keywords":    [str(k) for k in data.get("keywords",[])],
        "item_words":  [str(w) for w in data.get("item_words",[])],
        "summary":     str(data.get("summary","")),
        "error":       None,
    }


def _empty_theme() -> dict:
    return {"colors":[],"patterns":[],"formality":5,"silhouettes":[],"fabrics":[],
            "avoid":[],"keywords":[],"item_words":[],"summary":"","error":None}


_OFFLINE_PROFILES = {
    "garden party":   {"colors":["sage green","cream","blush","white","lilac"],"patterns":["floral","solid"],"formality":6,"silhouettes":["flowy","midi","relaxed"],"fabrics":["chiffon","cotton","linen"],"avoid":["dark colors","heavy boots","athleisure"],"keywords":["romantic","feminine","fresh","effortless","spring"],"item_words":["floral","dress","midi","linen","blouse","sundress"],"summary":"Light flowy pieces in soft florals and pastels."},
    "old money":      {"colors":["navy","cream","camel","forest green","burgundy"],"patterns":["plaid","solid","stripes"],"formality":8,"silhouettes":["tailored","structured","classic"],"fabrics":["wool","cashmere","cotton"],"avoid":["logos","neon","athleisure"],"keywords":["classic","preppy","refined","understated","timeless"],"item_words":["blazer","loafer","trouser","polo","cashmere","oxford"],"summary":"Quiet luxury with tailored pieces in rich neutrals."},
    "coastal grandmother":{"colors":["white","cream","navy","sky blue","sand"],"patterns":["solid","stripes"],"formality":4,"silhouettes":["relaxed","wide leg","loose"],"fabrics":["linen","cotton"],"avoid":["bright colors","tight fits"],"keywords":["relaxed","coastal","airy","natural"],"item_words":["linen","wide","trouser","blouse","stripe","sandal"],"summary":"Breezy linen in ocean neutrals."},
    "cottagecore":    {"colors":["cream","sage","dusty rose","brown","white"],"patterns":["floral","print","solid"],"formality":3,"silhouettes":["flowy","oversized","puff sleeves"],"fabrics":["cotton","linen","crochet"],"avoid":["synthetic","neon","corporate"],"keywords":["whimsical","nature","vintage","handmade","pastoral"],"item_words":["floral","cottage","prairie","puff","sleeve","crochet","lace"],"summary":"Romantic nature-inspired flowy pieces."},
    "dark academia":  {"colors":["brown","dark green","burgundy","black","cream","mustard"],"patterns":["plaid","solid","stripes"],"formality":7,"silhouettes":["layered","structured","classic"],"fabrics":["wool","tweed","corduroy"],"avoid":["bright colors","athleisure","beachwear"],"keywords":["intellectual","moody","vintage","literary","autumnal"],"item_words":["plaid","tweed","blazer","turtleneck","oxford","corduroy","loafer"],"summary":"Moody autumnal layers in earth tones."},
    "denim":          {"colors":["light blue","dark blue","medium blue","indigo","white","black"],"patterns":["solid"],"formality":3,"silhouettes":["relaxed","casual","classic"],"fabrics":["denim","cotton"],"avoid":["formal","delicate fabrics","silk"],"keywords":["casual","denim","jeans","classic","americana"],"item_words":["denim","jeans","jean","chambray","indigo","blue denim","dark denim","light denim"],"summary":"Classic denim pieces in various washes. Jeans, denim jackets, chambray shirts."},
    "polka dots":     {"colors":["white","black","red","navy","cream"],"patterns":["print"],"formality":4,"silhouettes":["classic","feminine","retro"],"fabrics":["cotton","silk","chiffon"],"avoid":["solid only","plain","minimalist"],"keywords":["polka","dot","playful","retro","print","spotted"],"item_words":["polka","dot","spotted","print","dotted"],"summary":"Playful polka dot prints on classic silhouettes."},
    "floral":         {"colors":["white","cream","pink","sage","yellow","blush"],"patterns":["floral"],"formality":5,"silhouettes":["flowy","feminine","midi"],"fabrics":["chiffon","cotton","silk"],"avoid":["solid corporate","dark heavy"],"keywords":["floral","botanical","feminine","spring","bloom"],"item_words":["floral","flower","bloom","botanical","garden","rose","daisy"],"summary":"Floral prints across feminine and flowing silhouettes."},
    "stripes":        {"colors":["navy","white","cream","black","red","blue"],"patterns":["stripes"],"formality":4,"silhouettes":["classic","nautical","relaxed"],"fabrics":["cotton","linen","jersey"],"avoid":["plaid","heavy print"],"keywords":["stripe","nautical","classic","preppy","clean"],"item_words":["stripe","striped","stripes","nautical","breton","pinstripe"],"summary":"Classic stripe patterns in nautical or preppy style."},
    "70s":            {"colors":["burnt orange","mustard","brown","rust","cream","olive"],"patterns":["print","floral","stripes"],"formality":4,"silhouettes":["flared","wide leg","oversized"],"fabrics":["suede","corduroy","denim"],"avoid":["minimalist","corporate","structured"],"keywords":["retro","groovy","bold","funky","vintage"],"item_words":["flared","wide","bell","corduroy","suede","retro","vintage"],"summary":"Earthy retro tones with flared silhouettes."},
    "black tie":      {"colors":["black","navy","champagne","silver","burgundy"],"patterns":["solid"],"formality":10,"silhouettes":["floor length","fitted","elegant"],"fabrics":["silk","satin","velvet"],"avoid":["casual","sneakers","denim"],"keywords":["elegant","formal","glamorous","sophisticated"],"item_words":["gown","tuxedo","satin","velvet","silk","formal","floor","evening"],"summary":"Maximum formality in floor-length or tuxedo pieces."},
    "the great gatsby":{"colors":["gold","cream","white","black","champagne","blush"],"patterns":["solid","print"],"formality":9,"silhouettes":["drop waist","art deco","embellished"],"fabrics":["silk","beaded","feathers"],"avoid":["casual","modern minimalism"],"keywords":["glamorous","roaring 20s","opulent","jazz age","beaded"],"item_words":["beaded","fringe","feather","drop","waist","1920","gatsby","pearl","headband"],"summary":"1920s opulence with beaded embellishment and art deco details."},
    "audrey hepburn": {"colors":["black","white","cream","navy","red"],"patterns":["solid"],"formality":8,"silhouettes":["slim","classic","elegant","fitted"],"fabrics":["silk","cotton","wool"],"avoid":["flashy prints","oversized","trendy"],"keywords":["chic","timeless","minimalist","elegant","classic"],"item_words":["little black","cigarette","trouser","ballet","flat","fitted","slim","classic"],"summary":"Understated chic with clean lines and classic silhouettes."},
    "euphoria":       {"colors":["holographic","purple","blue","pink","gold","black"],"patterns":["print","bold"],"formality":3,"silhouettes":["crop","bodycon","cutout","dramatic"],"fabrics":["vinyl","mesh","sequins"],"avoid":["conservative","muted","traditional"],"keywords":["bold","maximalist","Y2K","glam","expressive","glitter"],"item_words":["crop","bodycon","cutout","sequin","mesh","vinyl","glitter","holographic"],"summary":"High-impact maximalist with bold color and body-conscious silhouettes."},
    "succession":     {"colors":["navy","grey","camel","white","black","brown"],"patterns":["solid","fine stripe"],"formality":9,"silhouettes":["tailored","structured","minimal","sharp"],"fabrics":["cashmere","wool","silk"],"avoid":["logos","trendy","athleisure","bright colors"],"keywords":["power dressing","quiet luxury","corporate","understated","expensive"],"item_words":["tailored","structured","blazer","cashmere","wool","trouser","minimal","sharp"],"summary":"Ultra-refined power dressing in muted neutrals."},
}


def _offline_profile(theme: str) -> dict:
    for key, profile in _OFFLINE_PROFILES.items():
        if key in theme:
            return {**profile, "error":"offline profile"}
        if any(kw in theme for kw in profile.get("keywords",[])):
            return {**profile, "error":"offline keyword match"}
    return {**_empty_theme(),"keywords":[theme],"item_words":[theme],"summary":f"Inspired by: {theme}","error":"no profile found"}


def theme_score_item(item, theme_profile: dict) -> float:
    """
    Scores an item against a theme. Reads ALL item fields including description.
    This ensures items labeled "denim jeans" or "polka dot tee" match the right themes.
    Returns -60 to +60.
    """
    if not theme_profile or not any([
        theme_profile.get("colors"), theme_profile.get("keywords"),
        theme_profile.get("patterns"), theme_profile.get("item_words"),
    ]):
        return 0

    score = 0
    item_color   = (item.color or "").lower()
    item_styles  = set(s.lower() for s in (item.styles or []))
    item_pattern = (item.pattern or "").lower()
    item_desc    = (getattr(item, "description", "") or "").lower()

    # Tokenize description into individual words for precise matching
    desc_words = set(item_desc.replace("-"," ").split())
    # Full item text blob for substring matching
    item_text = " ".join([item_color, item_pattern, item_desc] + list(item_styles))

    # ── 1. item_words direct match (new field) ───────────────────────────────
    # These are words the theme generator says would appear in item descriptions
    # e.g. denim theme → item_words: ["denim","jeans","chambray"]
    item_words = [w.lower() for w in theme_profile.get("item_words", [])]
    for iw in item_words:
        iw_tokens = iw.split()
        if all(tok in item_text for tok in iw_tokens):
            score += 30  # strongest signal — direct description match
            break

    # ── 2. Color match ────────────────────────────────────────────────────────
    for tc in theme_profile.get("colors", []):
        tc_lower = tc.lower()
        if tc_lower in item_color or item_color in tc_lower or tc_lower in item_desc:
            score += 20
            break

    # ── 3. Pattern match ─────────────────────────────────────────────────────
    theme_patterns = [p.lower() for p in theme_profile.get("patterns", [])]
    if item_pattern in theme_patterns:
        score += 15
    # Check description for pattern words
    pattern_vocab = ["stripe","stripes","plaid","check","floral","flower","polka","dot",
                     "animal","leopard","zebra","houndstooth","paisley","abstract","print",
                     "denim","chambray","lace","crochet","tweed","corduroy","velvet"]
    theme_text = " ".join(
        theme_profile.get("keywords",[]) + theme_profile.get("item_words",[]) +
        [theme_profile.get("summary","")]
    ).lower()
    for pw in pattern_vocab:
        if pw in item_desc and pw in theme_text:
            score += 18
            break

    # ── 4. Keyword/style overlap ──────────────────────────────────────────────
    theme_kw = set(k.lower() for k in theme_profile.get("keywords", []))
    score += len(item_styles & theme_kw) * 10
    score += len(desc_words & theme_kw) * 8

    # ── 5. Formality match ────────────────────────────────────────────────────
    theme_f = theme_profile.get("formality", 5)
    diff = abs(item.formality - theme_f)
    if diff <= 1:   score += 12
    elif diff <= 3: score += 4
    elif diff >= 5: score -= 20

    # ── 6. Avoid list ─────────────────────────────────────────────────────────
    for avoid in [a.lower() for a in theme_profile.get("avoid", [])]:
        avoid_tokens = avoid.split()
        if any(tok in item_text for tok in avoid_tokens):
            score -= 20
            break

    return max(-60, min(60, score))


if __name__ == "__main__":
    tests = ["denim","polka dots","garden party","Audrey Hepburn","dark academia"]
    for t in tests:
        print(f"\n{'='*40}")
        p = analyze_theme(t)
        print(f"THEME: {t}")
        print(f"item_words: {p.get('item_words')}")
        print(f"keywords:   {p.get('keywords')}")
