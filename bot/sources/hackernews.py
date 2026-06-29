"""
Hacker News topic fetcher via public Firebase API — NO API keys needed.

HN's API is completely free and open. We fetch:
- Top stories (general trending)
- Controversial stories (sorted by most comments relative to score)

This replaces X/Twitter as the "worldwide" source since X has killed
all free third-party access (Nitter dead, syndication rate-limited).
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import requests

from bot.config import INDIA_KEYWORDS
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

_hn_api = "https://hacker-news.firebaseio.com/v0"
_session = requests.Session()
_session.headers.update({"User-Agent": "KaleshRadar/0.1"})


def _is_india_topic(title: str, url: str) -> bool:
    """Check if an HN story is India-centric."""
    text = (title + " " + url).lower()
    return any(kw in text for kw in INDIA_KEYWORDS)


def _fetch_item(item_id: int) -> Optional[dict]:
    """Fetch a single HN item by ID."""
    try:
        resp = _session.get(f"{_hn_api}/item/{item_id}.json", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Failed to fetch HN item {item_id}: {e}")
    return None


def _item_to_topic(item: dict, source_tag: str) -> Optional[Topic]:
    """Convert an HN item dict to a Topic object."""
    if not item or item.get("type") != "story":
        return None

    title = item.get("title", "")
    if not title:
        return None

    url = item.get("url", "")
    if not url:
        url = f"https://news.ycombinator.com/item?id={item.get('id', '')}"

    # Ask HN and Show HN are usually not controversial/drama
    if title.startswith("Ask HN:") or title.startswith("Show HN:"):
        return None

    # Parse time (HN uses Unix timestamps)
    created_ts = item.get("time", 0)
    created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else datetime.now(timezone.utc)

    score = item.get("score", 0)
    comments = item.get("descendants", 0) or 0

    is_india = _is_india_topic(title, url)

    topic = Topic(
        source="hackernews",
        subreddit=None,
        curator=None,
        title=title,
        url=url,
        body="",
        comment_count=comments,
        upvote_count=score,
        downvote_count=0,
        upvote_ratio=1.0,
        created_at=created_at,
        is_india=is_india,
        region="india" if is_india else "worldwide",
    )
    return topic


def fetch_hackernews() -> List[Topic]:
    """
    Fetch trending + controversial topics from Hacker News.
    Returns a list of Topic objects.
    """
    all_topics: List[Topic] = []

    # Fetch top stories
    try:
        resp = _session.get(f"{_hn_api}/topstories.json", timeout=10)
        if resp.status_code == 200:
            top_ids = resp.json()
            logger.info(f"HN: fetched {len(top_ids)} top story IDs")

            # Process top 20 stories (enough for good variety)
            fetched_count = 0
            for sid in top_ids[:20]:
                item = _fetch_item(sid)
                if item:
                    topic = _item_to_topic(item, "top")
                    if topic:
                        all_topics.append(topic)
                        fetched_count += 1
                # No delay needed — HN API is fast and generous

            logger.info(f"HN: converted {fetched_count} top stories to topics")

    except Exception as e:
        logger.error(f"HN top stories fetch failed: {e}")

    # Fetch latest stories for freshness
    existing_urls = {t.url for t in all_topics}
    try:
        resp = _session.get(f"{_hn_api}/newstories.json", timeout=10)
        if resp.status_code == 200:
            new_ids = resp.json()

            # Get top 10 new stories for freshness
            new_count = 0
            for sid in new_ids[:10]:
                item = _fetch_item(sid)
                if item:
                    topic = _item_to_topic(item, "new")
                    if topic and topic.url not in existing_urls:
                        all_topics.append(topic)
                        existing_urls.add(topic.url)
                        new_count += 1

            logger.info(f"HN: added {new_count} new stories")

    except Exception as e:
        logger.warning(f"HN new stories fetch failed (non-fatal): {e}")

    logger.info(f"Hacker News total: {len(all_topics)} topics")
    return all_topics