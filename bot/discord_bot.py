"""
Discord bot — sends ranked topic briefings via Webhooks.
Uses webhooks instead of gateway client for reliability in CI/cron.
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

import requests

from bot.config import DISCORD_CHANNEL_MAP
from bot.sources.base import Topic

logger = logging.getLogger(__name__)

RANK_EMOJIS = ["🥇", "🥈", "🥉"]

SLOT_LABELS = {
    "morning": "☀️ MORNING BRIEFING — 9 AM",
    "afternoon": "🌤️ AFTERNOON BRIEFING — 1 PM",
    "evening": "🌆 EVENING BRIEFING — 5 PM",
    "night": "🌙 NIGHT BRIEFING — 9 PM",
}

SLOT_COLORS = {
    "morning": 0xF59E0B,    # Amber
    "afternoon": 0x3B82F6,  # Blue
    "evening": 0x8B5CF6,    # Purple
    "night": 0x6366F1,      # Indigo
}


def _score_bar(score: float, length: int = 10) -> str:
    filled = round(score / 100 * length)
    return "█" * filled + "░" * (length - filled)


def _region_badge(topic: Topic) -> str:
    return "🇮🇳 INDIA" if topic.region == "india" else "🌍 WORLDWIDE"


def _source_badge(topic: Topic) -> str:
    if topic.source == "reddit" and topic.subreddit:
        return f"Reddit r/{topic.subreddit}"
    elif topic.source == "x" and topic.curator:
        return f"X @{topic.curator}"
    elif topic.source == "hackernews":
        return f"HN ({topic.upvote_count} pts, {topic.comment_count} comments)"
    return topic.source.upper()


def _build_topic_embed(topic: Topic, rank: int) -> dict:
    """Build a Discord embed for a single topic."""
    rank_emoji = RANK_EMOJIS[rank - 1] if rank <= 3 else f"#{rank}"
    color = SLOT_COLORS.get("morning", 0x000000)

    embed = {
        "title": f"{rank_emoji}  {_region_badge(topic)}  |  {_source_badge(topic)}",
        "description": f"**{topic.title[:300]}**",
        "url": topic.url,
        "color": color,
        "fields": [],
        "footer": {"text": "🔥 = Comment   👀 = Watching   ❌ = Skip   💾 = Save"},
    }

    # Timestamp
    if topic.created_at:
        if topic.created_at.tzinfo is None:
            topic.created_at = topic.created_at.replace(tzinfo=timezone.utc)
        embed["timestamp"] = topic.created_at.isoformat()

    # Body snippet
    if topic.body and len(topic.body) > 10:
        body_snippet = topic.body[:300] + ("..." if len(topic.body) > 300 else "")
        embed["fields"].append({
            "name": "",
            "value": f"> {body_snippet}",
            "inline": False,
        })

    # Score breakdown
    embed["fields"].append({
        "name": "📊 Scores",
        "value": (
            f"🔥 Engagement: {_score_bar(topic.engagement_score)} {topic.engagement_score:.0f}/100\n"
            f"⚔️ Divisiveness: {_score_bar(topic.divisiveness_score)} {topic.divisiveness_score:.0f}/100\n"
            f"😏 Satire Potential: {_score_bar(topic.satirizability_score)} {topic.satirizability_score:.0f}/100\n"
            f"⏰ Freshness: {_score_bar(topic.freshness_score)} {topic.freshness_score:.0f}/100\n"
            f"**🏆 Final: {_score_bar(topic.final_score)} {topic.final_score:.0f}/100**"
        ),
        "inline": True,
    })

    # Metadata
    meta_parts = []
    if topic.comment_count:
        meta_parts.append(f"💬 {topic.comment_count} comments")
    if topic.reply_count:
        meta_parts.append(f"💬 {topic.reply_count} replies")
    if topic.like_count:
        meta_parts.append(f"❤️ {topic.like_count}")
    if topic.retweet_count:
        meta_parts.append(f"🔁 {topic.retweet_count}")
    meta_parts.append(f"⏱️ {topic.age_hours:.1f}h ago")

    embed["fields"].append({
        "name": "ℹ️",
        "value": " | ".join(meta_parts) if meta_parts else "No metadata",
        "inline": True,
    })

    return embed


def send_briefing_sync(topics: List[Topic], slot: str):
    """
    Send a briefing to the appropriate Discord channel via webhook.
    """
    webhook_url = DISCORD_CHANNEL_MAP.get(slot)
    if not webhook_url:
        logger.error(f"No webhook URL configured for slot '{slot}'")
        raise ValueError(f"No webhook URL for slot '{slot}'. "
                         f"Set WEBHOOK_MORNING, WEBHOOK_AFTERNOON, WEBHOOK_EVENING, WEBHOOK_NIGHT.")

    if not topics:
        # Send a "no topics" status message so user knows bot is alive
        _send_status(webhook_url, slot, "No controversial topics found this cycle. "
                      "Sources may be unavailable or all topics were blocked by the safety gate.")
        return

    # Send header
    header = f"**{SLOT_LABELS.get(slot, slot.upper())}**\n" \
             f"```fix\n{len(topics)} topics ready for your takes.\n```"
    _post_webhook(webhook_url, {"content": header})

    # Send each topic
    for i, topic in enumerate(topics):
        embed = _build_topic_embed(topic, i + 1)
        _post_webhook(webhook_url, {"embeds": [embed]})

    logger.info(f"Briefing sent for slot '{slot}': {len(topics)} topics")


def send_error(slot: str, error_message: str):
    """Send an error message to the channel."""
    webhook_url = DISCORD_CHANNEL_MAP.get(slot)
    if webhook_url:
        _send_status(webhook_url, slot, f"⚠️ Error: {error_message}")


def _send_status(webhook_url: str, slot: str, message: str):
    """Send a plain text status message."""
    _post_webhook(webhook_url, {
        "content": f"**{SLOT_LABELS.get(slot, slot.upper())}**\n>>> {message}"
    })


def _post_webhook(webhook_url: str, payload: dict):
    """POST a message to a Discord webhook."""
    resp = requests.post(webhook_url, json=payload, timeout=15)
    if resp.status_code == 204:
        logger.debug("Webhook sent successfully")
    else:
        logger.error(f"Webhook failed: {resp.status_code} {resp.text}")
        raise RuntimeError(f"Discord webhook failed: {resp.status_code} {resp.text}")