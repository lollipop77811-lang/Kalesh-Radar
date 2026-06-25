"""
X / Twitter topic fetcher via RSSHub.
Pulls timelines of configured curator accounts and converts
their posts into Topic objects.

RSSHub Twitter route: /twitter/user/:id
"""

import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import feedparser
import requests

from bot.config import X_CURATORS, RSSHUB_BASE_URL, INDIA_KEYWORDS
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": "kalesh-radar-bot/0.1"})


def _is_india_topic(title: str, body: str, curator: str, category: str) -> bool:
    """Determine if a curator's post is India-centric."""
    if category in ("india_chaos", "comedy"):
        return True
    text = (title + " " + body).lower()
    return any(kw in text for kw in INDIA_KEYWORDS)


def _parse_engagement_from_text(text: str) -> dict:
    """
    RSSHub Twitter entries sometimes include engagement stats in the description.
    Try to extract reply/retweet/like counts.
    """
    stats = {"replies": 0, "retweets": 0, "likes": 0}

    # Pattern: "💬 123  🔁 456  ❤ 789"
    reply_match = re.search(r"(?:💬|💬\s*|\breplies?\b)[:\s]*(\d+)", text, re.IGNORECASE)
    rt_match = re.search(r"(?:🔁|🔁\s*|\bretweets?\b|\breposts?\b)[:\s]*(\d+)", text, re.IGNORECASE)
    like_match = re.search(r"(?:❤|❤\s*|\blikes?\b)[:\s]*(\d+)", text, re.IGNORECASE)

    if reply_match:
        stats["replies"] = int(reply_match.group(1))
    if rt_match:
        stats["retweets"] = int(rt_match.group(1))
    if like_match:
        stats["likes"] = int(like_match.group(1))

    return stats


def _parse_published(published: str) -> datetime:
    """Parse RSS pub date to datetime."""
    if not published:
        return datetime.now(timezone.utc) - timedelta(minutes=30)  # assume recent

    try:
        parsed = feedparser.parse(published)
        if hasattr(parsed, "published_parsed") and parsed.published_parsed:
            return datetime(*parsed.published_parsed[:6], tzinfo=timezone.utc)
        # feedparser already parses the date in the entry
        return datetime.now(timezone.utc) - timedelta(minutes=30)
    except Exception:
        return datetime.now(timezone.utc) - timedelta(minutes=30)


def fetch_x_topics() -> List[Topic]:
    """
    Fetch topics from all configured X curator accounts via RSSHub.
    Returns a flat list of Topic objects.
    """
    topics: List[Topic] = []

    for handle, cfg in X_CURATORS.items():
        try:
            fetched = _fetch_curator(handle, cfg)
            topics.extend(fetched)
            logger.info(f"@{handle}: fetched {len(fetched)} topics")
        except Exception as e:
            logger.error(f"Failed to fetch @{handle}: {e}")
            time.sleep(2)

    logger.info(f"X total: {len(topics)} topics")
    return topics


def _fetch_curator(handle: str, cfg: dict) -> List[Topic]:
    """Fetch a single curator's timeline from RSSHub."""
    url = f"{RSSHUB_BASE_URL}/twitter/user/{handle}"

    resp = _session.get(url, timeout=15)
    resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    topics = []

    for entry in feed.entries[:15]:  # Last 15 posts per curator
        title = entry.get("title", "").strip()
        if not title:
            continue

        # The link is the tweet URL
        link = entry.get("link", "")
        if not link:
            continue

        # Description often contains the full tweet text + engagement stats
        description = entry.get("description", "")
        # Strip HTML tags for body text
        body = re.sub(r"<[^>]+>", "", description)[:500]

        # Parse engagement
        stats = _parse_engagement_from_text(description)

        # Parse publish time
        published = entry.get("published", entry.get("updated", ""))
        created_at = _parse_published(published)

        is_india = _is_india_topic(title, body, handle, cfg.get("category", ""))

        topic = Topic(
            source="x",
            subreddit=None,
            curator=handle,
            title=title,
            url=link,
            body=body,
            comment_count=stats["replies"],
            upvote_count=stats["likes"],
            downvote_count=0,
            upvote_ratio=1.0,  # Not available from RSS
            reply_count=stats["replies"],
            like_count=stats["likes"],
            retweet_count=stats["retweets"],
            created_at=created_at,
            is_india=is_india,
            region="india" if is_india else "worldwide",
        )
        topics.append(topic)

    return topics