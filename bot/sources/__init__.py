"""Sources package — unified fetch interface."""

from bot.sources.base import Topic
from bot.sources.reddit import fetch_reddit_topics
from bot.sources.twitter import fetch_x_topics
from typing import List
import logging

logger = logging.getLogger(__name__)


def fetch_all_topics() -> List[Topic]:
    """Fetch topics from all configured sources."""
    all_topics = []

    # Fetch Reddit
    try:
        reddit_topics = fetch_reddit_topics()
        all_topics.extend(reddit_topics)
    except Exception as e:
        logger.error(f"Reddit fetch failed entirely: {e}")

    # Fetch X via RSSHub
    try:
        x_topics = fetch_x_topics()
        all_topics.extend(x_topics)
    except Exception as e:
        logger.error(f"X fetch failed entirely: {e}")

    logger.info(f"Total topics fetched: {len(all_topics)} "
                f"(Reddit: {sum(1 for t in all_topics if t.source == 'reddit')}, "
                f"X: {sum(1 for t in all_topics if t.source == 'x')})")

    return all_topics