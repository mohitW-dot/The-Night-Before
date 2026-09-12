"""Shared, validated configuration for the Study Assistant."""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
if not GEMINI_API_KEY or GEMINI_API_KEY == "your-free-gemini-key-here":
    raise RuntimeError(
        "GOOGLE_API_KEY is not configured. Add your Gemini API key to "
        f"{PROJECT_ROOT / '.env'} as GOOGLE_API_KEY=your-key."
    )

# The supported Google Gen AI SDK uses this stable, general-purpose model for
# text, vision, and quiz generation. It can be overridden without changing code.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
