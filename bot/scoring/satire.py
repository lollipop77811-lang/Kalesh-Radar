"""
Satirizability scorer — uses LLM to assess humor/satire potential.
Falls back to rule-based scoring if no LLM API key is configured.
"""

import json
import logging
import re
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

# ── POLITICAL BOOSTERS (highest priority — user wants political topics) ──────
POLITICAL_BOOSTERS = [
    # Indian political parties + leaders
    (r"\b(bjp|congress|aap|tmc|bsp|sp|bsp|ncp|shiv\s*sena|dmk|aiadmk|tdp|jd[uv])\b", 20, "Political party"),
    (r"\b(modi|narendra\s*modi|pm\s*modi|na\s*mo)\b", 20, "Modi mention"),
    (r"\b(rahul\s*gandhi|rahul\s*gandhi)\b", 20, "Rahul Gandhi mention"),
    (r"\b(amit\s*shah|yogi\s*adityanath|kejriwal|mamata|mamta|arvind)\b", 20, "Political leader"),
    (r"\b(rahul\s*gandhi|priyanka\s*gandhi|pappu|raGa)\b", 18, "Gandhi family"),
    (r"\b(oppo[sx]ition|ruling\s*party|govt|government|parliament)\b", 15, "Govt/opposition"),
    (r"\b(election|vote|voting|poll|ballot|campaign|rally)\b", 15, "Election/political"),
    (r"\b(polio|mandir|masjid|ayodhya|ram\s*mandir|cauvery|article\s*370|cabinet|budget|tax)\b", 18, "Political flashpoint"),
    (r"\b(bjp\s*win|congress\s*win|winning|still\s*winning|hate\s*that\s*party)\b", 22, "Electoral controversy"),
    (r"\b(propaganda|narrative|agenda|pappu|chowkidar|anti\s*national|sickular|librandu)\b", 22, "Political slang"),
    (r"\b(anti\s*incumbent|pro\s*incumbent|incumbent|anti\s*govt|pro\s*govt)\b", 18, "Anti/pro govt sentiment"),
    (r"\b(swiss\s*bank|black\s*money|scam|corruption|scandal)\b.*\b(india|govt|minister|party)\b", 22, "Political scandal"),
    (r"\b(democracy|democratic|dictator|fascist|communist|capitalist|leftist|rightist)\b", 15, "Political ideology"),
    # Worldwide political
    (r"\b(trump|biden|harris|obama)\b", 18, "US political figure"),
    (r"\b(republican|democrat|conservative|liberal)\b.*\b(party|govt|policy)\b", 15, "US politics"),
    (r"\b(parliament|senate|congress)\b.*\b(pass|reject|ban|bill|law)\b", 15, "Legislative action"),
    # Policy/political economy
    (r"\b(gst|demonetis|note\s*ban|up[as]c|neet|caa|nrc)\b", 20, "Indian policy hot-button"),
    (r"\b(free\s*bie|freebie|revdi|welfare|subsidy)\b.*\b(vote|election|bjp|congress|govt)\b", 22, "Freebie politics"),
]

# ── BILLIONAIRE / TECH ABSURDITY BOOSTERS ───────────────────────────────────
BILLIONAIRE_BOOSTERS = [
    (r"\b(bezos|jeff\s*bezos|musk|elon\s*musk|gates|bill\s*gates|zuck|zuckerberg|ambani|adani|mukesh|tata)\b", 18, "Billionaire mention"),
    (r"\b(ceo|cto|cfo|founder|co.?founder)\b.*\b(say|said|believe|think|claim|want|said)\b", 25, "CEO controversial take"),
    (r"\b(ai|artificial\s*intelligence)\b.*\b(water|human|priority|replace|job|take|steal)\b", 25, "AI vs humans absurdity"),
    (r"\b(sold.*data|data.*sold|data.*breach|data.*leak|privacy|meta.*data)\b", 22, "Data scam/sale"),
    (r"\b(made.*ceo|appointed.*head|became.*global|promoted)\b.*\b(indian|india|desi)\b", 25, "Indian CEO pride irony"),
    (r"\b(cheering|celebrating|proud|jai\s*ho)\b.*\b(ceo|head|global|foreign)\b", 22, "National pride irony"),
    (r"\b(tech\s*bro|startup\s*bro|silicon\s*valley)\b", 18, "Tech bro culture"),
    (r"\b(hustle\s*culture|grind\s*set|passion|sunday.*work|work.*sunday)\b", 20, "Hustle culture absurdity"),
]

# ── SYSTEMIC IRONY / ECONOMY BOOSTERS ───────────────────────────────────────
SYSTEMIC_IRONY_BOOSTERS = [
    (r"\b(scammer|scam|fraud|fraudster)\b", 18, "Scammer mention"),
    (r"\b(remote\s*job|18\s*dollar|\$18|freelanc|gig)\b.*\b(economy|messed|scam)\b", 25, "Economy absurdity"),
    (r"\b(economy|recession|inflation|unemployment|layoff)\b", 15, "Economy topic"),
    (r"\b(therapy|mental\s*health|counseling|depression|anxiety)\b.*\b(afford|cheap|free|under|rupee|₹)\b", 22, "Mental health systemic irony"),
    (r"\b(can'?t\s*afford|too\s*expensive|no\s*money|broke|budget|cheap)\b.*\b(therapy|doctor|hospital|medicine)\b", 22, "Healthcare affordability"),
    (r"\b(under\s*₹|under\s*500|under\s*1000|free|pro\s*bono)\b.*\b(therapy|treatment|doctor)\b", 20, "Budget services"),
]

# ── CULTURAL / FAMILY DRAMA BOOSTERS ────────────────────────────────────────
CULTURAL_BOOSTERS = [
    (r"\bindian\s*(mom|moms|mother|mothers|parents|dad|father|families|family|husband|wife|men|women|boys|girls)\b", 22, "Indian cultural generalization"),
    (r"\b(mom|mother|mummy|amma|aai)\b.*\b(obsess|control|dominat|son|boy|married)\b", 22, "Mom-son dynamic"),
    (r"\b(dad|father|papa|baap)\b.*\b(obsess|control|dominat|daughter|girl)\b", 20, "Dad-daughter dynamic"),
    (r"\b(in.?law|saas|bahu|sasural|mother\s*in\s*law|father\s*in\s*law)\b", 20, "In-law drama"),
    (r"\b(engagement|wedding|marriage|shaadi|vivah|divorce|talaaq)\b.*\b(bad|worst|toxic|red\s*flag|should|why|how)\b", 20, "Marriage drama"),
    (r"\b(arranged\s*marriage|love\s*marriage|shaadi)\b", 20, "Marriage system debate"),
    (r"\b(joint\s*family|nuclear\s*family|living\s*with\s*parents)\b", 18, "Family structure debate"),
    (r"\b(why\s+(are|is|do)\s+(indian|desi))\b", 20, "Indian culture why-question"),
    (r"\b(indian\s+culture|desi\s+culture|our\s+culture|culture\s*(is|are|makes))\b", 18, "Cultural commentary"),
    (r"\b(survival\s*instinct|common\s*sense|street\s*smart)\b", 20, "Survival/common sense debate"),
    (r"\b(obeys|obedient|submissive|respect\s*your\s*elders|honor|honour)\b", 18, "Traditional values debate"),
    (r"\b(son\s*preference|male\s*child|beta|beti|ladka|ladki)\b", 20, "Gender preference"),
]

# ── GENDER WAR BOOSTERS ─────────────────────────────────────────────────────
GENDER_WAR_BOOSTERS = [
    (r"\b(women|woman|girl|girls|female)\b.*\b(0|zero|no|don'?t|never|can'?t)\b.*\b(survival|sense|logic|brain|drive|know)\b", 30, "Anti-women generalization"),
    (r"\b(men|man|boy|boys|male)\b.*\b(0|zero|no|don'?t|never|can'?t)\b.*\b(survival|sense|logic|brain|drive|know)\b", 30, "Anti-men generalization"),
    (r"\b(indian\s+men|indian\s+women|desi\s+men|desi\s+women)\b", 25, "Indian gender discourse"),
    (r"\b(friendzone|simp|nice\s+guy|alpha|beta|sigma|chad|virgin|incel)\b", 25, "Dating culture war"),
    (r"\b(tinder|bumble|dating\s*app|matrimony|shaadi\.com)\b", 18, "Dating app discourse"),
    (r"\b(red\s*flag|green\s*flag|beige\s*flag)\b", 18, "Flag discourse"),
    (r"\b(gaslight|narcissist|toxic|manipulat)\b", 18, "Relationship psychology"),
    (r"\b(men\s+are|women\s+are|boys\s+are|girls\s+are)\b.*\b(all|always|never|just|only)\b", 25, "Gender generalization"),
    (r"\b(50.*50|equal.*rights|gender.*equal|feminis|misogyn|misandry|patriarchy|matriarchy)\b", 20, "Gender politics"),
]

# ── EXISTING GENERAL BOOSTERS ───────────────────────────────────────────────
GENERAL_BOOSTERS = [
    # India-specific kalesh
    (r"\bCEO\b.*\b(work|passion|sunday|weekend|grind|hustle)\b", 30, "CEO tone-deaf"),
    (r"\blinkedin\b", 25, "LinkedIn post"),
    (r"\bunpopular\s+opinion\b", 25, "Self-identified controversy"),
    (r"\bnepotism\b", 25, "Nepotism angle"),
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
    (r"\b(toxic|toxicity)\b", 20, "Toxicity discussion"),
    (r"\bcontroversial\b", 25, "Self-identified controversy"),
    (r"\bdebate\b", 15, "Debate topic"),
    (r"\b(boycott|cancel)\b", 25, "Boycott/cancel culture"),
    (r"\b(unpopular|against|hate|love|worst|best)\b.*\b(opinion|take|thing|part|move)\b", 20, "Strong opinion"),
    (r"\b(ai|artificial\s*intelligence)\b", 15, "AI topic"),
    (r"\bindia\b.*\b(vs|versus|against)\b", 15, "India vs something"),
    (r"\b(caste|religion|hindu|muslim|sikh)\b", 15, "Sensitive identity topic"),
    (r"\bsmash\b.*\b(burger|not|overrated)\b", 20, "Food war"),
    (r"\b(entrepreneur|founder|ceo|cto)\b.*\b(failed|fired|arrested|scam|fraud)\b", 25, "Founder downfall"),
    (r"\bgenuine\s+question\b", 15, "Genuine question framing"),
    (r"\b(how\s+(is|are|do|does)|why\s+(is|are|do|does|can))\b", 8, "Question framing"),
    (r"\b(indian\s+ceo|desi\s+ceo|indian\s+cto|global\s+head)\b.*\b(meta|google|microsoft|apple|amazon|whatsapp)\b", 28, "Indian tech CEO at Big Tech"),
    (r"\b(millions?\s+of\s+indians|crores?\s+of\s+indians|indian\s+users)\b.*\b(data|sold|leaked|breach|meta)\b", 28, "Indian data exploitation"),
]

# Flatten all boosters into one list for iteration
ALL_BOOSTERS = POLITICAL_BOOSTERS + BILLIONAIRE_BOOSTERS + SYSTEMIC_IRONY_BOOSTERS + CULTURAL_BOOSTERS + GENDER_WAR_BOOSTERS + GENERAL_BOOSTERS

# Topics that are NEVER satirizable
SATIRE_KILLERS = [
    r"\b(died|death|killed|murder|rape|assault|suicide|terror|attack|crash|accident)\b.*\b(child|children|kid|minor)\b",
    r"\bsuicide\b.*\b(prevention|hotline|help)\b",
    r"\bmass\s+shooting\b",
    r"\bterrorist\s+attack\b",
]


def _score_rules(topic: Topic) -> float:
    """Rule-based satirizability scoring (no LLM needed)."""
    text = (topic.title + " " + topic.body).lower()
    score = 30.0  # Base score — everything has SOME potential

    # ── Subreddit boost tiers ────────────────────────────────────────────
    # Political subs — highest boost
    POLITICAL_SUBS = {
        "indiapolitics", "politicalindia", "indianews", "realindia",
        "india", "indiaspeaks", "chodi", "liberalmarxist", "indiadiscussion",
    }
    # Kalesh/gender/cultural goldmines
    KALESH_SUBS = {
        "indiamemes", "indiangirlsontinder", "indiadankmemes", "indiaafterdark",
        "twoxindia", "bollyblindsngossip", "desimeta",
    }
    # Drama/controversy subs
    DRAMA_SUBS = {
        "subredditdrama", "unpopularopinion", "corporateslavery",
        "antiwork", "trueoffmychest",
    }

    if topic.source == "reddit" and topic.subreddit:
        sub_lower = topic.subreddit.lower()
        if sub_lower in POLITICAL_SUBS:
            score += 20
            logger.debug(f"Political subreddit boost: +20 for r/{topic.subreddit}")
        elif sub_lower in KALESH_SUBS:
            score += 18
            logger.debug(f"Kalesh subreddit boost: +18 for r/{topic.subreddit}")
        elif sub_lower in DRAMA_SUBS:
            score += 12
            logger.debug(f"Drama subreddit boost: +12 for r/{topic.subreddit}")
        elif sub_lower in {"indiatech", "technology"}:
            score += 8
            logger.debug(f"Tech subreddit boost: +8 for r/{topic.subreddit}")

    # Check for satire killers first
    for killer_pattern in SATIRE_KILLERS:
        if re.search(killer_pattern, text, re.IGNORECASE):
            logger.debug(f"Satire killer matched for: {topic.title[:50]}")
            return 5.0

    # Apply all boosters (capped at +30 per category to prevent stacking)
    category_scores = {
        "political": 0, "billionaire": 0, "systemic": 0,
        "cultural": 0, "gender": 0, "general": 0,
    }
    category_ranges = {
        "political": POLITICAL_BOOSTERS,
        "billionaire": BILLIONAIRE_BOOSTERS,
        "systemic": SYSTEMIC_IRONY_BOOSTERS,
        "cultural": CULTURAL_BOOSTERS,
        "gender": GENDER_WAR_BOOSTERS,
        "general": GENERAL_BOOSTERS,
    }

    for cat_name, cat_boosters in category_ranges.items():
        for pattern, boost, label in cat_boosters:
            if re.search(pattern, text, re.IGNORECASE):
                category_scores[cat_name] += boost
                logger.debug(f"Satire boost [{label}]: +{boost} for '{topic.title[:50]}'")

    # Cap each category at 30 to prevent over-stacking, then add
    for cat_name, cat_score in category_scores.items():
        capped = min(cat_score, 30)
        score += capped

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

    # Divisiveness proxy: upvote_ratio far from 1.0 = people are split
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