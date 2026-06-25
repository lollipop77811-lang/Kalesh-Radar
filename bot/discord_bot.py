"""
Discord bot — sends ranked topic briefings and tracks user reactions.

Two modes of operation:
1. SCHEDULED: Script calls send_briefing() directly (for cron/CI usage)
2. INTERACTIVE: Bot listens for reactions on sent messages (for feedback loop)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

import discord

from bot.config import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_MAP
from bot.sources.base import Topic
from bot.db import update_discord_message_id, update_user_reaction

logger = logging.getLogger(__name__)

# Reactions the bot will add and track
REACTION_FIRE = "🔥"  # User wants to comment on this
REACTION_EYES = "👀"  # User is interested / considering
REACTION_SKIP = "❌"  # User will skip this
REACTION_SAVE = "💾"  # Save for later

TRACKED_REACTIONS = {REACTION_FIRE, REACTION_EYES, REACTION_SKIP, REACTION_SAVE}

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
    """Visual score bar like ████████░░."""
    filled = round(score / 100 * length)
    return "█" * filled + "░" * (length - filled)


def _region_badge(topic: Topic) -> str:
    return "🇮🇳 INDIA" if topic.region == "india" else "🌍 WORLDWIDE"


def _source_badge(topic: Topic) -> str:
    if topic.source == "reddit" and topic.subreddit:
        return f"Reddit r/{topic.subreddit}"
    elif topic.source == "x" and topic.curator:
        return f"X @{topic.curator}"
    return topic.source.upper()


def format_topic_message(topic: Topic, rank: int, total: int) -> dict:
    """
    Format a single topic as a Discord message payload.
    Returns a dict with 'content' and 'embed' keys.
    """
    rank_emoji = RANK_EMOJIS[rank - 1] if rank <= 3 else f"#{rank}"

    embed = discord.Embed(
        title=f"{rank_emoji}  {_region_badge(topic)}  |  {_source_badge(topic)}",
        description=f"**{topic.title[:200]}**",
        url=topic.url,
        color=SLOT_COLORS.get("morning", 0x000000),
        timestamp=topic.created_at if topic.created_at else None,
    )

    # If there's a body snippet, add it
    if topic.body and len(topic.body) > 10:
        body_snippet = topic.body[:200] + ("..." if len(topic.body) > 200 else "")
        embed.add_field(name="", value=f"> {body_snippet}", inline=False)

    # Score breakdown
    embed.add_field(
        name="📊 Scores",
        value=(
            f"🔥 Engagement: {_score_bar(topic.engagement_score)} {topic.engagement_score:.0f}/100\n"
            f"⚔️ Divisiveness: {_score_bar(topic.divisiveness_score)} {topic.divisiveness_score:.0f}/100\n"
            f"😏 Satire Potential: {_score_bar(topic.satirizability_score)} {topic.satirizability_score:.0f}/100\n"
            f"⏰ Freshness: {_score_bar(topic.freshness_score)} {topic.freshness_score:.0f}/100\n"
            f"**🏆 Final: {_score_bar(topic.final_score)} {topic.final_score:.0f}/100**"
        ),
        inline=True,
    )

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

    embed.add_field(name="ℹ️", value=" | ".join(meta_parts), inline=True)

    embed.set_footer(text="React: 🔥 Comment  👀 Watching  ❌ Skip  💾 Save")

    return {"embed": embed}


async def send_briefing(topics: List[Topic], slot: str):
    """
    Send a briefing to the appropriate Discord channel for the given slot.
    This is the main entry point called by the orchestrator.
    """
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not set. Cannot send briefing.")
        return

    channel_id = DISCORD_CHANNEL_MAP.get(slot)
    if not channel_id:
        logger.error(f"No channel configured for slot '{slot}'")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info(f"Discord bot logged in as {client.user}")
        channel = client.get_channel(int(channel_id))
        if channel is None:
            logger.error(f"Channel {channel_id} not found")
            await client.close()
            return

        # Send header
        header = f"**{SLOT_LABELS.get(slot, slot.upper())}**\n"
        header += f"```fix\n{len(topics)} topics ready for your takes.\n"
        header += f"React to each topic to track your engagement.\n```"
        await channel.send(header)

        # Send each topic as a separate message
        for i, topic in enumerate(topics):
            try:
                payload = format_topic_message(topic, i + 1, len(topics))
                msg = await channel.send(embed=payload["embed"])

                # Add reaction buttons
                for emoji in [REACTION_FIRE, REACTION_EYES, REACTION_SKIP, REACTION_SAVE]:
                    await msg.add_reaction(emoji)

                # Store message ID for reaction tracking
                # We'll use the topic URL to find it in DB
                topic._discord_message_id = msg.id

            except Exception as e:
                logger.error(f"Failed to send topic '{topic.title[:50]}': {e}")

        logger.info(f"Briefing sent for slot '{slot}': {len(topics)} topics")
        await client.close()

    @client.event
    async def on_raw_reaction_add(payload):
        """Track user reactions on bot messages."""
        if payload.user_id == client.user.id:
            return  # Ignore bot's own reactions

        if str(payload.emoji) not in TRACKED_REACTIONS:
            return

        # Map emoji to reaction label
        emoji_map = {
            REACTION_FIRE: "fire",
            REACTION_EYES: "eyes",
            REACTION_SKIP: "skip",
            REACTION_SAVE: "save",
        }
        reaction_label = emoji_map.get(str(payload.emoji), "unknown")

        try:
            update_user_reaction(str(payload.message_id), reaction_label)
            logger.info(f"User reaction: {payload.emoji} on message {payload.message_id}")
        except Exception as e:
            logger.error(f"Failed to record reaction: {e}")

    await client.start(DISCORD_BOT_TOKEN)


def send_briefing_sync(topics: List[Topic], slot: str):
    """Synchronous wrapper for send_briefing (for use in scripts/cron)."""
    asyncio.run(send_briefing(topics, slot))