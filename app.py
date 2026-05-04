# app.py
# Flask routes — connects the Python backend to the HTML frontend.
# Each route corresponds to an action the user takes in the browser.

import os
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory

from wardrobe import wardrobe, ClothingItem
from preferences import Preferences
from recommender import Recommender
from vision import analyze_image
from explainer import explain_outfit
from theme_analyzer import analyze_theme
from weather import get_weather

app = Flask(__name__)

# ── Upload folder setup ───────────────────────────────────────────────────────
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main page."""
    return render_template("index.html")


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """Serve uploaded images back to the frontend."""
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/api/upload", methods=["POST"])
def upload_item():
    """
    Receives a clothing photo from the frontend.
    1. Saves the image to disk
    2. Calls vision.py to analyze it
    3. Creates a ClothingItem and adds it to the wardrobe
    4. Returns the item data as JSON
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Use JPG, PNG, GIF, or WEBP."}), 400

    # Save with a unique filename to avoid collisions
    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = UPLOAD_FOLDER / unique_filename
    file.save(save_path)

    # Analyze the image
    analysis = analyze_image(str(save_path))

    # Create clothing item and populate from analysis
    item = ClothingItem(
        image_path=f"/uploads/{unique_filename}",
        filename=file.filename,
    )
    item.category    = analysis["category"]
    item.color       = analysis["color"]
    item.color_hex   = analysis["color_hex"]
    item.formality   = analysis["formality"]
    item.styles      = analysis["styles"]
    # Use AI description; if it looks like a filename or is empty, build one from color+category
    raw_desc = analysis.get("description", "").strip()
    if not raw_desc or ".jpg" in raw_desc.lower() or ".png" in raw_desc.lower() or ".jpeg" in raw_desc.lower():
        raw_desc = f"{analysis['color']} {analysis['category']}"
    item.description = raw_desc
    item.season      = analysis["season"]
    item.pattern     = analysis["pattern"]

    wardrobe.add_item(item)

    response = item.to_dict()
    if analysis.get("error"):
        response["analysis_warning"] = analysis["error"]

    return jsonify(response), 201


@app.route("/api/wardrobe", methods=["GET"])
def get_wardrobe():
    """Returns all items currently in the wardrobe as JSON."""
    return jsonify({
        "items": wardrobe.to_dict_list(),
        "count": wardrobe.count(),
        "ready": wardrobe.has_enough_for_outfit(),
    })


@app.route("/api/wardrobe/<item_id>", methods=["PATCH"])
def update_item(item_id):
    """
    Updates any field on a wardrobe item.
    Accepts: description, category, color, pattern, formality, styles, available
    Used by the edit modal when the user corrects a misclassification.
    """
    item = wardrobe.get_by_id(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    data = request.get_json()

    if "available" in data:
        item.available = bool(data["available"])
    if "description" in data:
        item.description = str(data["description"]).strip()
    if "category" in data:
        valid_cats = ["top","bottom","dress","outerwear","shoes","accessory","other"]
        if data["category"] in valid_cats:
            item.category = data["category"]
    if "color" in data:
        item.color = str(data["color"]).strip()
    if "color_hex" in data:
        item.color_hex = str(data["color_hex"]).strip()
    if "pattern" in data:
        valid_patterns = ["solid","stripes","plaid","floral","print","other"]
        if data["pattern"] in valid_patterns:
            item.pattern = data["pattern"]
    if "formality" in data:
        try:
            item.formality = max(1, min(10, int(data["formality"])))
        except (TypeError, ValueError):
            pass
    if "styles" in data and isinstance(data["styles"], list):
        valid_styles = ["minimalist","classic","bohemian","streetwear","preppy",
                        "romantic","edgy","business","athleisure","elegant"]
        item.styles = [s for s in data["styles"] if s in valid_styles]

    return jsonify(item.to_dict())


@app.route("/api/wardrobe/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    """Removes an item from the wardrobe."""
    item = wardrobe.get_by_id(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    wardrobe._items = [i for i in wardrobe._items if i.id != item_id]
    return jsonify({"deleted": item_id})


@app.route("/api/recommend", methods=["POST"])
def recommend():
    """
    Main recommendation endpoint.
    1. Reads user preferences from the POST body
    2. Calls recommender.py to select the best outfit (pure Python logic)
    3. Calls explainer.py to generate the explanation (API)
    4. Returns everything as JSON

    POST body:
    {
      "preferences": { styles, occasion, formality, ... },
      "exclude_ids": []   // optional: item IDs to exclude (for "generate alternative")
    }
    """
    data = request.get_json()

    if not wardrobe.has_enough_for_outfit():
        return jsonify({
            "error": "Not enough items in wardrobe. "
                     "Please upload at least one top, one bottom, and one pair of shoes."
        }), 400

    # Build preferences object
    prefs = Preferences()
    prefs.set_from_dict(data.get("preferences", {}))

    # Get excluded item IDs (for "generate alternative" button)
    exclude_ids = data.get("exclude_ids", [])

    # Fetch real weather if location was sent by the browser
    lat = data.get("lat")
    lon = data.get("lon")
    weather_data = {}
    if prefs.weather_sensitivity > 0:
        try:
            weather_data = get_weather(
                float(lat) if lat is not None else None,
                float(lon) if lon is not None else None
            )
        except Exception as e:
            # Log the actual error so we can see what's going wrong
            print(f"[weather] fetch failed: {e}")
            weather_data = get_weather(None, None)  # fall back to seasonal

    # Run the recommendation algorithm
    rec = Recommender(wardrobe, prefs)
    rec.weather = weather_data  # inject real weather
    result = rec.recommend(exclude_ids=exclude_ids)

    if not result["selected_items"]:
        return jsonify({"error": result["warnings"][0] if result["warnings"] else "No outfit found"}), 400

    # Analyze theme if provided (already cached in recommender, but we need it for explainer too)
    theme_profile = analyze_theme(prefs.event_theme) if prefs.event_theme else {}

    # Generate explanation
    # Add weather to preferences summary for explainer
    weather_line = ""
    if weather_data:
        weather_line = f"\nCurrent weather: {weather_data.get('summary','unknown')} (source: {weather_data.get('source','estimated')})"

    explanation = explain_outfit(
        selected_items=result["selected_items"],
        preferences_summary=prefs.to_text_summary() + weather_line,
        score_breakdown=result["score_breakdown"],
        theme_profile=theme_profile,
    )

    # Mark worn items
    for item_dict in result["selected_items"]:
        wardrobe.mark_worn(item_dict["id"])

    return jsonify({
        "outfit":        result["selected_items"],
        "explanation":   explanation,
        "score":         result["score_breakdown"],
        "warnings":      result["warnings"],
        "weather":       weather_data,
    })


@app.route("/api/reset", methods=["POST"])
def reset_wardrobe():
    """Clears the entire wardrobe. Useful for starting fresh."""
    wardrobe.clear()
    return jsonify({"message": "Wardrobe cleared."})
