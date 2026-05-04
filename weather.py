# weather.py
# Fetches real current weather using Open-Meteo — completely free, no API key needed.
# Falls back to season-based estimation if location is unavailable or network fails.
#
# Called from app.py when the user requests a recommendation.
# The frontend sends the user's lat/lon (obtained via browser geolocation).

import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# WMO weather codes -> human readable condition
# https://open-meteo.com/en/docs#weathervariables
WMO_CONDITIONS = {
    0:  "clear",
    1:  "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    80: "light showers", 81: "showers", 82: "heavy showers",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


def get_weather(lat: float, lon: float) -> dict:
    """
    Fetches current weather for a given location.
    Falls back to seasonal estimation if network is unavailable.
    """
    if REQUESTS_AVAILABLE and lat is not None and lon is not None:
        try:
            result = _fetch_live_weather(lat, lon)
            if result:
                return result
        except Exception as e:
            print(f"[weather] API call failed ({e}), using seasonal estimate")

    # Fallback: estimate from current month + hemisphere
    return _estimate_from_season(lat, had_location=(lat is not None))


def _fetch_live_weather(lat: float, lon: float) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,precipitation,windspeed_10m,weathercode"
        f"&temperature_unit=fahrenheit"
        f"&wind_speed_unit=mph"
        f"&timezone=auto"
    )

    response = requests.get(url, timeout=5)
    if response.status_code != 200:
        return None

    data     = response.json()
    current  = data.get("current", {})

    temp_f   = float(current.get("temperature_2m", 65))
    temp_c   = round((temp_f - 32) * 5 / 9, 1)
    precip   = float(current.get("precipitation", 0))
    wind_mph = float(current.get("windspeed_10m", 0))
    wmo_code = int(current.get("weathercode", 0))

    condition   = WMO_CONDITIONS.get(wmo_code, "partly cloudy")
    is_raining  = precip > 0.1 or wmo_code in [51,53,55,61,63,65,80,81,82,95,96,99]
    is_cold     = temp_f < 50
    is_hot      = temp_f > 77
    is_mild     = not is_cold and not is_hot
    is_windy    = wind_mph > 15

    summary = _build_summary(temp_f, condition, is_raining, is_windy)

    import datetime
    month = datetime.datetime.now().month
    if month in [12,1,2]:   cur_season = "winter"
    elif month in [3,4,5]:  cur_season = "spring"
    elif month in [6,7,8]:  cur_season = "summer"
    else:                    cur_season = "fall"

    return {
        "temp_f":     round(temp_f, 1),
        "temp_c":     temp_c,
        "condition":  condition,
        "is_raining": is_raining,
        "is_cold":    is_cold,
        "is_hot":     is_hot,
        "is_mild":    is_mild,
        "is_windy":   is_windy,
        "wind_mph":   round(wind_mph, 1),
        "season":     cur_season,
        "source":     "live",
        "summary":    summary,
    }


def _estimate_from_season(lat: float = None, had_location: bool = False) -> dict:
    """
    Falls back to month-based season estimation.
    Uses hemisphere (lat > 0 = northern) to flip seasons correctly.
    had_location: True if we had coordinates but the API failed.
    """
    month = datetime.datetime.now().month
    northern = lat is None or lat >= 0

    if northern:
        if month in [12, 1, 2]:   season = "winter"
        elif month in [3, 4, 5]:  season = "spring"
        elif month in [6, 7, 8]:  season = "summer"
        else:                      season = "fall"
    else:
        # Southern hemisphere — flip seasons
        if month in [12, 1, 2]:   season = "summer"
        elif month in [3, 4, 5]:  season = "fall"
        elif month in [6, 7, 8]:  season = "winter"
        else:                      season = "spring"

    season_temps = {
        "winter": 35, "spring": 58, "summer": 80, "fall": 55
    }
    temp_f   = season_temps[season]
    temp_c   = round((temp_f - 32) * 5 / 9, 1)
    is_cold  = temp_f < 50
    is_hot   = temp_f > 77
    is_mild  = not is_cold and not is_hot

    return {
        "temp_f":     temp_f,
        "temp_c":     temp_c,
        "condition":  f"typical {season}",
        "is_raining": False,
        "is_cold":    is_cold,
        "is_hot":     is_hot,
        "is_mild":    is_mild,
        "is_windy":   False,
        "wind_mph":   0,
        "season":     season,
        "source":     "estimated",
        "summary":    f"Typical {season} weather ({temp_f}°F / {temp_c}°C)" + (" — live weather unavailable." if had_location else " — location not available."),
    }


def _build_summary(temp_f, condition, is_raining, is_windy):
    parts = [f"{temp_f:.0f}°F", condition]
    if is_windy:
        parts.append("windy")
    return ", ".join(parts)


def weather_score_item(item, weather: dict, sensitivity: int) -> float:
    """
    Scores a clothing item against real weather conditions.
    Uses description, category, color, season tags, and formality to judge.
    sensitivity: 0-100 (from user slider). 0 = ignore completely.
    Returns -60 to +35.
    """
    if sensitivity == 0 or not weather:
        return 0

    weight = sensitivity / 100
    score  = 0

    desc    = (getattr(item, "description", "") or "").lower()
    color   = (getattr(item, "color", "") or "").lower()
    cat     = getattr(item, "category", "")
    form    = getattr(item, "formality", 5)
    seasons = getattr(item, "season", ["all"])

    # ── Season tag check (from vision analysis) ──────────────────────────────
    current_season = weather.get("season", "")
    if current_season and "all" not in seasons:
        if current_season in seasons:
            score += 15 * weight   # item is tagged for this season
        else:
            score -= 20 * weight   # item is tagged for a different season

    # ── Warm/cold item vocabulary ─────────────────────────────────────────────
    warm_words  = {"wool","knit","sweater","coat","jacket","hoodie","sweatshirt",
                   "fleece","turtleneck","thermal","puffer","parka","cardigan","chunky"}
    light_words = {"linen","cotton","tank","sleeveless","crop","shorts","short",
                   "sandal","sundress","spaghetti","strapless","thin","sheer","silk chiffon"}
    shoe_cold   = {"boot","ankle boot","chelsea","loafer","oxford","sneaker"}
    shoe_hot    = {"sandal","slide","mule","flip","espadrille","open toe"}

    desc_set = set(desc.replace("-"," ").split())

    # ── Temperature scoring ──────────────────────────────────────────────────
    if weather["is_cold"]:
        if cat == "outerwear":
            score += 30 * weight   # outerwear is great when cold
        if desc_set & warm_words:
            score += 22 * weight   # warm fabric/style in description
        if desc_set & light_words:
            score -= 35 * weight   # summer items in cold
        if cat == "shoes":
            if desc_set & shoe_cold:
                score += 10 * weight
            if desc_set & shoe_hot:
                score -= 30 * weight
        # Formality proxy: in cold weather, higher formality often = heavier fabric
        if form >= 7:
            score += 5 * weight

    elif weather["is_hot"]:
        if desc_set & light_words:
            score += 22 * weight   # light/breathable
        if desc_set & warm_words:
            score -= 30 * weight   # heavy fabric in heat
        if cat == "outerwear" and form >= 5:
            score -= 28 * weight   # heavy outerwear in heat
        if cat == "shoes":
            if desc_set & shoe_hot:
                score += 12 * weight
            if "boot" in desc and "ankle" not in desc:
                score -= 15 * weight
        # Very hot: penalize dark colors (absorb heat)
        if weather.get("temp_f", 70) > 85:
            if any(c in color for c in ["black","dark","navy"]):
                score -= 10 * weight

    else:  # mild
        if cat == "outerwear":
            score += 10 * weight   # light layer is useful in mild weather
        if desc_set & {"cardigan","blazer","light jacket","trench"}:
            score += 8 * weight

    # ── Rain scoring ─────────────────────────────────────────────────────────
    if weather["is_raining"]:
        delicate = {"suede","velvet","silk","satin","cashmere"}
        if desc_set & delicate:
            score -= 22 * weight
        if cat == "shoes":
            if desc_set & {"suede","canvas","open","sandal","slide"}:
                score -= 28 * weight
            if desc_set & {"boot","waterproof","rubber","chelsea"}:
                score += 18 * weight
        if "white" in color:
            score -= 12 * weight   # white in rain = risky

    # ── Wind scoring ─────────────────────────────────────────────────────────
    if weather["is_windy"]:
        if cat in ["dress","bottom"]:
            if desc_set & {"midi","maxi","flowy","pleated","wide","skirt","flare"}:
                score -= 18 * weight

    return max(-60, min(35, score))


if __name__ == "__main__":
    print("Testing weather fetch (New Haven, CT):")
    w = get_weather(41.31, -72.92)
    for k, v in w.items():
        print(f"  {k}: {v}")
