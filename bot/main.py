"""
Kalesh Radar — Main Orchestrator
Called with: python -m bot.main --slot <morning|afternoon|evening|night>

Pipeline:
1. Fetch topics from all sources
2. Run safety gate
3. Score all safe topics
4. Select top N for this slot
5. Send briefing to Discord
6. Save to database
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from bot.config import SLOT_CONFIG, TOPICS_PER_SLOT
from bot.sources import fetch_all_topics
from bot.safety import check_safety
from bot.scoring import score_all_topics, select_top_topics
from bot.discord_bot import send_briefing_sync, send_error
from bot.db import save_topics, get_recent_urls, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kalesh-radar")


def run_slot(slot: str):
    """Execute the full pipeline for a single briefing slot."""
    logger.info(f"{'='*60}")
    logger.info(f"KALESH RADAR — {slot.upper()} slot")
    logger.info(f"{'='*60}")
    start_time = time.time()

    # ── 1. Fetch ──────────────────────────────────────────────────────────
    logger.info("Step 1: Fetching topics from all sources...")
    try:
        topics = fetch_all_topics()
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        sys.exit(1)

    if not topics:
        logger.warning("No topics fetched. Nothing to do.")
        try:
            send_error(slot, "No topics fetched from any source. Reddit or RSSHub may be unavailable.")
        except Exception:
            pass
        return

    logger.info(f"Fetched {len(topics)} raw topics")

    # ── 2. Dedup against recent sends ─────────────────────────────────────
    logger.info("Step 2: Deduplicating against recent sends...")
    try:
        recent_urls = get_recent_urls(hours=24)
        before_dedup = len(topics)
        topics = [t for t in topics if t.url not in recent_urls]
        logger.info(f"Dedup removed {before_dedup - len(topics)} recently-sent topics")
    except Exception as e:
        logger.warning(f"Dedup failed (non-fatal): {e}")

    # ── 3. Safety Gate ───────────────────────────────────────────────────
    logger.info("Step 3: Running safety gate...")
    safe_count = 0
    blocked_count = 0
    for topic in topics:
        try:
            check_safety(topic)
            if topic.safety_passed:
                safe_count += 1
            else:
                blocked_count += 1
        except Exception as e:
            logger.error(f"Safety check error for '{topic.title[:50]}': {e}")
            topic.safety_passed = False
            blocked_count += 1

    logger.info(f"Safety: {safe_count} passed, {blocked_count} blocked")

    # Filter to safe only
    safe_topics = [t for t in topics if t.safety_passed]

    if not safe_topics:
        logger.warning("All topics blocked by safety gate. Nothing to send.")
        try:
            send_error(slot, "All topics blocked by the safety gate. Nothing controversial enough or topics were too sensitive.")
        except Exception:
            pass
        return

    # ── 4. Score ─────────────────────────────────────────────────────────
    logger.info("Step 4: Scoring topics...")
    safe_topics = score_all_topics(safe_topics)

    # Log top 5 scores for debugging
    safe_topics.sort(key=lambda t: t.final_score, reverse=True)
    for t in safe_topics[:5]:
        logger.info(
            f"  [{t.final_score:.0f}] {t.title[:60]} "
            f"(E:{t.engagement_score:.0f} D:{t.divisiveness_score:.0f} "
            f"S:{t.satirizability_score:.0f} F:{t.freshness_score:.0f})"
        )

    # ── 5. Select Top N for this slot ────────────────────────────────────
    logger.info(f"Step 5: Selecting top {TOPICS_PER_SLOT} for '{slot}' slot...")
    selected = select_top_topics(safe_topics, slot)

    if not selected:
        logger.warning("No topics selected after slot filtering.")
        return

    for i, t in enumerate(selected):
        rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
        region = "🇮🇳" if t.region == "india" else "🌍"
        logger.info(
            f"  {rank} {region} [{t.final_score:.0f}] {t.title[:60]}"
        )

    # ── 6. Save to database ──────────────────────────────────────────────
    logger.info("Step 6: Saving to database...")
    try:
        save_topics(selected, slot)
    except Exception as e:
        logger.error(f"Database save failed (non-fatal): {e}")

    # ── 7. Send Discord briefing ─────────────────────────────────────────
    logger.info("Step 7: Sending Discord briefing...")
    send_briefing_sync(selected, slot)  # Let errors propagate — workflow should show red

    elapsed = time.time() - start_time
    logger.info(f"{'='*60}")
    logger.info(f"DONE — {slot.upper()} slot completed in {elapsed:.1f}s")
    logger.info(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Kalesh Radar — Controversy Briefing Bot")
    parser.add_argument(
        "--slot",
        required=True,
        choices=["morning", "afternoon", "evening", "night"],
        help="Which briefing slot to run",
    )
    parser.add_argument(
        "--all-slots",
        action="store_true",
        help="Run all 4 slots sequentially (for testing)",
    )
    args = parser.parse_args()

    if args.all_slots:
        for slot in ["morning", "afternoon", "evening", "night"]:
            run_slot(slot)
            print()  # Separator
    else:
        run_slot(args.slot)


if __name__ == "__main__":
    main()