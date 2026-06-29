"""
X/Twitter trend fetcher — scrapes X trending topics from GetDayTrends + Trends24.

Why these sources instead of Nitter/Nitter forks:
  - All Nitter instances are dead or blocked (tested 2026-06-29)
  - X/Twitter blocks non-authenticated scraping (login wall)
  - GetDayTrends provides SCORED, RANKED X trends with recency data
  - Trends24 provides raw trend names (more volume, no scores)

No API keys needed. Works in GitHub Actions out of the box.
"""

import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from urllib.parse import quote

import requests

from bot.config import (
    X_TREND_SOURCES,
    X_TRENDS_PER_SOURCE,
    INDIA_KEYWORDS,
)
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})

# Skip list — boring/irrelevant trends that are never satirizable
_SKIP_PATTERNS = [
    r"^#?good\s*(morning|night|evening|afternoon)",
    r"^#?god(morning|night|evening)",
    r"^#?happy\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    r"^#?hbd_",  # generic birthday wishes
    r"^\d+\s*(cr|crore|lakh|k|million|billion)$",  # pure numbers (stock volumes)
    r"^\d+\s*pfc$",  # stock tickers
    r"^\d+\s*rec$",  # stock tickers
    r"^\d+\s*\.$",  # single numbers
]

_SKIP_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SKIP_PATTERNS]


def _is_skip(trend_name: str) -> bool:
    """Check if a trend is boring/irrelevant."""
    for pattern in _SKIP_COMPILED:
        if pattern.search(trend_name):
            return True
    return False


def _parse_hours_ago(text: str) -> float:
    """Parse 'X hours ago' / 'Now' into hours."""
    text = text.strip().lower()
    if not text or text == "now":
        return 0.5
    match = re.search(r"(\d+)\s*h(?:our)?", text)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+)\s*m(?:in)?", text)
    if match:
        return float(match.group(1)) / 60.0
    return 2.0  # default fallback


def _make_x_search_url(trend_name: str) -> str:
    """Create an X search URL for a trend."""
    return f"https://x.com/search?q={quote(trend_name)}&f=live"


def _is_india_trend(name: str) -> bool:
    """Check if a trend is India-centric."""
    lower = name.lower()
    return any(kw in lower for kw in INDIA_KEYWORDS)


def _estimate_age_from_position(position: int) -> float:
    """Higher-ranked trends tend to be more recent."""
    if position <= 3:
        return 1.0
    elif position <= 10:
        return 2.5
    elif position <= 20:
        return 4.0
    else:
        return 6.0


# ── GetDayTrends Parser ─────────────────────────────────────────────────────

def _parse_getdaytrends_top(html: str, region: str) -> List[Topic]:
    """
    Parse GetDayTrends 'Top Tweeted' page.
    Format: table rows with [rank, trend_name, score, "X hours ago", "View details"]
    """
    topics = []

    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL)
    all_rows = []
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)
        all_rows.extend(rows)

    for row in all_rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        cell_texts = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

        # Need at least: rank, name, score, time_ago
        if len(cell_texts) < 4:
            continue

        # Skip header rows
        try:
            rank = int(cell_texts[0])
        except (ValueError, IndexError):
            continue

        trend_name = cell_texts[1].strip()
        score_str = cell_texts[2].strip()
        time_ago_str = cell_texts[3].strip()

        if not trend_name or _is_skip(trend_name):
            continue

        # Parse score
        try:
            score = float(score_str.replace(",", ""))
        except ValueError:
            score = 100.0

        # Parse time ago
        hours_ago = _parse_hours_ago(time_ago_str)
        created_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

        # Use score as engagement proxy (higher score = more tweets)
        # GetDayTrends score roughly maps to tweet volume
        comment_count = int(score * 50)  # rough estimate
        like_count = int(score * 200)

        is_india = (region == "india") or _is_india_trend(trend_name)

        topic = Topic(
            source="x",
            subreddit=None,
            curator="getdaytrends",
            title=trend_name,
            url=_make_x_search_url(trend_name),
            body=f"X/Twitter trending topic — GetDayTrends score: {score} (rank #{rank}, {time_ago_str})",
            comment_count=comment_count,
            upvote_count=like_count,
            downvote_count=0,
            upvote_ratio=1.0,
            reply_count=comment_count,
            like_count=like_count,
            retweet_count=int(score * 100),
            created_at=created_at,
            is_india=is_india,
            region="india" if is_india else "worldwide",
        )
        topics.append(topic)

    return topics


def _parse_getdaytrends_current(html: str, region: str) -> List[Topic]:
    """
    Parse GetDayTrends current trends page.
    Format: table rows with [rank, trend_name, description, "View details"]
    No scores — use position-based heuristics.
    """
    topics = []

    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL)
    all_rows = []
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)
        all_rows.extend(rows)

    for row in all_rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        cell_texts = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

        if len(cell_texts) < 3:
            continue

        try:
            rank = int(cell_texts[0])
        except (ValueError, IndexError):
            continue

        trend_name = cell_texts[1].strip()
        if not trend_name or _is_skip(trend_name):
            continue

        # Skip if we already have too many
        if len(topics) >= X_TRENDS_PER_SOURCE:
            break

        hours_ago = _estimate_age_from_position(rank)
        created_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

        # Position-based engagement estimate
        base_engagement = max(500 - rank * 15, 50)

        is_india = (region == "india") or _is_india_trend(trend_name)

        topic = Topic(
            source="x",
            subreddit=None,
            curator="getdaytrends",
            title=trend_name,
            url=_make_x_search_url(trend_name),
            body=f"X/Twitter trending topic (rank #{rank} on GetDayTrends)",
            comment_count=base_engagement,
            upvote_count=base_engagement * 3,
            downvote_count=0,
            upvote_ratio=1.0,
            reply_count=base_engagement,
            like_count=base_engagement * 3,
            retweet_count=base_engagement * 2,
            created_at=created_at,
            is_india=is_india,
            region="india" if is_india else "worldwide",
        )
        topics.append(topic)

    return topics


def _fetch_getdaytrends(region: str) -> List[Topic]:
    """Fetch X trends from GetDayTrends for a region."""
    urls = X_TREND_SOURCES["getdaytrends"]
    all_topics: List[Topic] = []

    # 1) Top Tweeted (has scores — higher quality)
    top_url = urls[f"{region}_top"]
    try:
        resp = _session.get(top_url, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 1000:
            topics = _parse_getdaytrends_top(resp.text, region)
            all_topics.extend(topics)
            logger.info(f"GetDayTrends top [{region}]: {len(topics)} scored trends")
    except Exception as e:
        logger.warning(f"GetDayTrends top [{region}] failed: {e}")

    # 2) Current trends (no scores, but more topics)
    current_url = urls[region]
    try:
        resp = _session.get(current_url, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 1000:
            topics = _parse_getdaytrends_current(resp.text, region)
            # Dedup against already-fetched top trends
            existing_names = {t.title.lower() for t in all_topics}
            new_topics = [t for t in topics if t.title.lower() not in existing_names]
            all_topics.extend(new_topics)
            logger.info(f"GetDayTrends current [{region}]: {len(new_topics)} new trends")
    except Exception as e:
        logger.warning(f"GetDayTrends current [{region}] failed: {e}")

    return all_topics


# ── Trends24 Parser ─────────────────────────────────────────────────────────

def _parse_trends24(html: str, region: str) -> List[Topic]:
    """
    Parse Trends24 page — extracts trend names from <a> tags.
    Trends24 embeds trends directly in HTML (not JS-rendered).
    """
    # Extract all <a> tag text content
    all_links = re.findall(r"<a[^>]*>(.*?)</a>", html, re.DOTALL)

    # Navigation/footer links to skip
    skip_words = [
        "checkout", "trends24", "archive", "youtube", "about",
        "feedback", "contact", "terms", "privacy", "apps", "hub",
        "historical", "x (twitter)", "offerings",
    ]

    topics = []
    seen = set()

    for link_text in all_links:
        clean = re.sub(r"<[^>]+>", "", link_text).strip()
        # Remove leading/trailing whitespace and newlines
        clean = re.sub(r"\s+", " ", clean)

        if not clean or len(clean) < 2 or len(clean) > 100:
            continue

        # Skip nav/footer links
        if any(sw in clean.lower() for sw in skip_words):
            continue

        # Skip boring trends
        if _is_skip(clean):
            continue

        # Dedup
        if clean.lower() in seen:
            continue
        seen.add(clean.lower())

        if len(topics) >= X_TRENDS_PER_SOURCE:
            break

        # Trends24 doesn't provide scores or timing — use position
        rank = len(topics) + 1
        hours_ago = _estimate_age_from_position(rank)
        created_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

        is_india = (region == "india") or _is_india_trend(clean)

        topic = Topic(
            source="x",
            subreddit=None,
            curator="trends24",
            title=clean,
            url=_make_x_search_url(clean),
            body=f"X/Twitter trending topic (rank #{rank} on Trends24)",
            comment_count=max(400 - rank * 10, 30),
            upvote_count=max(1200 - rank * 30, 100),
            downvote_count=0,
            upvote_ratio=1.0,
            reply_count=max(400 - rank * 10, 30),
            like_count=max(1200 - rank * 30, 100),
            retweet_count=max(800 - rank * 20, 60),
            created_at=created_at,
            is_india=is_india,
            region="india" if is_india else "worldwide",
        )
        topics.append(topic)

    return topics


def _fetch_trends24(region: str) -> List[Topic]:
    """Fetch X trends from Trends24 for a region."""
    url = X_TREND_SOURCES["trends24"][region]
    try:
        resp = _session.get(url, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 5000:
            # Trends24 may have encoding issues — try to fix
            html = resp.text
            topics = _parse_trends24(html, region)
            logger.info(f"Trends24 [{region}]: {len(topics)} trends")
            return topics
        else:
            logger.warning(f"Trends24 [{region}]: bad response ({resp.status_code}, {len(resp.text)} bytes)")
    except Exception as e:
        logger.warning(f"Trends24 [{region}] failed: {e}")
    return []


# ── Main Fetcher ───────────────────────────────────────────────────────────

def fetch_x_trends() -> List[Topic]:
    """
    Fetch X/Twitter trending topics from GetDayTrends + Trends24.
    Returns combined, deduplicated list of Topic objects.
    """
    all_topics: List[Topic] = []

    # Fetch India trends from both sources
    for region in ["india", "worldwide"]:
        region_topics: List[Topic] = []

        # GetDayTrends (has scores — preferred)
        gdt_topics = _fetch_getdaytrends(region)
        region_topics.extend(gdt_topics)

        # Trends24 (more volume, no scores —补充)
        existing_names = {t.title.lower() for t in region_topics}
        t24_topics = _fetch_trends24(region)
        new_t24 = [t for t in t24_topics if t.title.lower() not in existing_names]
        region_topics.extend(new_t24)

        all_topics.extend(region_topics)

    # Global dedup (same trend might appear in both India and worldwide)
    seen_titles = set()
    deduped = []
    for t in all_topics:
        key = t.title.lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            deduped.append(t)

    india_count = sum(1 for t in deduped if t.region == "india")
    ww_count = sum(1 for t in deduped if t.region == "worldwide")
    logger.info(
        f"X/Twitter trends total: {len(deduped)} "
        f"(India: {india_count}, Worldwide: {ww_count})"
    )

    return deduped
