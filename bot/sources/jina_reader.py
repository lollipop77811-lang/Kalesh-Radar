"""
Jina Reader topic fetcher — fetches Reddit + X topics WITHOUT API keys.

How it works:
  Jina Reader (r.jina.ai) fetches any URL and returns clean Markdown.
  Reddit's .json endpoints work through Jina because Jina is a legitimate
  web reader service — Reddit doesn't block it the way they block direct
  unauthenticated API calls.

  For X/Twitter, we use Nitter instances (open-source Twitter frontend)
  which provide RSS/Atom feeds of user timelines.

  This replaces:
    - reddit.py (Reddit OAuth — needs app registration)
    - twitter.py (RSSHub — dropped Twitter support)

  No API keys needed. Works in GitHub Actions out of the box.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from xml.etree import ElementTree as ET

import requests

from bot.config import (
    REDDIT_SUBREDDITS,
    REDDIT_FETCH_LIMIT,
    X_CURATORS,
    INDIA_KEYWORDS,
    JINA_READER_BASE,
    NITTER_INSTANCES,
)
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": "kalesh-radar-bot/0.1", "Accept": "text/plain"})


# ── Reddit via Jina Reader ────────────────────────────────────────────────────

def _is_india_topic(title: str, body: str, subreddit: str) -> bool:
    """Check if a topic is India-centric based on keywords or subreddit."""
    india_subreddits = {
        "india", "indiaspeaks", "chodi", "desimeta", "indianews",
        "indianstartup", "corporateslavery", "bollyblindsngossip",
        "askindia", "iit", "engineeringstudents", "liberalmarxist",
        "indiadiscussion", "delhi", "mumbai", "indiansengagingingaandmasti",
    }
    if subreddit.lower() in india_subreddits:
        return True

    text = (title + " " + body).lower()
    return any(kw in text for kw in INDIA_KEYWORDS)


def _fetch_reddit_via_jina(subreddit: str, sort_type: str, weight: float) -> List[Topic]:
    """
    Fetch a single subreddit's listing via Jina Reader.
    Jina fetches the .json endpoint and returns the JSON as text.
    """
    reddit_url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={REDDIT_FETCH_LIMIT}&raw_json=1"
    jina_url = f"{JINA_READER_BASE}/{reddit_url}"

    resp = _session.get(jina_url, timeout=30)
    if resp.status_code != 200:
        logger.warning(f"Jina returned {resp.status_code} for r/{subreddit}/{sort_type}")
        return []

    # Jina wraps the JSON in markdown code blocks or returns it raw
    text = resp.text.strip()

    # Strip markdown code fences if present (Jina sometimes wraps JSON)
    if text.startswith("```"):
        # Remove opening fence line
        lines = text.split("\n")
        lines = lines[1:]  # skip ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON for r/{subreddit}: {e}")
        # Try to find JSON in the response
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    posts = data.get("data", {}).get("children", [])
    topics = []

    for post in posts:
        d = post.get("data", {})
        if not d:
            continue

        # Skip stickied posts
        if d.get("stickied"):
            continue

        # Skip crossposts and promoted
        if d.get("is_crosspost") or d.get("promoted"):
            continue

        created_ts = d.get("created_utc", 0)
        created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else datetime.now(timezone.utc)

        upvote_ratio = d.get("upvote_ratio", 1.0)
        score = d.get("score", 0)
        ups = d.get("ups", score)

        if 0 < upvote_ratio < 1:
            total_votes = ups / upvote_ratio
            downs = max(total_votes - ups, 0)
        else:
            downs = 0

        title = d.get("title", "")
        body = d.get("selftext", "")[:500]

        is_india = _is_india_topic(title, body, subreddit)

        topic = Topic(
            source="reddit",
            subreddit=subreddit,
            curator=None,
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


def fetch_reddit_via_jina() -> List[Topic]:
    """Fetch topics from all configured subreddits via Jina Reader."""
    topics: List[Topic] = []

    for subreddit, cfg in REDDIT_SUBREDDITS.items():
        if cfg.get("seasonal"):
            logger.info(f"Skipping seasonal subreddit r/{subreddit}")
            continue

        for sort_type in cfg["sorts"]:
            try:
                fetched = _fetch_reddit_via_jina(subreddit, sort_type, cfg.get("weight", 1.0))
                topics.extend(fetched)
                logger.info(f"r/{subreddit} [{sort_type}]: fetched {len(fetched)} topics via Jina")
            except Exception as e:
                logger.error(f"Failed to fetch r/{subreddit} [{sort_type}] via Jina: {e}")
                time.sleep(2)

    logger.info(f"Reddit (Jina) total: {len(topics)} topics")
    return topics


# ── X/Twitter via Nitter RSS ──────────────────────────────────────────────────

def _fetch_nitter_instance(base_url: str, handle: str) -> Optional[List[dict]]:
    """
    Try to fetch a user's RSS feed from a Nitter instance.
    Returns list of entry dicts or None if the instance is down.
    """
    url = f"{base_url}/{handle}/rss"
    resp = _session.get(url, timeout=15, allow_redirects=True)

    if resp.status_code != 200:
        return None

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        published_el = entry.find("atom:published", ns)
        summary_el = entry.find("atom:summary", ns)

        if title_el is None or title_el.text is None:
            continue

        entries.append({
            "title": title_el.text.strip(),
            "url": link_el.get("href", "") if link_el is not None else "",
            "published": published_el.text if published_el is not None else "",
            "summary": summary_el.text if summary_el is not None else "",
        })

    return entries if entries else None


def _is_india_x_topic(title: str, body: str, handle: str, category: str) -> bool:
    """Determine if an X post is India-centric."""
    if category in ("india_chaos", "comedy"):
        return True
    text = (title + " " + body).lower()
    return any(kw in text for kw in INDIA_KEYWORDS)


def _parse_nitter_published(published: str) -> datetime:
    """Parse ISO date from Nitter RSS feed."""
    if not published:
        return datetime.now(timezone.utc) - timedelta(minutes=30)
    try:
        # Nitter uses ISO format: 2025-01-15T10:30:00+00:00
        return datetime.fromisoformat(published.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc) - timedelta(minutes=30)


def _parse_engagement_from_nitter(text: str) -> dict:
    """Parse engagement stats from Nitter RSS summary text."""
    stats = {"replies": 0, "retweets": 0, "likes": 0}

    # Nitter sometimes includes: " Replies: 123  Retweets: 456  Likes: 789"
    reply_match = re.search(r'(?:replies?|comments?)[:\s]*(\d+)', text, re.IGNORECASE)
    rt_match = re.search(r'(?:retweets?|reposts?)[:\s]*(\d+)', text, re.IGNORECASE)
    like_match = re.search(r'(?:likes?|favorites?)[:\s]*(\d+)', text, re.IGNORECASE)

    if reply_match:
        stats["replies"] = int(reply_match.group(1))
    if rt_match:
        stats["retweets"] = int(rt_match.group(1))
    if like_match:
        stats["likes"] = int(like_match.group(1))

    return stats


def fetch_x_via_nitter() -> List[Topic]:
    """
    Fetch X/Twitter topics from curator accounts via Nitter RSS.
    Tries multiple Nitter instances — if one fails, tries the next.
    """
    all_topics: List[Topic] = []

    # Find at least one working Nitter instance
    working_instance = None
    for instance_url in NITTER_INSTANCES:
        try:
            # Quick health check — try fetching one known handle
            test = _fetch_nitter_instance(instance_url, "elonmusk")
            if test is not None:
                working_instance = instance_url
                logger.info(f"Nitter instance working: {instance_url}")
                break
        except Exception:
            continue

    if not working_instance:
        logger.warning("No working Nitter instance found. X/Twitter topics will be skipped.")
        return []

    for handle, cfg in X_CURATORS.items():
        try:
            entries = _fetch_nitter_instance(working_instance, handle)
            if entries is None:
                logger.warning(f"Nitter returned no data for @{handle}")
                continue

            topics = []
            for entry in entries[:15]:
                title = entry["title"]
                if not title:
                    continue

                url = entry["url"]
                if not url:
                    continue

                summary = entry.get("summary", "")
                body = re.sub(r"<[^>]+>", "", summary)[:500]
                stats = _parse_engagement_from_nitter(summary)
                created_at = _parse_nitter_published(entry.get("published", ""))

                is_india = _is_india_x_topic(title, body, handle, cfg.get("category", ""))

                topic = Topic(
                    source="x",
                    subreddit=None,
                    curator=handle,
                    title=title,
                    url=url,
                    body=body,
                    comment_count=stats["replies"],
                    upvote_count=stats["likes"],
                    downvote_count=0,
                    upvote_ratio=1.0,
                    reply_count=stats["replies"],
                    like_count=stats["likes"],
                    retweet_count=stats["retweets"],
                    created_at=created_at,
                    is_india=is_india,
                    region="india" if is_india else "worldwide",
                )
                topics.append(topic)

            all_topics.extend(topics)
            logger.info(f"@{handle}: fetched {len(topics)} topics via Nitter")

        except Exception as e:
            logger.error(f"Failed to fetch @{handle} via Nitter: {e}")
            time.sleep(2)

    logger.info(f"X (Nitter) total: {len(all_topics)} topics")
    return all_topics