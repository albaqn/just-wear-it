# main.py
# Entry point. Run this file to start the program:
#
#   python main.py
#
# Then open your browser at:  http://localhost:5000

import os
from dotenv import load_dotenv

# Load API key from .env file if it exists
# Your .env file should contain:  ANTHROPIC_API_KEY=sk-ant-...
load_dotenv()

from app import app

if __name__ == "__main__":
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    print("=" * 50)
    print("  Just Wear It — Outfit Recommender")
    print("=" * 50)

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("  ⚠  No API key found.")
        print("  The app will run but clothing analysis")
        print("  will use mock data instead of real AI.")
        print("  Add ANTHROPIC_API_KEY=sk-ant-... to a .env file.")
    else:
        print("  ✓  API key loaded.")

    print("  Opening at: http://127.0.0.1:5000")
    print("=" * 50)

    app.run(debug=True, port=5000)
