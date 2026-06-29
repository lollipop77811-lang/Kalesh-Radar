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
    elif topic.source == "hackernews":
        return _score_hn_engagement(topic)
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
    X trends: Use GetDayTrends score (if available) or rank-based heuristic.
    GetDayTrends score is embedded in topic.body.
    """
    # Try to extract GetDayTrends score from body
    import re
    gdt_match = re.search(r"GetDayTrends score:\s*([\d.]+)", topic.body or "")
    gdt_score = float(gdt_match.group(1)) if gdt_match else 0

    if gdt_score > 0:
        # Map GetDayTrends score (typically 50-600) to engagement 0-100
        # 500+ = massive trend, 200-500 = big, 100-200 = moderate, <100 = small
        if gdt_score >= 400:
            score = 65
        elif gdt_score >= 250:
            score = 55
        elif gdt_score >= 150:
            score = 45
        else:
            score = 35
    elif topic.curator == "trends24":
        # Trends24 has no scores — use rank heuristic
        # Trends are stored with comment_count based on rank position
        score = min(30 + topic.comment_count * 0.1, 60)
    else:
        # Fallback: use reply velocity like before, but more conservative
        age_hours = max(topic.age_hours, 0.5)
        velocity = topic.reply_count / age_hours
        score = min(velocity * 0.5, 50)

    # Small boost for very recent trends
    if topic.age_hours < 2:
        score = min(score + 5, 100)

    return max(0, min(score, 100))


def _score_hn_engagement(topic: Topic) -> float:
    """
    Hacker News: we have real score (upvotes) AND comment count.
    HN is great — actual data, no scraping needed.
    """
    points = topic.upvote_count
    comments = topic.comment_count
    age = topic.age_hours
    if age < 0.5:
        age = 0.5

    # Points velocity (points per hour)
    points_velocity = points / age
    # Comment velocity
    comment_velocity = comments / age

    # Base score from points (100+ points on HN is solid)
    base = min(points / 3, 50)  # 150 pts = 50 points

    # Comment velocity bonus (high comments/hour = heated)
    if comment_velocity > 10:
        base = min(base + 25, 100)
    elif comment_velocity > 5:
        base = min(base + 15, 100)
    elif comment_velocity > 2:
        base = min(base + 8, 100)

    # Comment-to-points ratio: lots of comments relative to points = debate
    if points > 0 and comments / points > 1.0:
        base = min(base + 15, 100)
    elif points > 0 and comments / points > 0.5:
        base = min(base + 8, 100)

    # Viral signal: very recent with high engagement
    if age < 3 and points > 100:
        base = min(base + 15, 100)
    elif age < 3 and points > 50:
        base = min(base + 8, 100)

    return max(0, min(base, 100))