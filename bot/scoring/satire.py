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
    # India-specific kalesh
    (r"\bCEO\b.*\b(work|passion|sunday|weekend|grind|hustle)\b", 30, "CEO tone-deaf"),
    (r"\blinkedin\b", 25, "LinkedIn post"),
    (r"\bunpopular\s+opinion\b", 25, "Self-identified controversy"),
    (r"\bnepotism\b", 25, "Nepotism angle"),
    (r"\barranged\s+marriage\b", 25, "Arranged marriage debate"),
    (r"\bcricket\b.*\b(fix|fixed|rigged|biased|unfair)\b", 25, "Cricket conspiracy"),
    (r"\b(ipl|bcci)\b", 20, "IPL/BCCI drama"),
    (r"\bstartup\b.*\b(fire|laid\s*off|funding|unicorn|down\s*round)\b", 25, "Startup drama"),
    (r"\b(corporate|work)\s*(culture|slave)\b", 25, "Corporate slavery"),
    (r"\bbollywood\b.*\b(nepotism|boycott|flop|hit)\b", 25, "Bollywood drama"),
    (r"\bshould\b.*\bbe\s+banned\b", 20, "Ban demand"),
    (r"everyone\s+(is|are)\s+(wrong|stupid|crazy|dumb)", 25, "Takes claim"),
    (r"\bhot\s+take\b", 30, "Self-identified hot take"),
    (r"ratio['d]*", 25, "Already ratio'd"),
    (r"main\s+character", 20, "Main character energy"),
    (r"red\s+flag", 20, "Red flag discussion"),
    (r"gaslighting", 20, "Gaslighting discussion"),
    # Broad controversy/debate signals
    (r"\b(toxic|toxicity)\b", 20, "Toxicity discussion"),
    (r"\bcontroversial\b", 25, "Self-identified controversy"),
    (r"\bdebate\b", 15, "Debate topic"),
    (r"\b(boycott|cancel)\b", 25, "Boycott/cancel culture"),
    (r"\b(unpopular|against|hate|love|worst|best)\b.*\b(opinion|take|thing|part|move)\b", 20, "Strong opinion"),
    (r"(why|how)\s+(do|does|is|are|can)\s+\w+", 10, "Question framing"),
    (r"\b(ai|artificial\s+intelligence)\b", 15, "AI topic"),
    (r"\bindia\b.*\b(vs|versus|against)\b", 15, "India vs something"),
    (r"\b(modi|pm|bjp|congress|aap|tmc)\b", 15, "Political topic"),
    (r"\b(caste|religion|hindu|muslim|sikh)\b", 15, "Sensitive identity topic"),
    (r"\b(men|women|boys|girls|male|female)\b.*\b(should|can|why|how|always|never)\b", 15, "Gender war"),
    (r"\b(friendzone|simp|nice\s+guy|alpha|beta|sigma)\b", 25, "Dating culture war"),
    (r"\b(in\-laws|saas|bahu|mother\s*in\s*law)\b", 20, "In-law drama"),
    (r"\b(engagement|wedding|marriage|divorce)\b.*\b(bad|worst|toxic|red\s+flag|should)\b", 20, "Marriage drama"),
    (r"\bsmash\b.*\b(burger|not|overrated)\b", 20, "Food war"),
    (r"\b(indian\s+men|indian\s+women)\b", 25, "Indian gender discourse"),
    (r"\b(entrepreneur|founder|ceo|cto)\b.*\b(failed|fired|arrested|scam|fraud)\b", 25, "Founder downfall"),
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
    score = 30.0  # Base score — everything has SOME potential

    # Reddit topics from drama/kalesh subreddits get a base boost
    DRAMA_SUBS = {
        "subredditdrama", "indiaspeaks", "chodi", "unpopularopinion",
        "bollyblindsngossip", "corporateslavery", "india",
    }
    if topic.source == "reddit" and topic.subreddit and topic.subreddit.lower() in DRAMA_SUBS:
        score += 15
        logger.debug(f"Drama subreddit boost: +15 for r/{topic.subreddit}")

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
    if topic.comment_count > 500:
        score += 15
    elif topic.comment_count > 200:
        score += 10
    elif topic.comment_count > 50:
        score += 5

    # Divisiveness proxy: upvote_ratio far from 0.5 = people are split
    if 0.4 < topic.upvote_ratio < 0.95:
        score += 10  # Controversial upvote pattern

    # X/Twitter trends are inherently satirizable — they're controversial
    # enough to trend nationally/globally, which means people are fighting
    # over them. This is prime satire territory.
    if topic.source == "x":
        score += 35  # Big boost: trending = controversy = satire gold
        logger.debug(f"X trend satire boost: +35 for '{topic.title[:50]}'")

        # Hashtag topics are even better for one-liner satire
        if topic.title.startswith("#"):
            score += 10

    return max(0, min(score, 100))