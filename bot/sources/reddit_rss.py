import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import List
from xml.etree import ElementTree as ET

import requests

from bot.config import INDIA_KEYWORDS
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({
    "User-Agent": "KaleshRadar/0.1 (RSS feed reader)",
    "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
})

# Reddit multireddit groups — each group is ONE RSS request
# This avoids per-subreddit rate limiting (non-auth IPs get 429 fast)
MULTIREDDIT_GROUPS = {
    # Kalesh core: gender wars, political memes, cultural commentary, corporate slavery
    "hot": {
        "subs": (
            "india+IndiaSpeaks+BollyBlindsNGossip+SubredditDrama+CorporateSlavery"
            "+Chodi+unpopularopinion+technology+TrueOffMyChest+antiwork"
            "+IndiaMemes+Indiangirlsontinder+IndiaTech+delhi"
            "+IndianDankMemes+DesiMeta+liberalmarxist+IndiaDiscussion"
            "+IndiaPolitics+PoliticalIndia+AskIndia+TwoXIndia+IndianParenting"
            "+IndiaNews+RealIndia+IndiaAfterDark"
        ),
        "sort": "hot",
        "limit": 75,
    },
    # Controversial takes — separate request for max drama
    "controversial": {
        "subs": (
            "india+IndiaSpeaks+SubredditDrama+unpopularopinion"
            "+Indiangirlsontinder+IndiaMemes+Chodi+IndiaDiscussion"
            "+IndiaPolitics+PoliticalIndia+TwoXIndia+liberalmarxist"
        ),
        "sort": "controversial",
        "limit": 35,
    },
    # Rising / new — catch fresh political/cultural takes early
    "rising": {
        "subs": (
            "india+IndiaSpeaks+IndiaMemes+IndiaPolitics+PoliticalIndia"
            "+Indiangirlsontinder+IndiaTech+TwoXIndia+IndiaDiscussion"
            "+BollyBlindsNGossip+CorporateSlavery+delhi"
        ),
        "sort": "rising",
        "limit": 30,
    },
}

# Subreddit-to-weight mapping for scoring
_SUBREDDIT_WEIGHTS = {
    # Kalesh goldmines — gender wars, dating culture
    "indiamemes": 1.3, "indiangirlsontinder": 1.3, "indiadankmemes": 1.2,
    "indiaafterdark": 1.2, "twoxindia": 1.1,
    # Political / debate — HIGH priority for user
    "indiapolitics": 1.4, "politicalindia": 1.4, "indianews": 1.3, "realindia": 1.2,
    "india": 1.2, "indiaspeaks": 1.2, "chodi": 1.0, "indiadiscussion": 1.0, "liberalmarxist": 1.0,
    # Tech / corporate / scam
    "indiatech": 1.2, "desimeta": 1.1, "corporateslavery": 1.1, "antiwork": 0.8,
    # Cultural / family drama
    "indianparenting": 1.2, "askindia": 1.1, "delhi": 0.9,
    # Drama / gossip
    "bollyblindsngossip": 0.9, "subredditdrama": 0.8,
    # General controversy
    "unpopularopinion": 0.7, "technology": 0.7, "trueoffmychest": 0.7,
}

# Subreddits that are India-centric
_INDIA_SUBREDDITS = {
    "india", "indiaspeaks", "chodi", "desimeta", "indianews",
    "indianstartup", "corporateslavery", "bollyblindsngossip",
    "askindia", "liberalmarxist", "indiadiscussion",
    # Meme/take/gender/cultural subs
    "indiamemes", "indiangirlsontinder", "indiadankmemes",
    "indiatech", "delhi", "twoxindia",
    # Political subs
    "indiapolitics", "politicalindia", "realindia",
    # Cultural/family/life subs
    "indianparenting", "indiaafterdark",
}


def _is_india_topic(title: str, body: str, subreddit: str) -> bool:
    if subreddit.lower() in _INDIA_SUBREDDITS:
        return True
    text = (title + " " + body).lower()
    return any(kw in text for kw in INDIA_KEYWORDS)


def _parse_atom_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _fetch_multireddit(group_name: str, config: dict) -> List[Topic]:
    """Fetch a multireddit RSS feed (one HTTP request for multiple subreddits)."""
    url = (
        f"https://www.reddit.com/r/{config['subs']}"
        f"/{config['sort']}/.rss?limit={config['limit']}"
    )

    logger.info(f"Fetching {group_name} multireddit: r/{config['subs'][:40]}...")

    resp = _session.get(url, timeout=30)
    if resp.status_code == 429:
        logger.warning(f"{group_name}: rate-limited (429), retrying in 10s...")
        time.sleep(10)
        resp = _session.get(url, timeout=30)
    if resp.status_code == 403:
        logger.error(f"{group_name}: blocked (403)")
        return []
    if resp.status_code != 200:
        logger.warning(f"{group_name}: HTTP {resp.status_code}")
        return []

    return _parse_reddit_atom(resp.text)


def _parse_reddit_atom(xml_text: str) -> List[Topic]:
    """Parse Reddit Atom XML into Topic objects."""
    topics = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"Failed to parse Atom XML: {e}")
        return topics

    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall("a:entry", ns)
    if not entries:
        entries = root.findall("entry")

    for entry in entries:
        # Helper to get text from namespaced element
        def get_text(path):
            el = entry.find(path, ns)
            if el is None:
                el = entry.find(path)
            if el is not None and el.text:
                return el.text.strip()
            return ""

        def get_attr(path, attr):
            el = entry.find(path, ns)
            if el is None:
                el = entry.find(path)
            if el is not None:
                return el.get(attr, "")
            return ""

        title = get_text("a:title")
        if not title:
            continue

        # Skip AutoModerator scheduled threads
        author = get_text("a:author/a:name")
        if author == "AutoModerator":
            continue

        # Get subreddit from <category term="subreddit">
        cat_el = entry.find("a:category", ns)
        subreddit = cat_el.get("term", "") if cat_el is not None else ""

        url = get_attr("a:link", "href")
        if not url:
            continue

        published = get_text("a:published") or get_text("a:updated")

        # Parse body (decode HTML entities, strip tags)
        content = get_text("a:content")
        content = html.unescape(content)
        body = re.sub(r"<[^>]+>", " ", content).strip()
        body = re.sub(r"\s+", " ", body)[:500]

        created_at = _parse_atom_date(published)
        is_india = _is_india_topic(title, body, subreddit)

        topic = Topic(
            source="reddit",
            subreddit=subreddit,
            curator=None,
            title=title,
            url=url,
            body=body,
            comment_count=0,
            upvote_count=0,
            downvote_count=0,
            upvote_ratio=1.0,
            created_at=created_at,
            is_india=is_india,
            region="india" if is_india else "worldwide",
        )
        topics.append(topic)

    return topics


def fetch_reddit_rss() -> List[Topic]:
    """Fetch topics from all subreddit groups via multireddit RSS feeds."""
    all_topics: List[Topic] = []

    for group_name, config in MULTIREDDIT_GROUPS.items():
        try:
            topics = _fetch_multireddit(group_name, config)
            all_topics.extend(topics)
            logger.info(f"{group_name}: {len(topics)} topics via multireddit RSS")
        except Exception as e:
            logger.error(f"Failed to fetch {group_name} multireddit: {e}")

        # Delay between groups to avoid rate limits
        if group_name != list(MULTIREDDIT_GROUPS.keys())[-1]:
            time.sleep(3)

    logger.info(f"Reddit RSS total: {len(all_topics)} topics")
    return all_topics