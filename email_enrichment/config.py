"""Configuration for email validation pipeline."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Get project directory (where this config.py file is located)
PROJECT_DIR = Path(__file__).parent

# Reacher API configuration
REACHER_API_URL = os.getenv("REACHER_API_URL", "'https://api.reacher.email")
REACHER_API_KEY = os.getenv("REACHER_API_KEY", "")  # Only needed for managed Reacher

# Input/Output configuration (relative to project directory)
INPUT_LEADS_CSV = str(PROJECT_DIR / "input" / "leads.csv")
OUTPUT_DIR = PROJECT_DIR / "output"

# Validation settings
VALIDATION_DELAY_SECONDS = float(os.getenv("VALIDATION_DELAY_SECONDS", "1.5"))
MAX_PATTERNS_PER_LEAD = int(os.getenv("MAX_PATTERNS_PER_LEAD", "20"))
INCLUDE_RISKY = (
    os.getenv("INCLUDE_RISKY", "false").lower() == "true"
)  # Catch-all addresses
