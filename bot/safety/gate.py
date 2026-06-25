"""
Safety gate — prevents topics from reaching you that could get your
account banned or cause real harm.

Two layers:
1. Rule-based: keyword/regex blocks for known-dangerous categories
2. LLM-based: nuanced judgment for borderline cases

A topic must pass BOTH layers. If either says UNSAFE, it's filtered out.
"""

import json
import logging
import re
from typing import Optional, Tuple

from bot.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

# ── BLOCKLIST: Regex patterns that immediately mark a topic as UNSAFE ─────────

HARD_BLOCKS = [
    # Deaths and tragedies
    r"\b\d+\s+(people|persons?|kids?|children|soldiers?|civilians?)\s+(killed|died|dead|found dead|bodies?)\b",
    r"\b(mass\s+shooting|school\s+shooting|terrorist?\s+attack|bombing)\b",
    r"\bsuicide\b(?!.*\b(joke|meme|funny)\b)",  # Allow if clearly being memed, block otherwise
    r"\b(mass\s+casualt|genocide|ethnic\s+cleansing)\b",

    # Sexual violence — absolute block
    r"\b(raped?|gang.?rape|sexual\s+assault|molested?|sa\s+alleg)\b",
    r"\b(child\s+(abuse|molest|exploit)|minor\s+(abuse|assault))\b",

    # Hate speech triggers (India-specific legal risk)
    r"\b(caste\s+violence|caste\s+riot|communal\s+violence|communal\s+riot)\b",
    r"\b(lynching|mob\s+lynch)\b",

    # Active armed conflict
    r"\b(war\s+declared|invasion\s+of|missile\s+strike|airstrike)\b.*\b(casualt|death|kill)\b",

    # Natural disasters with casualties
    r"\b(earthquake|flood|tsunami|cyclone|landslide)\b.*\b(\d+\s+(dead|killed|missing|died))\b",

    # Minors in negative context
    r"\b(minor|underage|child|kid)\b.*\b(abuse|exploit|assault|harass)\b",
]

# ── WARNLIST: Patterns that need LLM review but aren't auto-blocked ──────────

WARN_PATTERNS = [
    r"\bdeath\b",
    r"\bkilled\b",
    r"\bdied\b",
    r"\bsuicide\b",
    r"\bmental\s+health\b",
    r"\bdomestic\s+violence\b",
    r"\breligion\b.*\b(hate|attack|kill|ban)\b",
    r"\bhindu\b.*\b(muslim|christian|sikh)\b",
    r"\bmuslim\b.*\b(hindu|christian|sikh)\b",
    r"\bdalit\b.*\b(attack|violence|caste)\b",
    r"\brape\b",
    r"\bmetoo\b",
    r"\bgender\b.*\b(violence|attack)\b",
]


def check_safety(topic: Topic) -> bool:
    """
    Run safety gate on a topic.
    Returns True if safe to comment on, False if should be filtered.
    """
    text = (topic.title + " " + topic.body).lower()
    text = " ".join(text.split())  # Normalize whitespace

    # Layer 1: Hard blocks (regex)
    for pattern in HARD_BLOCKS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.info(f"SAFETY BLOCK (hard) for: {topic.title[:80]}")
            topic.safety_passed = False
            return False

    # Layer 2: Check if topic hits any warn patterns
    needs_llm_review = any(
        re.search(p, text, re.IGNORECASE) for p in WARN_PATTERNS
    )

    if needs_llm_review:
        # Layer 2b: LLM review for borderline cases
        if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
            try:
                safe = _llm_safety_check_openai(topic)
                topic.safety_passed = safe
                return safe
            except Exception as e:
                logger.warning(f"LLM safety check failed: {e}")
                # When in doubt, block it
                topic.safety_passed = False
                return False
        elif LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
            try:
                safe = _llm_safety_check_anthropic(topic)
                topic.safety_passed = safe
                return safe
            except Exception as e:
                logger.warning(f"LLM safety check failed: {e}")
                topic.safety_passed = False
                return False
        else:
            # No LLM available and topic hits warn patterns — be cautious, block
            logger.info(f"SAFETY BLOCK (no LLM, warn pattern matched) for: {topic.title[:80]}")
            topic.safety_passed = False
            return False

    # Passed all checks
    topic.safety_passed = True
    return True


def _build_safety_prompt(topic: Topic) -> str:
    source_label = f"r/{topic.subreddit}" if topic.source == "reddit" else f"@{topic.curator}"
    return f"""You are a safety filter for a satirical social media commenter. 
This person comments ONLY in a humorous, sarcastic, non-serious tone on trending/controversial topics.

Evaluate if it is SAFE for this person to comment on this topic with humor/satire.

Source: {source_label}
Region: {"[INDIA]" if topic.is_india else "[WORLDWIDE]"}
Title: {topic.title}
Body: {topic.body[:300]}

Consider:
- Would a sarcastic/humorous comment here be in extremely poor taste?
- Could commenting lead to the account being banned (especially on Indian social platforms where certain topics are legally sensitive)?
- Is the topic about a recent tragedy, death, or sensitive personal matter where humor would be inappropriate?
- Even if the topic is controversial, can humor be applied without crossing ethical/legal lines?

IMPORTANT: This is an India-focused account. Topics involving religious tension, caste violence, 
sexual assault, or communal riots carry LEGAL risk in India. Be extra cautious.

Respond ONLY with JSON:
{{"safe": true/false, "reason": "<brief explanation>"}}

When in doubt, return {{"safe": false, ...}}."""


def _llm_safety_check_openai(topic: Topic) -> bool:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = _build_safety_prompt(topic)

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a content safety evaluator. Respond in valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=100,
    )

    content = response.choices[0].message.content.strip()
    return _parse_safety_response(content, topic)


def _llm_safety_check_anthropic(topic: Topic) -> bool:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_safety_prompt(topic)

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    content = response.content[0].text.strip()
    return _parse_safety_response(content, topic)


def _parse_safety_response(content: str, topic: Topic) -> bool:
    try:
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        data = json.loads(json_str)
        safe = bool(data.get("safe", False))
        reason = data.get("reason", "")
        if not safe:
            logger.info(f"SAFETY BLOCK (LLM) for: {topic.title[:80]} — {reason}")
        return safe
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse LLM safety response, blocking by default: {e}")
        return False