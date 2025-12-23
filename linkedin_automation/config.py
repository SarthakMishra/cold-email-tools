"""Configuration for LinkedIn automation pipeline."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Get project directory (where this config.py file is located)
PROJECT_DIR = Path(__file__).parent

# OpenOutreach API configuration
API_BASE_URL = os.getenv("OPENOUTREACH_API_URL", "http://localhost:8000")
API_KEY = os.getenv("OPENOUTREACH_API_KEY", "")

# Account configuration
ACCOUNT_HANDLE = os.getenv("ACCOUNT_HANDLE", "")
ACCOUNT_USERNAME = os.getenv("ACCOUNT_USERNAME", "")  # LinkedIn email/username
ACCOUNT_PASSWORD = os.getenv("ACCOUNT_PASSWORD", "")  # LinkedIn password
ACCOUNT_PROXY = os.getenv("ACCOUNT_PROXY", None)  # Optional proxy
ACCOUNT_DAILY_CONNECTIONS = int(os.getenv("ACCOUNT_DAILY_CONNECTIONS", "50"))
ACCOUNT_DAILY_MESSAGES = int(os.getenv("ACCOUNT_DAILY_MESSAGES", "20"))

# Input/Output configuration (relative to project directory)
INPUT_LEADS_CSV = str(PROJECT_DIR / "input" / "leads.csv")
OUTPUT_DIR = PROJECT_DIR / "output"

# Campaign settings
PROFILE_VISIT_DURATION_S = float(os.getenv("PROFILE_VISIT_DURATION_S", "5.0"))
PROFILE_VISIT_SCROLL_DEPTH = int(os.getenv("PROFILE_VISIT_SCROLL_DEPTH", "3"))
RUN_POLL_INTERVAL_S = float(os.getenv("RUN_POLL_INTERVAL_S", "2.0"))
RUN_POLL_TIMEOUT_S = float(os.getenv("RUN_POLL_TIMEOUT_S", "300.0"))  # 5 minutes max per run

