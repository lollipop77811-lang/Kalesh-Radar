"""
Engagement velocity scorer.
Measures how FAST a topic is getting engagement, not just total engagement.
"""

import logging
from bot.sources.base import Topic
from bot.config import REDDIT_SUBREDDITS

logger = logging.getLogger(__name__)

# Estimated average velocity thresholds per subreddit (comments/hour)
# These are rough baselines — topics above these are "above average"
_BASELINE_VELOCITIES = {
    "india": 15,
    "IndiaSpeaks": 10,
    "BollyBlindsNGossip": 8,
    "SubredditDrama": 12,
    "IndianStartup": 5,
    "CorporateSlavery": 4,
    "technology": 20,
    "unpopularopinion": 10,
    "Cricket": 30,
}

DEFAULT_VELOCITY_BASELINE = 8  # comments/hour for unknown subs


def score_engagement(topic: Topic) -> float:
    """
    Score engagement velocity 0-100.
    A topic blowing up faster than its subreddit's average scores higher.
    """
    if topic.source == "reddit":
        return _score_reddit_engagement(topic)
    elif topic.source == "x":
        return _score_x_engagement(topic)
    return 0.0


def _score_reddit_engagement(topic: Topic) -> float:
    """Reddit: velocity = comments / age_in_hours."""
    # RSS-sourced topics have comment_count=0 — give a baseline score
    # since being on hot/controversial already implies engagement
    if topic.comment_count == 0 and topic.upvote_count == 0:
        # No engagement data (RSS source). Freshness becomes the key signal.
        # More recent = likely more engaged.
        if topic.age_hours < 4:
            return 55  # Very recent, likely still active
        elif topic.age_hours < 12:
            return 45  # Recent
        else:
            return 30  # Older, less likely to be active

    velocity = topic.engagement_velocity  # comments per hour

    # Get baseline for this subreddit
    sub = topic.subreddit or ""
    baseline = _BASELINE_VELOCITIES.get(sub, DEFAULT_VELOCITY_BASELINE)

    # Score relative to baseline, capped at 100
    if baseline > 0:
        score = (velocity / baseline) * 50  # 50 = average
    else:
        score = 0

    # Boost for high absolute engagement too
    if topic.comment_count > 200:
        score = min(score + 15, 100)
    elif topic.comment_count > 100:
        score = min(score + 8, 100)

    # Boost for very recent high engagement (viral signal)
    if topic.age_hours < 2 and topic.comment_count > 50:
        score = min(score + 20, 100)

    return max(0, min(score, 100))


def _score_x_engagement(topic: Topic) -> float:
    """
    X: Use reply count as proxy for engagement.
    Higher replies relative to likes = more heated = higher velocity.
    """
    replies = topic.reply_count
    likes = topic.like_count
    retweets = topic.retweet_count

    if topic.age_hours < 0.5:
        age_hours = 0.5  # Floor to avoid division issues
    else:
        age_hours = topic.age_hours

    velocity = replies / age_hours

    # Reply-to-like ratio: high replies + low likes = ratio'd = high engagement
    if likes > 0:
        reply_ratio = replies / likes
    else:
        reply_ratio = replies  # All replies, no likes = maximum ratio

    # Base score from velocity (reply velocity)
    score = min(velocity * 2, 60)  # Scale: 30 replies/hr = 60 points

    # Ratio bonus: more replies than likes = controversial
    if reply_ratio > 1.0:
        score = min(score + 25, 100)
    elif reply_ratio > 0.5:
        score = min(score + 15, 100)
    elif reply_ratio > 0.2:
        score = min(score + 5, 100)

    # Retweet boost (quote tweets = people engaging with takes)
    if retweets > 100:
        score = min(score + 15, 100)
    elif retweets > 50:
        score = min(score + 10, 100)
    elif retweets > 20:
        score = min(score + 5, 100)

    return max(0, min(score, 100))