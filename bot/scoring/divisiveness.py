"""
Divisiveness scorer.
Measures how divided the audience is — 50/50 splits score highest.
"""

import logging
from bot.sources.base import Topic

logger = logging.getLogger(__name__)


def score_divisiveness(topic: Topic) -> float:
    """
    Score divisiveness 0-100.
    A perfectly split audience (50/50 upvote ratio) = 100.
    A unanimous audience (95/5) = low score.
    """
    if topic.source == "reddit":
        return _score_reddit_divisiveness(topic)
    elif topic.source == "x":
        return _score_x_divisiveness(topic)
    elif topic.source == "hackernews":
        return _score_hn_divisiveness(topic)
    return 0.0


def _score_reddit_divisiveness(topic: Topic) -> float:
    """
    Reddit gives us upvote_ratio directly.
    Ratio of 0.5 = perfectly divided = 100 score.
    Ratio of 1.0 or 0.0 = unanimous = 0 score.
    """
    ratio = topic.upvote_ratio

    # RSS-sourced topics have upvote_ratio=1.0 (unknown) and comment_count=0.
    # Use a heuristic based on title keywords and subreddit to estimate divisiveness.
    if ratio >= 1.0 and topic.comment_count == 0:
        return _estimate_divisiveness_from_content(topic)

    if ratio <= 0 or ratio >= 1:
        return 5.0

    distance = abs(ratio - 0.5)
    score = (1 - distance * 2) * 100

    if topic.comment_count > 500:
        score = min(score + 15, 100)
    elif topic.comment_count > 200:
        score = min(score + 8, 100)

    return max(0, min(score, 100))


def _estimate_divisiveness_from_content(topic: Topic) -> float:
    """
    When we don't have vote data (RSS source), estimate divisiveness
    from the title content and subreddit.
    """
    score = 30  # Base score for any hot/controversial post
    title_lower = topic.title.lower()

    # Strong divisiveness signals in titles
    hot_words = [
        "controversial", "debate", "vs", "versus", "wrong", "right",
        "should", "ban", "stop", "why", "is it", "opinion", "unpopular",
        "agree", "disagree", "boycott", "cancel", "problem", "issue",
        "worse", "better", "destroying", "ruined", "saved",
        "modi", "bjp", "congress", "left", "right", "liberal", "conservative",
        "hindu", "muslim", "secular", "communal", "nationalist",
        "gender", "feminist", "misogyny", "patriarchy",
        "nepotism", "privilege", "caste", "reservation",
    ]

    matches = sum(1 for w in hot_words if w in title_lower)
    score += matches * 8  # Each match adds 8 points

    # Question titles tend to invite debate
    if "?" in topic.title:
        score += 10

    # Subreddits known for debate get a boost
    debate_subs = {"indiaspeaks", "chodi", "unpopularopinion", "subredditdrama",
                   "liberalmarxist", "india"}
    if (topic.subreddit or "").lower() in debate_subs:
        score += 10

    return max(0, min(score, 100))


def _score_x_divisiveness(topic: Topic) -> float:
    """
    X divisiveness from reply-to-like ratio.
    More replies than likes = people are arguing = high divisiveness.
    """
    replies = topic.reply_count
    likes = topic.like_count

    if likes == 0 and replies == 0:
        return 5.0  # No data, tiny base

    if likes == 0:
        # Replies but no likes = extremely divisive (ratio'd)
        return min(replies * 2, 95)

    reply_ratio = replies / likes

    if reply_ratio >= 2.0:
        # Way more replies than likes — nuclear ratio
        score = 90 + min(reply_ratio, 5) * 2
    elif reply_ratio >= 1.0:
        # More replies than likes — clearly controversial
        score = 70 + (reply_ratio - 1.0) * 20
    elif reply_ratio >= 0.5:
        score = 45 + (reply_ratio - 0.5) * 50
    elif reply_ratio >= 0.2:
        score = 25 + (reply_ratio - 0.2) * 67
    else:
        # Low reply ratio — mostly agreement
        score = reply_ratio * 125

    # Retweet/quote-tweet boost (people sharing their takes = divided opinions)
    if topic.retweet_count > replies * 0.5:
        score = min(score + 10, 100)

    return max(0, min(score, 100))


def _score_hn_divisiveness(topic: Topic) -> float:
    """
    HN divisiveness from comment-to-point ratio.
    HN doesn't have downvotes, so we use comments/points as a proxy.
    High comments relative to points = people arguing in threads.
    """
    points = topic.upvote_count
    comments = topic.comment_count

    if points == 0 and comments == 0:
        return 5.0

    if points == 0:
        return min(comments * 3, 95)

    # Comments per point ratio
    ratio = comments / points

    if ratio >= 1.0:
        # More comments than points = serious debate
        score = 70 + min(ratio - 1.0, 3) * 10
    elif ratio >= 0.5:
        score = 50 + (ratio - 0.5) * 40
    elif ratio >= 0.2:
        score = 30 + (ratio - 0.2) * 67
    else:
        score = ratio * 150

    # High absolute comments = long threads = debate
    if comments > 300:
        score = min(score + 15, 100)
    elif comments > 100:
        score = min(score + 8, 100)

    return max(0, min(score, 100))