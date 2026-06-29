"""
Base data model for topics from any source.
All fetchers return a list of Topic dicts.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Topic:
    source: str              # "reddit" or "x"
    subreddit: Optional[str] # subreddit name or None for X
    curator: Optional[str]   # X curator handle or None for Reddit
    title: str
    url: str
    body: str = ""           # post body / tweet text (truncated)
    comment_count: int = 0
    upvote_count: int = 0
    downvote_count: int = 0
    upvote_ratio: float = 1.0  # 0.0 to 1.0
    reply_count: int = 0     # X-specific: reply count
    like_count: int = 0      # X-specific: like count
    retweet_count: int = 0   # X-specific: retweet/quote-tweet count
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Computed scores (filled later by scoring engine)
    engagement_score: float = 0.0
    divisiveness_score: float = 0.0
    satirizability_score: float = 0.0
    freshness_score: float = 0.0
    final_score: float = 0.0
    safety_passed: Optional[bool] = None

    # Metadata
    is_india: bool = False
    region: str = "worldwide"  # "india" or "worldwide"

    @property
    def age_hours(self) -> float:
        """How old is this topic in hours."""
        delta = datetime.now(timezone.utc) - self.created_at
        return max(delta.total_seconds() / 3600, 0.1)

    @property
    def engagement_velocity(self) -> float:
        """Comments (or replies) per hour."""
        return self.comment_count / self.age_hours

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "subreddit": self.subreddit,
            "curator": self.curator,
            "title": self.title,
            "url": self.url,
            "body": self.body[:200],
            "comment_count": self.comment_count,
            "upvote_count": self.upvote_count,
            "downvote_count": self.downvote_count,
            "upvote_ratio": self.upvote_ratio,
            "reply_count": self.reply_count,
            "like_count": self.like_count,
            "retweet_count": self.retweet_count,
            "created_at": self.created_at.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
            "engagement_score": self.engagement_score,
            "divisiveness_score": self.divisiveness_score,
            "satirizability_score": self.satirizability_score,
            "freshness_score": self.freshness_score,
            "final_score": self.final_score,
            "safety_passed": self.safety_passed,
            "is_india": self.is_india,
            "region": self.region,
        }