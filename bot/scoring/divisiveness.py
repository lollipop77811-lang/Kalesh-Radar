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
    return 0.0


def _score_reddit_divisiveness(topic: Topic) -> float:
    """
    Reddit gives us upvote_ratio directly.
    Ratio of 0.5 = perfectly divided = 100 score.
    Ratio of 1.0 or 0.0 = unanimous = 0 score.
    """
    ratio = topic.upvote_ratio

    if ratio <= 0 or ratio >= 1:
        # Perfectly unanimous or no data
        return 5.0  # Tiny base score — even unanimous threads have SOME debate in comments

    # Distance from 0.5 on a 0-0.5 scale
    distance = abs(ratio - 0.5)  # 0 = perfectly split, 0.5 = unanimous
    score = (1 - distance * 2) * 100

    # Boost for high comment count even if ratio isn't 50/50
    # (long comment threads often have heated debates even with high upvote ratio)
    if topic.comment_count > 500:
        score = min(score + 15, 100)
    elif topic.comment_count > 200:
        score = min(score + 8, 100)

    # Controversial sort inherently surfaces divided threads
    # (we don't know which sort was used here, but high comment/low score suggests it)

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