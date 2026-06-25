"""
Reddit topic fetcher.
Uses Reddit's .json API — no third-party library needed.
"""

import logging
import time
from datetime import datetime, timezone
from typing import List

import requests

from bot.config import (
    REDDIT_SUBREDDITS,
    REDDIT_FETCH_LIMIT,
    REDDIT_USER_AGENT,
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    INDIA_KEYWORDS,
)
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

# Session with retry + auth if configured
_session = requests.Session()
_session.headers.update({"User-Agent": REDDIT_USER_AGENT})

if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
    _auth = (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
else:
    _auth = None


def _is_india_topic(title: str, body: str, subreddit: str) -> bool:
    """Check if a topic is India-centric based on keywords or subreddit."""
    # India-specific subreddits are auto-tagged
    india_subreddits = {
        "india", "IndiaSpeaks", "Chodi", "DesiMeta", "indianews",
        "IndianStartup", "CorporateSlavery", "BollyBlindsNGossip",
        "AskIndia", "iit", "EngineeringStudents", "LiberalMarxist",
        "IndiaDiscussion", "delhi", "mumbai", "indiansengagingingaandmasti",
    }
    if subreddit.lower() in {s.lower() for s in india_subreddits}:
        return True

    text = (title + " " + body).lower()
    return any(kw in text for kw in INDIA_KEYWORDS)


def fetch_reddit_topics() -> List[Topic]:
    """
    Fetch topics from all configured subreddits.
    Returns a flat list of Topic objects.
    """
    topics: List[Topic] = []

    for subreddit, cfg in REDDIT_SUBREDDITS.items():
        # Skip seasonal subreddits when not in season
        if cfg.get("seasonal"):
            logger.info(f"Skipping seasonal subreddit r/{subreddit} (implement season check)")
            continue

        for sort_type in cfg["sorts"]:
            try:
                fetched = _fetch_subreddit(subreddit, sort_type, cfg.get("weight", 1.0))
                topics.extend(fetched)
                logger.info(f"r/{subreddit} [{sort_type}]: fetched {len(fetched)} topics")
            except Exception as e:
                logger.error(f"Failed to fetch r/{subreddit} [{sort_type}]: {e}")
                time.sleep(2)  # Back off on error

    logger.info(f"Reddit total: {len(topics)} topics")
    return topics


def _fetch_subreddit(subreddit: str, sort_type: str, weight: float) -> List[Topic]:
    """Fetch a single subreddit with a given sort."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json"
    params = {"limit": REDDIT_FETCH_LIMIT}

    if _auth:
        params["raw_json"] = 1

    resp = _session.get(url, params=params, timeout=15)
    resp.raise_for_status()

    if resp.status_code == 429:
        logger.warning(f"Rate limited on r/{subreddit}, backing off")
        time.sleep(10)
        return []

    data = resp.json()
    posts = data.get("data", {}).get("children", [])

    topics = []
    for post in posts:
        d = post.get("data", {})
        if not d:
            continue

        # Skip stickied posts, crossposts with no engagement
        if d.get("stickied") or d.get("is_crosspost") and d.get("num_comments", 0) < 5:
            continue

        # Parse created_at from Reddit's epoch seconds
        created_ts = d.get("created_utc", 0)
        created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else datetime.now(timezone.utc)

        # Reddit provides upvote_ratio as 0.0-1.0
        upvote_ratio = d.get("upvote_ratio", 1.0)

        # Estimate downvotes from ratio and score
        score = d.get("score", 0)
        ups = d.get("ups", score)
        if upvote_ratio > 0 and upvote_ratio < 1:
            total_votes = ups / upvote_ratio if upvote_ratio > 0 else ups
            downs = max(total_votes - ups, 0)
        else:
            downs = 0

        title = d.get("title", "")
        body = d.get("selftext", "")[:500]  # Truncate long posts

        is_india = _is_india_topic(title, body, subreddit)

        topic = Topic(
            source="reddit",
            subreddit=subreddit,
            title=title,
            url=f"https://reddit.com{d.get('permalink', '')}",
            body=body,
            comment_count=d.get("num_comments", 0),
            upvote_count=ups,
            downvote_count=downs,
            upvote_ratio=upvote_ratio,
            created_at=created_at,
            is_india=is_india,
            region="india" if is_india else "worldwide",
        )
        topics.append(topic)

    return topics