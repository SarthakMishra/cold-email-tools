"""Configuration for outreach pipeline."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Get project directory (where this config.py file is located)
PROJECT_DIR = Path(__file__).parent

# Bright Data API configuration
BRIGHTDATA_API_KEY = os.getenv("BRIGHTDATA_API_KEY", "")
BRIGHTDATA_TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
BRIGHTDATA_SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot"
PROFILE_DATASET_ID = "gd_l1viktl72bvl7bjuj0"
COMPANY_DATASET_ID = "gd_l1vikfnt1wgvvqz95w"

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.2")

# Input/Output configuration (relative to project directory)
INPUT_LEADS_CSV = str(PROJECT_DIR / "input" / "leads.csv")
OUTPUT_DIR = PROJECT_DIR / "output"
LOCAL_PROFILES_PATH = ""
USE_LOCAL_PROFILES = False

# Polling settings
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))
POLL_TIMEOUT_SECONDS = int(os.getenv("POLL_TIMEOUT_SECONDS", "300"))
