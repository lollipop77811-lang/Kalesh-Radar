"""
Freshness scorer.
Estimates how much comment window remains before the topic dies.
"""

import logging
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

# Estimated topic lifecycle in hours by platform/source
LIFECYCLE_HOURS = {
    # Reddit — larger subs live longer
    "reddit:india": 18,
    "reddit:IndiaSpeaks": 16,
    "reddit:technology": 14,
    "reddit:unpopularopinion": 20,
    "reddit:Cricket": 6,  # Cricket drama is short-lived
    "reddit:default": 12,  # Default for unlisted subs

    # X — everything moves faster
    "x:default": 6,
}


def get_lifecycle_hours(topic: Topic) -> float:
    """Get estimated lifecycle for a topic."""
    if topic.source == "reddit":
        key = f"reddit:{topic.subreddit}" if topic.subreddit else "reddit:default"
        return LIFECYCLE_HOURS.get(key, LIFECYCLE_HOURS["reddit:default"])
    elif topic.source == "x":
        return LIFECYCLE_HOURS["x:default"]
    return 12.0


def score_freshness(topic: Topic) -> float:
    """
    Score freshness 0-100.
    100 = just posted, 0 = past its lifecycle.
    """
    lifecycle = get_lifecycle_hours(topic)
    age = topic.age_hours

    if age >= lifecycle:
        return 0.0  # Dead topic

    # Linear decay from 100 to 0 over the lifecycle
    freshness = (1 - age / lifecycle) * 100

    # Boost for topics still in their "growth" phase (first 30% of lifecycle)
    if age < lifecycle * 0.3:
        freshness = min(freshness + 15, 100)

    # Penalty for topics very close to death (last 10%)
    if age > lifecycle * 0.9:
        freshness *= 0.5

    return max(0, min(freshness, 100))


def time_to_next_slot_hours(current_slot: str) -> float:
    """Return hours until the next briefing slot."""
    slot_hours = {"morning": 9, "afternoon": 13, "evening": 17, "night": 21}
    # This is simplified — in production, calculate from actual current time
    return 4.0  # Default 4-hour gap between slots