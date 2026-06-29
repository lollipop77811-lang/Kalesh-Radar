"""
Reddit topic fetcher using OAuth2 client credentials flow.

Reddit's JSON API requires authentication. This fetcher uses the
client credentials flow (no user login needed) to get a read-only token.

Setup: Register a "script" app at https://www.reddit.com/prefs/apps
       → You get client_id (under app name) and client_secret
"""

import base64
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

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

_session = requests.Session()
_session.headers.update({"User-Agent": REDDIT_USER_AGENT})

# OAuth token cache
_token: Optional[str] = None
_token_expires: float = 0


def _get_access_token() -> str:
    """
    Get a read-only Reddit access token using client credentials flow.
    Token is cached and reused until it expires.
    """
    global _token, _token_expires

    if _token and time.time() < _token_expires:
        return _token

    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        raise RuntimeError(
            "Reddit OAuth requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET. "
            "Register a script app at https://www.reddit.com/prefs/apps"
        )

    auth = base64.b64encode(
        f"{REDDIT_CLIENT_ID}:{REDDIT_CLIENT_SECRET}".encode()
    ).decode()

    resp = _session.post(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {auth}"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    _token = data["access_token"]
    # Reddit tokens last 1 hour, refresh 5 min early
    _token_expires = time.time() + data.get("expires_in", 3600) - 300

    logger.info("Reddit OAuth token obtained successfully")
    return _token


def _api_get(url: str, params: dict = None) -> requests.Response:
    """Make an authenticated GET request to Reddit's API."""
    token = _get_access_token()
    resp = _session.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )

    if resp.status_code == 401:
        # Token expired, force refresh
        global _token, _token_expires
        _token = None
        _token_expires = 0
        token = _get_access_token()
        resp = _session.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )

    if resp.status_code == 429:
        logger.warning(f"Reddit rate limited, backing off...")
        time.sleep(10)
        return _api_get(url, params)

    resp.raise_for_status()
    return resp


def _is_india_topic(title: str, body: str, subreddit: str) -> bool:
    """Check if a topic is India-centric based on keywords or subreddit."""
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
    Fetch topics from all configured subreddits using OAuth.
    Returns a flat list of Topic objects.
    """
    topics: List[Topic] = []

    for subreddit, cfg in REDDIT_SUBREDDITS.items():
        if cfg.get("seasonal"):
            logger.info(f"Skipping seasonal subreddit r/{subreddit}")
            continue

        for sort_type in cfg["sorts"]:
            try:
                fetched = _fetch_subreddit(subreddit, sort_type, cfg.get("weight", 1.0))
                topics.extend(fetched)
                logger.info(f"r/{subreddit} [{sort_type}]: fetched {len(fetched)} topics")
            except Exception as e:
                logger.error(f"Failed to fetch r/{subreddit} [{sort_type}]: {e}")
                time.sleep(2)

    logger.info(f"Reddit total: {len(topics)} topics")
    return topics


def _fetch_subreddit(subreddit: str, sort_type: str, weight: float) -> List[Topic]:
    """Fetch a single subreddit with a given sort."""
    url = f"https://oauth.reddit.com/r/{subreddit}/{sort_type}"
    params = {"limit": REDDIT_FETCH_LIMIT, "raw_json": 1}

    resp = _api_get(url, params=params)
    data = resp.json()
    posts = data.get("data", {}).get("children", [])

    topics = []
    for post in posts:
        d = post.get("data", {})
        if not d:
            continue

        if d.get("stickied"):
            continue

        created_ts = d.get("created_utc", 0)
        created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else datetime.now(timezone.utc)

        upvote_ratio = d.get("upvote_ratio", 1.0)
        score = d.get("score", 0)
        ups = d.get("ups", score)

        if upvote_ratio > 0 and upvote_ratio < 1:
            total_votes = ups / upvote_ratio if upvote_ratio > 0 else ups
            downs = max(total_votes - ups, 0)
        else:
            downs = 0

        title = d.get("title", "")
        body = d.get("selftext", "")[:500]

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