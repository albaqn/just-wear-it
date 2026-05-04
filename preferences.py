# preferences.py
class Preferences:
    VALID_STYLES = ["minimalist","classic","bohemian","streetwear","preppy","romantic","edgy","business","athleisure","elegant"]
    VALID_OCCASIONS = ["office","casual","dinner","event","active","travel"]
    OCCASION_FORMALITY = {"office":70,"casual":25,"dinner":80,"event":90,"active":10,"travel":35}

    def __init__(self):
        self.styles = []
        self.style_today = ""
        self.occasion = "casual"
        self.event_theme = ""
        self.formality = 50
        self.comfort_vs_style = 50
        self.layering = 30
        self.boldness = 40
        self.weather_sensitivity = 50
        self.preferred_colors = []
        self.avoided_colors = []
        self.worn_yesterday_ids = []
        self.avoided_combos = []

    def set_from_dict(self, data):
        raw_styles = data.get("styles", [])
        self.styles = [s.lower() for s in raw_styles if s.lower() in self.VALID_STYLES]
        self.style_today = str(data.get("style_today", "")).strip()[:200]
        raw_occasion = data.get("occasion", "casual").lower()
        self.occasion = raw_occasion if raw_occasion in self.VALID_OCCASIONS else "casual"
        self.event_theme = str(data.get("event_theme", "")).strip()[:200]
        self.formality           = self._clamp(data.get("formality", 50))
        self.comfort_vs_style    = self._clamp(data.get("comfort_vs_style", 50))
        self.layering            = self._clamp(data.get("layering", 30))
        self.boldness            = self._clamp(data.get("boldness", 40))
        self.weather_sensitivity = self._clamp(data.get("weather_sensitivity", 50))
        self.preferred_colors    = data.get("preferred_colors", [])
        self.avoided_colors      = data.get("avoided_colors", [])
        self.worn_yesterday_ids  = data.get("worn_yesterday_ids", [])
        # List of [color_a, color_b] pairs that should never appear together
        self.avoided_combos = data.get("avoided_combos", [])

    def get_implied_formality(self):
        occasion_formality = self.OCCASION_FORMALITY.get(self.occasion, 50)
        return int(self.formality * 0.7 + occasion_formality * 0.3)

    def to_text_summary(self):
        lines = [
            f"Occasion: {self.occasion}",
            f"General styles: {', '.join(self.styles) if self.styles else 'none'}",
            f"Style mood for today: {self.style_today if self.style_today else 'not specified'}",
            f"Event theme/inspiration: {self.event_theme if self.event_theme else 'none'}",
            f"Formality (0=casual,100=formal): {self.formality}",
            f"Comfort vs Style: {self.comfort_vs_style}",
            f"Layering: {self.layering}",
            f"Boldness: {self.boldness}",
            f"Weather sensitivity (0=ignore,100=top priority): {self.weather_sensitivity}",
            f"Preferred colors: {', '.join(self.preferred_colors) if self.preferred_colors else 'none'}",
            f"Colors to avoid: {', '.join(self.avoided_colors) if self.avoided_colors else 'none'}",
            f"Worn yesterday (deprioritize): {', '.join(self.worn_yesterday_ids) if self.worn_yesterday_ids else 'none'}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _clamp(value, min_val=0, max_val=100):
        try:
            return max(min_val, min(max_val, int(value)))
        except (TypeError, ValueError):
            return 50

if __name__ == "__main__":
    p = Preferences()
    p.set_from_dict({"styles":["Classic"],"style_today":"put-together but relaxed","occasion":"event","event_theme":"garden party","weather_sensitivity":80,"worn_yesterday_ids":["abc123"]})
    print(p.to_text_summary())
