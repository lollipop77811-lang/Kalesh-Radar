"""
Kalesh Radar — Configuration
All tweakable knobs live here.
Secrets are read from environment variables (set in GitHub Actions or .env file).
"""

import os

# ── Jina Reader (free, no API keys — default Reddit fetcher) ─────────────────
JINA_READER_BASE = os.environ.get("JINA_READER_BASE", "https://r.jina.ai")

# ── Nitter instances (open-source Twitter frontend with RSS) ─────────────────
# ── X/Twitter Trend Sources ─────────────────────────────────────────────────
# GetDayTrends provides scored, ranked X/Twitter trends with recency.
# Trends24 provides raw trending topic names (no scores, more topics).
X_TREND_SOURCES = {
    "getdaytrends": {
        "india": "https://getdaytrends.com/india/",
        "india_top": "https://getdaytrends.com/india/top/tweeted/day/",
        "worldwide": "https://getdaytrends.com/united-states/",
        "worldwide_top": "https://getdaytrends.com/united-states/top/tweeted/day/",
    },
    "trends24": {
        "india": "https://trends24.in/india/",
        "worldwide": "https://trends24.in/united-states/",
    },
}

# Maximum trends to fetch per source per region
X_TRENDS_PER_SOURCE = 25

# Dead Nitter instances (kept for reference — DO NOT USE)
# NITTER_INSTANCES = [
#     "https://nitter.privacydev.net",    # Connection refused
#     "https://nitter.poast.org",         # 403 Cloudflare
#     "https://nitter.woodland.cafe",     # Connection refused
#     "https://nitter.projectsegfau.lt",  # IP banned
# ]

# ── Discord (Webhooks — more reliable than bot gateway for CI) ────────────────
# Create webhooks in each channel: Channel Settings → Integrations → Webhooks → New
DISCORD_CHANNEL_MAP = {
    "morning":   os.environ.get("WEBHOOK_MORNING", ""),
    "afternoon": os.environ.get("WEBHOOK_AFTERNOON", ""),
    "evening":   os.environ.get("WEBHOOK_EVENING", ""),
    "night":     os.environ.get("WEBHOOK_NIGHT", ""),
}

# ── Reddit OAuth (OPTIONAL — only needed if Jina Reader fails) ──────────────
# If these are not set, the bot uses Jina Reader (free, no API keys).
# To enable OAuth: register a script app at https://www.reddit.com/prefs/apps
REDDIT_USER_AGENT = "kalesh-radar-bot/0.1 (by /u/kaleshradar)"
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

# Subreddits to track with their sort strategy
# NOTE: When using RSS (no API keys), Reddit rate-limits aggressively.
# Keep this list focused on the highest-value subreddits to stay within limits.
REDDIT_SUBREDDITS = {
    # Tier 1 — Must-track (India)
    "india":             {"sorts": ["hot"], "weight": 1.2},
    "IndiaSpeaks":       {"sorts": ["hot"], "weight": 1.0},
    "SubredditDrama":    {"sorts": ["hot"], "weight": 0.8},
    "BollyBlindsNGossip":{"sorts": ["hot"], "weight": 0.9},

    # Tier 2 — High-value niche (India)
    "CorporateSlavery":  {"sorts": ["hot"], "weight": 1.0},
    "Chodi":             {"sorts": ["hot"], "weight": 0.8},

    # Tier 3 — Worldwide + niche
    "unpopularopinion":  {"sorts": ["hot"], "weight": 0.6},
    "technology":        {"sorts": ["hot"], "weight": 0.7},
}

# How many posts to fetch per subreddit per sort (keep low to avoid rate limits)
REDDIT_FETCH_LIMIT = 10

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

# ── Satire Threshold ─────────────────────────────────────────────────────
# Only topics with satirizability score >= this threshold are considered.
# Set to 0 to disable filtering.
SATIRE_MIN_THRESHOLD = 70

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