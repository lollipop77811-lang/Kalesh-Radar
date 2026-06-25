"""
Kalesh Radar — Configuration
All tweakable knobs live here.
Secrets are read from environment variables (set in GitHub Actions or .env file).
"""

import os

# ── Discord ──────────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_MAP = {
    "morning": os.environ.get("CHANNEL_MORNING", ""),
    "afternoon": os.environ.get("CHANNEL_AFTERNOON", ""),
    "evening": os.environ.get("CHANNEL_EVENING", ""),
    "night": os.environ.get("CHANNEL_NIGHT", ""),
}

# ── Reddit ───────────────────────────────────────────────────────────────────
REDDIT_USER_AGENT = "kalesh-radar-bot/0.1 (by /u/kaleshradar)"
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

# Subreddits to track with their sort strategy
REDDIT_SUBREDDITS = {
    # Tier 1 — Must-track
    "india":             {"sorts": ["controversial", "hot"], "weight": 1.2},
    "IndiaSpeaks":       {"sorts": ["controversial", "hot"], "weight": 1.0},
    "BollyBlindsNGossip":{"sorts": ["hot"],                 "weight": 0.9},
    "SubredditDrama":    {"sorts": ["hot"],                 "weight": 0.8},

    # Tier 2 — High-value niche
    "IndianStartup":     {"sorts": ["hot", "controversial"], "weight": 1.1},
    "CorporateSlavery":  {"sorts": ["hot"],                   "weight": 1.0},
    "DesiMeta":          {"sorts": ["hot"],                   "weight": 0.7},
    "Chodi":             {"sorts": ["hot"],                   "weight": 0.8},
    "indianews":         {"sorts": ["hot"],                   "weight": 0.7},

    # Tier 3 — Niche but explosive
    "Cricket":           {"sorts": ["hot"],           "weight": 0.6, "seasonal": True},
    "AskIndia":          {"sorts": ["hot"],           "weight": 0.5},
    "unpopularopinion":  {"sorts": ["hot"],           "weight": 0.6},
    "technology":        {"sorts": ["controversial"], "weight": 0.7},
}

# How many posts to fetch per subreddit per sort
REDDIT_FETCH_LIMIT = 25

# ── X / Twitter via RSSHub ───────────────────────────────────────────────────
RSSHUB_BASE_URL = "https://rsshub.app"  # Change to self-hosted instance if you have one

# Curator accounts to track
X_CURATORS = {
    # General India chaos
    "ScreenShotsofIndia":  {"category": "india_chaos", "weight": 1.0},
    "DealWithItIndia":     {"category": "india_chaos", "weight": 0.9},

    # Tech / Startup drama
    "inc42":               {"category": "tech",       "weight": 0.8},
    "YourStoryCo":         {"category": "tech",       "weight": 0.8},

    # Pop culture
    "FilmCompanion":       {"category": "pop_culture","weight": 0.7},

    # Wildcards / Comedic
    "TheKunalKamra":       {"category": "comedy",     "weight": 0.8},
}

# ── LLM (for satirizability scoring + safety gate) ──────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")  # "openai" or "anthropic"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-20250414")

# ── Scoring Weights ──────────────────────────────────────────────────────────
SCORING_WEIGHTS = {
    "engagement_velocity": 0.30,
    "divisiveness":        0.25,
    "satirizability":      0.25,
    "freshness":           0.20,
}

# ── Slot Configuration ──────────────────────────────────────────────────────
SLOT_CONFIG = {
    "morning": {
        "india_ratio": 0.67,    # ~2 India topics, ~1 worldwide
        "sources_priority": ["reddit_india", "reddit_india_niche", "x_india", "reddit_worldwide", "x_worldwide"],
    },
    "afternoon": {
        "india_ratio": 0.33,    # ~1 India, ~2 worldwide
        "sources_priority": ["reddit_worldwide", "x_worldwide", "reddit_india", "x_india"],
    },
    "evening": {
        "india_ratio": 0.33,
        "sources_priority": ["reddit_worldwide", "x_worldwide", "reddit_india", "reddit_india_niche"],
    },
    "night": {
        "india_ratio": 0.33,
        "sources_priority": ["reddit_worldwide", "x_worldwide", "reddit_india", "x_india"],
    },
}

# ── Topics per slot ─────────────────────────────────────────────────────────
TOPICS_PER_SLOT = 3

# ── India / Worldwide label keywords ────────────────────────────────────────
INDIA_KEYWORDS = [
    "india", "indian", "bharat", "iit", "iim", "ipl", "bcci", "bollywood",
    "cricket", "delhi", "mumbai", "bangalore", "chennai", "kolkata", "hyderabad",
    "modi", "rahul gandhi", "supreme court of india", "upsc", "neet",
    "startup india", "upsc", "jee", "cbse", "hinglish", "desi",
]

# ── Database ────────────────────────────────────────────────────────────────
DB_PATH = "data/kalesh.db"

# ── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"