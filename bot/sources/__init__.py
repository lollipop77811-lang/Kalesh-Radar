"""Sources package — unified fetch interface."""

from bot.sources.reddit_rss import fetch_reddit_rss
from bot.sources.reddit import fetch_reddit_topics
from bot.sources.jina_reader import fetch_x_via_nitter
from bot.sources.base import Topic
from typing import List
import logging
import os

logger = logging.getLogger(__name__)


def fetch_all_topics() -> List[Topic]:
    """
    Fetch topics from all configured sources.

    Priority order:
      1. Reddit RSS (no API keys needed) — DEFAULT
      2. Reddit OAuth (needs REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET) — FALLBACK
      3. X/Twitter via Nitter RSS (no API keys)
    """
    all_topics: List[Topic] = []

    # ── Reddit ────────────────────────────────────────────────────────────
    reddit_client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    if reddit_client_id:
        logger.info("Reddit OAuth credentials found — using official API fetcher")
        try:
            reddit_topics = fetch_reddit_topics()
            all_topics.extend(reddit_topics)
        except Exception as e:
            logger.error(f"Reddit OAuth fetch failed, falling back to RSS: {e}")
            reddit_topics = fetch_reddit_rss()
            all_topics.extend(reddit_topics)
    else:
        logger.info("No Reddit OAuth creds — using RSS feeds (no API keys needed)")
        reddit_topics = fetch_reddit_rss()
        all_topics.extend(reddit_topics)

    # ── X / Twitter via Nitter ────────────────────────────────────────────
    try:
        x_topics = fetch_x_via_nitter()
        all_topics.extend(x_topics)
    except Exception as e:
        logger.warning(f"X/Nitter fetch failed (non-fatal): {e}")

    logger.info(
        f"Total topics fetched: {len(all_topics)} "
        f"(Reddit: {sum(1 for t in all_topics if t.source == 'reddit')}, "
        f"X: {sum(1 for t in all_topics if t.source == 'x')})"
    )

    if not all_topics:
        raise RuntimeError(
            "No topics fetched from any source. "
            "Check logs above for specific errors."
        )

    return all_topics