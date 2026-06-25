"""Sources package — unified fetch interface."""

from bot.sources.reddit import fetch_reddit_topics
from bot.sources.base import Topic
from typing import List
import logging

logger = logging.getLogger(__name__)


def fetch_all_topics() -> List[Topic]:
    """Fetch topics from all configured sources."""
    all_topics = []

    # Fetch Reddit (uses OAuth — requires REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET)
    try:
        reddit_topics = fetch_reddit_topics()
        all_topics.extend(reddit_topics)
    except Exception as e:
        logger.error(f"Reddit fetch failed entirely: {e}")
        # Raise so the orchestrator knows nothing was fetched
        if not all_topics:
            raise

    # X/Twitter sources disabled — RSSHub public instance dropped Twitter support.
    # To re-enable:
    #   Option A: Self-host RSSHub (https://github.com/DIYgod/RSSHub)
    #   Option B: Use X API Basic tier ($100/mo) — see bot/sources/twitter.py
    #   Option C: Add X API keys and update twitter.py to use official API
    #
    # from bot.sources.twitter import fetch_x_topics
    # try:
    #     x_topics = fetch_x_topics()
    #     all_topics.extend(x_topics)
    # except Exception as e:
    #     logger.error(f"X fetch failed entirely: {e}")

    logger.info(f"Total topics fetched: {len(all_topics)} "
                f"(Reddit: {sum(1 for t in all_topics if t.source == 'reddit')})")

    return all_topics