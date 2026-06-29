"""
Satirizability scorer — uses LLM to assess humor/satire potential.
Falls back to rule-based scoring if no LLM API key is configured.
"""

import json
import logging
from typing import Optional, Tuple

from bot.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from bot.sources.base import Topic

logger = logging.getLogger(__name__)


def score_satirizability(topic: Topic) -> float:
    """
    Score satirizability 0-100 using LLM if available, else rules-based fallback.
    """
    # Try LLM first
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        try:
            return _score_via_openai(topic)
        except Exception as e:
            logger.warning(f"OpenAI scoring failed, falling back to rules: {e}")
    elif LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        try:
            return _score_via_anthropic(topic)
        except Exception as e:
            logger.warning(f"Anthropic scoring failed, falling back to rules: {e}")

    # Fallback to rules
    return _score_rules(topic)


def _build_prompt(topic: Topic) -> str:
    """Build the LLM prompt for satirizability scoring."""
    source_label = f"r/{topic.subreddit}" if topic.source == "reddit" else f"@{topic.curator}"
    region_label = "[INDIA]" if topic.is_india else "[WORLDWIDE]"

    prompt = f"""You are evaluating topics for a satirical/humorous social media commenter. 
This person ONLY comments in a funny, sarcastic, witty, never-serious tone. 
They specialize in hot takes on controversial/trending topics.

Rate this topic's POTENTIAL for generating a great satirical comment (0-100):

Source: {source_label}
Region: {region_label}
Title: {topic.title}
Body: {topic.body[:300]}
Comments: {topic.comment_count}
Age: {topic.age_hours:.1f} hours ago

Consider:
- Is the topic inherently absurd, ironic, or ridiculous?
- Can someone make a witty one-liner or deadpan sarcastic take?
- Is there a "everyone is missing the obvious joke" angle?
- Is it the kind of thing that makes people react with "lmao"?
- Would a non-serious comment stand out and get engagement?

Respond ONLY with a JSON object:
{{"score": <0-100>, "reason": "<one brief sentence explaining why>"}}

IMPORTANT: Score 0-10 if the topic is too serious, tragic, or sensitive to joke about.
Score 80-100 if it's literally made for satire."""

    return prompt


def _score_via_openai(topic: Topic) -> float:
    """Score using OpenAI API."""
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = _build_prompt(topic)

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a satire-potential evaluator. Always respond in valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=100,
    )

    content = response.choices[0].message.content.strip()
    return _parse_llm_response(content, topic)


def _score_via_anthropic(topic: Topic) -> float:
    """Score using Anthropic API."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_prompt(topic)

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=100,
        messages=[
            {"role": "user", "content": prompt},
        ],
    )

    content = response.content[0].text.strip()
    return _parse_llm_response(content, topic)


def _parse_llm_response(content: str, topic: Topic) -> float:
    """Parse the LLM JSON response."""
    try:
        # Try to extract JSON from the response
        # Sometimes LLM wraps in markdown code blocks
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        data = json.loads(json_str)
        score = float(data.get("score", 50))
        reason = data.get("reason", "")
        logger.debug(f"LLM satirizability for '{topic.title[:50]}...': {score} — {reason}")
        return max(0, min(score, 100))
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse LLM response: {content[:100]}... Error: {e}")
        return 50.0  # Neutral fallback


# ── Rule-based fallback ──────────────────────────────────────────────────────

# Keywords/patterns that boost satirizability
SATIRE_BOOSTERS = [
    (r"\bCEO\b.*\b(work|passion|sunday|weekend|grind|hustle)\b", 30, "CEO tone-deaf"),
    (r"\blinkedin\b", 20, "LinkedIn post"),
    (r"\bunpopular\s+opinion\b", 20, "Self-identified controversy"),
    (r"\bnepotism\b", 25, "Nepotism angle"),
    (r"\barranged\s+marriage\b", 20, "Arranged marriage debate"),
    (r"\bai\s+(will|can|should|replaced|replace)\b", 10, "AI hype/doom"),
    (r"\bcricket\b.*\b(fix|fixed|rigged|biased|unfair)\b", 20, "Cricket conspiracy"),
    (r"\b(ipl|bcci)\b", 15, "IPL/BCCI drama"),
    (r"\bstartup\b.*\b(fire|laid\s*off|funding|unicorn|down\s*round)\b", 25, "Startup drama"),
    (r"\b(corporate|work)\s*(culture|slave)\b", 25, "Corporate slavery"),
    (r"\bbollywood\b.*\b(nepotism|boycott|flop|hit)\b", 20, "Bollywood drama"),
    (r"\bshould\b.*\bbe\s+banned\b", 15, "Ban demand"),
    (r"everyone\s+(is|are)\s+(wrong|stupid|crazy|dumb)", 20, "Takes claim"),
    (r"\bhot\s+take\b", 25, "Self-identified hot take"),
    (r"ratio['d]*", 20, "Already ratio'd"),
    (r"main\s+character", 15, "Main character energy"),
    (r"red\s+flag", 15, "Red flag discussion"),
    (r"gaslighting", 15, "Gaslighting discussion"),
]

# Topics that are NEVER satirizable
SATIRE_KILLERS = [
    r"\b(died|death|killed|murder|rape|assault|suicide|terror|attack|crash|accident)\b.*\b(child|children|kid|minor)\b",
    r"\bsuicide\b.*\b(prevention|hotline|help)\b",
    r"\bmass\s+shooting\b",
    r"\bterrorist\s+attack\b",
]


def _score_rules(topic: Topic) -> float:
    """Rule-based satirizability scoring (no LLM needed)."""
    import re

    text = (topic.title + " " + topic.body).lower()
    score = 20.0  # Base score — everything has SOME potential

    # Check for satire killers first
    for killer_pattern in SATIRE_KILLERS:
        if re.search(killer_pattern, text, re.IGNORECASE):
            logger.debug(f"Satire killer matched for: {topic.title[:50]}")
            return 5.0

    # Apply boosters
    for pattern, boost, label in SATIRE_BOOSTERS:
        if re.search(pattern, text, re.IGNORECASE):
            score += boost
            logger.debug(f"Satire boost [{label}]: +{boost} for '{topic.title[:50]}'")

    # Shorter titles tend to be more "quotable" for one-liner satire
    if len(topic.title) < 80:
        score += 10
    elif len(topic.title) < 120:
        score += 5

    # Engagement as proxy: high comments = people are emotionally invested = satirizable
    if topic.comment_count > 300:
        score += 10
    elif topic.comment_count > 100:
        score += 5

    return max(0, min(score, 100))