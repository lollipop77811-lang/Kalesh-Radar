"""Sources package — unified fetch interface."""

from bot.sources.reddit_rss import fetch_reddit_rss
from bot.sources.reddit import fetch_reddit_topics
from bot.sources.hackernews import fetch_hackernews
from bot.sources.x_trends import fetch_x_trends
from bot.sources.base import Topic
from typing import List
import logging
import os

logger = logging.getLogger(__name__)


def fetch_all_topics() -> List[Topic]:
    """
    Fetch topics from all configured sources.

    Sources (no API keys needed):
      1. Reddit RSS (multireddit feeds) — India + worldwide
      2. X/Twitter trends (GetDayTrends + Trends24) — India + worldwide
      3. Hacker News API — worldwide tech/startup drama

    Optional sources (need API keys):
      4. Reddit OAuth (if REDDIT_CLIENT_ID set)
    """
    all_topics: List[Topic] = []

    # ── Reddit via RSS (default, no keys needed) ──────────────────────────
    reddit_client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    if reddit_client_id:
        logger.info("Reddit OAuth credentials found — using official API fetcher")
        try:
            reddit_topics = fetch_reddit_topics()
            all_topics.extend(reddit_topics)
        except Exception as e:
            logger.error(f"Reddit OAuth failed, falling back to RSS: {e}")
            all_topics.extend(fetch_reddit_rss())
    else:
        logger.info("Using Reddit RSS feeds (no API keys needed)")
        all_topics.extend(fetch_reddit_rss())

    # ── X/Twitter Trends (GetDayTrends + Trends24, no keys) ──────────────
    try:
        x_topics = fetch_x_trends()
        all_topics.extend(x_topics)
    except Exception as e:
        logger.warning(f"X/Twitter trends fetch failed (non-fatal): {e}")

    # ── Hacker News (free API, no keys) ───────────────────────────────────
    try:
        hn_topics = fetch_hackernews()
        all_topics.extend(hn_topics)
    except Exception as e:
        logger.warning(f"Hacker News fetch failed (non-fatal): {e}")

    reddit_count = sum(1 for t in all_topics if t.source == "reddit")
    hn_count = sum(1 for t in all_topics if t.source == "hackernews")
    x_count = sum(1 for t in all_topics if t.source == "x")

    logger.info(
        f"Total topics: {len(all_topics)} "
        f"(Reddit: {reddit_count}, X: {x_count}, HN: {hn_count})"
    )

    if not all_topics:
        raise RuntimeError(
            "No topics fetched from any source. "
            "Check logs above for specific errors."
        )

    return all_topics
