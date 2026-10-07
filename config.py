"""Central settings: Azure OpenAI credentials, skill levels, domains, DB path."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Azure OpenAI (values come from .env)
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "").strip()
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()

# SQLite database file
DB_PATH = os.getenv("SKILLS_DB_PATH", str(BASE_DIR / "skills.db"))

# Expertise levels L1-L5
LEVELS = {
    1: "Awareness",
    2: "Intermediate",
    3: "Practitioner",
    4: "Advanced",
    5: "Expert",
}

# Fixed list of domains every skill is categorised into
DOMAINS = [
    "Programming Languages",
    "Frontend",
    "Backend & APIs",
    "Cloud & DevOps",
    "Data Engineering",
    "Data Science & Analytics",
    "AI / ML",
    "Databases",
    "Developer Tools",
    "Testing & QA",
    "Security",
    "Mobile",
    "ERP / CRM",
    "Project Management",
    "Soft Skills",
    "Other",
]


def level_label(level: int) -> str:
    """3 -> 'L3 - Practitioner'"""
    return f"L{level} - {LEVELS.get(level, 'Unknown')}"
