"""
Scoring engine — orchestrates all scorers and computes the final score.
"""

import logging
from typing import List, Tuple

from bot.config import SCORING_WEIGHTS, SLOT_CONFIG, TOPICS_PER_SLOT, SATIRE_MIN_THRESHOLD
from bot.sources.base import Topic
from bot.scoring.engagement import score_engagement
from bot.scoring.divisiveness import score_divisiveness
from bot.scoring.freshness import score_freshness
from bot.scoring.satire import score_satirizability

logger = logging.getLogger(__name__)


def score_all_topics(topics: List[Topic]) -> List[Topic]:
    """Score every topic with all four scorers."""
    for topic in topics:
        try:
            topic.engagement_score = score_engagement(topic)
            topic.divisiveness_score = score_divisiveness(topic)
            topic.satirizability_score = score_satirizability(topic)
            topic.freshness_score = score_freshness(topic)

            # Weighted final score
            topic.final_score = (
                topic.engagement_score * SCORING_WEIGHTS["engagement_velocity"]
                + topic.divisiveness_score * SCORING_WEIGHTS["divisiveness"]
                + topic.satirizability_score * SCORING_WEIGHTS["satirizability"]
                + topic.freshness_score * SCORING_WEIGHTS["freshness"]
            )
        except Exception as e:
            logger.error(f"Scoring failed for '{topic.title[:50]}': {e}")
            topic.final_score = 0

    return topics


def select_top_topics(topics: List[Topic], slot: str) -> List[Topic]:
    """
    From all scored topics, select the top N for a given slot.
    Respects India/worldwide ratio from slot config.
    """
    slot_cfg = SLOT_CONFIG.get(slot, SLOT_CONFIG["morning"])
    india_ratio = slot_cfg.get("india_ratio", 0.5)
    n = TOPICS_PER_SLOT

    # Filter to only safe topics
    safe_topics = [t for t in topics if t.safety_passed is not False]

    # Filter by satire threshold — only topics with high satire potential
    if SATIRE_MIN_THRESHOLD > 0:
        before_satire = len(safe_topics)
        safe_topics = [t for t in safe_topics if t.satirizability_score >= SATIRE_MIN_THRESHOLD]
        logger.info(
            f"Satire gate (>= {SATIRE_MIN_THRESHOLD}): "
            f"{before_satire} → {len(safe_topics)} topics passed"
        )

    # Separate by region
    india_topics = [t for t in safe_topics if t.region == "india"]
    worldwide_topics = [t for t in safe_topics if t.region == "worldwide"]

    # Sort each by final score descending
    india_topics.sort(key=lambda t: t.final_score, reverse=True)
    worldwide_topics.sort(key=lambda t: t.final_score, reverse=True)

    # Calculate how many India vs worldwide
    n_india = round(n * india_ratio)
    n_worldwide = n - n_india

    selected: List[Topic] = []

    # Pick top India topics
    for t in india_topics:
        if len(selected) >= n_india + n_worldwide:
            break
        if _is_not_duplicate(t, selected):
            selected.append(t)
            if len([s for s in selected if s.region == "india"]) >= n_india:
                break

    # Fill remaining slots with worldwide topics
    for t in worldwide_topics:
        if len(selected) >= n:
            break
        if _is_not_duplicate(t, selected):
            selected.append(t)

    # If we don't have enough, fill from whichever pool has more
    if len(selected) < n:
        remaining = [t for t in safe_topics if _is_not_duplicate(t, selected)]
        remaining.sort(key=lambda t: t.final_score, reverse=True)
        for t in remaining:
            if len(selected) >= n:
                break
            selected.append(t)

    # Sort final selection by score (ranked)
    selected.sort(key=lambda t: t.final_score, reverse=True)

    # Trim to exactly N
    selected = selected[:n]

    logger.info(f"Selected {len(selected)} topics for {slot} slot "
                f"(India: {sum(1 for t in selected if t.region == 'india')}, "
                f"Worldwide: {sum(1 for t in selected if t.region == 'worldwide')})")

    return selected


def _is_not_duplicate(topic: Topic, selected: List[Topic]) -> bool:
    """Check if this topic is not a duplicate of an already-selected one."""
    title_lower = topic.title.lower().strip()

    for s in selected:
        other_lower = s.title.lower().strip()
        # Exact match
        if title_lower == other_lower:
            return False
        # High overlap (same topic from different sources)
        if _title_similarity(title_lower, other_lower) > 0.7:
            return False
        # Same URL
        if topic.url and s.url and topic.url == s.url:
            return False

    return True


def _title_similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)