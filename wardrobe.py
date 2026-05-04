# wardrobe.py
# Manages the in-memory wardrobe for the session.
# No database, no files — everything lives in a Python list while the program runs.
# When the user closes the program, the wardrobe resets. That's intentional.

import uuid
from typing import Optional, List

# ── Clothing item categories the system recognizes ──────────────────────────
CATEGORIES = ["top", "bottom", "shoes", "outerwear", "accessory", "dress", "other"]

# ── For a complete outfit, we need at least these slots filled ───────────────
# A "dress" can substitute for top + bottom together.
REQUIRED_SLOTS  = ["top", "bottom", "shoes"]
OPTIONAL_SLOTS  = ["outerwear", "accessory"]


class ClothingItem:
    """
    Represents one piece of clothing in the wardrobe.

    Some fields (like category, color, formality) are filled automatically
    by vision.py when the user uploads a photo.
    Others (like available) can be toggled by the user.
    """

    def __init__(self, image_path: str, filename: str):
        # Unique ID so we can reference this item later
        self.id = str(uuid.uuid4())[:8]

        # Path to the uploaded image file (used to display it in results)
        self.image_path  = image_path
        self.filename    = filename

        # ── Fields filled by vision.py after photo analysis ──
        self.category    = "other"      # top / bottom / shoes / outerwear / accessory / dress
        self.color       = "unknown"    # human-readable color name, e.g. "navy blue"
        self.color_hex   = "#888888"    # hex code extracted from the image
        self.formality   = 5            # 1 (very casual) to 10 (very formal)
        self.styles      = []           # list of style tags, e.g. ["classic", "minimalist"]
        self.description = ""           # short description, e.g. "navy slim-fit blazer"
        self.season      = ["all"]      # list: "spring", "summer", "fall", "winter", "all"
        self.pattern     = "solid"      # solid / stripes / plaid / floral / print / other

        # ── Fields the user can control ──
        self.available   = True         # False if dirty, lent out, or out of season
        self.times_worn  = 0            # tracked within the session

    def to_dict(self) -> dict:
        """Converts item to a dictionary — used to send data to the frontend."""
        return {
            "id":          self.id,
            "filename":    self.filename,
            "image_path":  self.image_path,
            "category":    self.category,
            "color":       self.color,
            "color_hex":   self.color_hex,
            "formality":   self.formality,
            "styles":      self.styles,
            "description": self.description,
            "season":      self.season,
            "pattern":     self.pattern,
            "available":   self.available,
            "times_worn":  self.times_worn,
        }

    def to_text_summary(self) -> str:
        """
        Short text description of this item.
        Used when we send the wardrobe list to the AI in recommender.py.
        Keeps token usage low while giving the AI enough info to decide.
        """
        return (
            f"[ID: {self.id}] {self.description} | "
            f"Category: {self.category} | "
            f"Color: {self.color} ({self.color_hex}) | "
            f"Formality: {self.formality}/10 | "
            f"Styles: {', '.join(self.styles)} | "
            f"Pattern: {self.pattern} | "
            f"Season: {', '.join(self.season)}"
        )

    def __repr__(self):
        return f"<ClothingItem {self.id}: {self.description}>"


class Wardrobe:
    """
    The user's wardrobe for this session.
    Just a list of ClothingItem objects with helper methods.
    """

    def __init__(self):
        self._items: list[ClothingItem] = []

    def add_item(self, item: ClothingItem):
        """Add a new clothing item to the wardrobe."""
        self._items.append(item)

    def get_all(self) -> list[ClothingItem]:
        """Return all items."""
        return self._items

    def get_available(self) -> list[ClothingItem]:
        """Return only items marked as available."""
        return [item for item in self._items if item.available]

    def get_by_id(self, item_id: str) -> Optional[ClothingItem]:
        """Find an item by its ID. Returns None if not found."""
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def get_by_category(self, category: str) -> list[ClothingItem]:
        """Return all available items of a specific category."""
        return [
            item for item in self.get_available()
            if item.category == category
        ]
    def mark_worn(self, item_id: str):
        """Increment the worn counter for an item."""
        item = self.get_by_id(item_id)
        if item:
            item.times_worn += 1

    def clear(self):
        """Reset the wardrobe entirely."""
        self._items = []

    def count(self) -> int:
        return len(self._items)

    def to_text_summary(self) -> str:
        """
        Full wardrobe as text — sent to the AI in recommender.py.
        Only includes available items.
        """
        available = self.get_available()
        if not available:
            return "The wardrobe is empty."
        lines = [f"Wardrobe ({len(available)} available items):"]
        for item in available:
            lines.append(f"  - {item.to_text_summary()}")
        return "\n".join(lines)

    def to_dict_list(self) -> list[dict]:
        """All items as a list of dicts — used by Flask to send JSON to frontend."""
        return [item.to_dict() for item in self._items]

    def has_enough_for_outfit(self) -> bool:
        """
        Check whether the wardrobe has at least one item in each required slot.
        A dress counts as both top and bottom.
        Items categorized as 'other' are counted as wildcards.
        """
        has_dress  = len(self.get_by_category("dress")) > 0
        has_top    = len(self.get_by_category("top")) > 0
        has_bottom = len(self.get_by_category("bottom")) > 0
        has_shoes  = len(self.get_by_category("shoes")) > 0
        has_other  = len(self.get_by_category("other")) > 0

        top_bottom_ok = has_dress or (has_top and has_bottom) or (has_other and (has_top or has_bottom))
        shoes_ok = has_shoes or has_other
        return top_bottom_ok and shoes_ok

    def __repr__(self):
        return f"<Wardrobe: {self.count()} items>"


# ── Shared singleton instance used across the app ───────────────────────────
# All Flask routes import this single object so they share the same wardrobe.
wardrobe = Wardrobe()


# ── Quick test ───────────────────────────────────────────────────────────────
