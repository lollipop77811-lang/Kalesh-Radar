"""
SQLite database layer.
Stores topics, user reactions, and preference data.
"""

import json
import logging
import sqlite3
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from bot.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating tables if needed."""
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else "data", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            subreddit TEXT,
            curator TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            body TEXT,
            comment_count INTEGER DEFAULT 0,
            upvote_count INTEGER DEFAULT 0,
            downvote_count INTEGER DEFAULT 0,
            upvote_ratio REAL DEFAULT 1.0,
            reply_count INTEGER DEFAULT 0,
            like_count INTEGER DEFAULT 0,
            retweet_count INTEGER DEFAULT 0,
            created_at TEXT,
            fetched_at TEXT,
            engagement_score REAL DEFAULT 0,
            divisiveness_score REAL DEFAULT 0,
            satirizability_score REAL DEFAULT 0,
            freshness_score REAL DEFAULT 0,
            final_score REAL DEFAULT 0,
            safety_passed INTEGER,
            is_india INTEGER DEFAULT 0,
            region TEXT DEFAULT 'worldwide',
            slot TEXT,
            discord_message_id TEXT,
            user_reaction TEXT,
            sent_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_topics_url ON topics(url);
        CREATE INDEX IF NOT EXISTS idx_topics_slot ON topics(slot);
        CREATE INDEX IF NOT EXISTS idx_topics_sent_at ON topics(sent_at);

        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT
        );
    """)
    conn.commit()


def save_topics(topics: List[Any], slot: str, conn: Optional[sqlite3.Connection] = None) -> None:
    """Save a list of scored topics to the database."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    now = datetime.now(timezone.utc).isoformat()

    try:
        for topic in topics:
            data = topic.to_dict() if hasattr(topic, "to_dict") else topic

            conn.execute("""
                INSERT OR IGNORE INTO topics (
                    source, subreddit, curator, title, url, body,
                    comment_count, upvote_count, downvote_count, upvote_ratio,
                    reply_count, like_count, retweet_count,
                    created_at, fetched_at,
                    engagement_score, divisiveness_score, satirizability_score, freshness_score,
                    final_score, safety_passed, is_india, region, slot, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("source"), data.get("subreddit"), data.get("curator"),
                data.get("title"), data.get("url"), data.get("body"),
                data.get("comment_count", 0), data.get("upvote_count", 0),
                data.get("downvote_count", 0), data.get("upvote_ratio", 1.0),
                data.get("reply_count", 0), data.get("like_count", 0),
                data.get("retweet_count", 0),
                data.get("created_at"), data.get("fetched_at"),
                data.get("engagement_score", 0), data.get("divisiveness_score", 0),
                data.get("satirizability_score", 0), data.get("freshness_score", 0),
                data.get("final_score", 0),
                1 if data.get("safety_passed") else 0,
                1 if data.get("is_india") else 0,
                data.get("region", "worldwide"),
                slot, now,
            ))
        conn.commit()
        logger.info(f"Saved {len(topics)} topics for slot '{slot}'")
    finally:
        if close_after:
            conn.close()


def update_discord_message_id(topic_id: int, message_id: str,
                               conn: Optional[sqlite3.Connection] = None) -> None:
    """Link a Discord message ID to a topic."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        conn.execute("UPDATE topics SET discord_message_id = ? WHERE id = ?",
                      (message_id, topic_id))
        conn.commit()
    finally:
        if close_after:
            conn.close()


def update_user_reaction(message_id: str, reaction: str,
                          conn: Optional[sqlite3.Connection] = None) -> None:
    """Record a user's reaction to a topic."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        conn.execute(
            "UPDATE topics SET user_reaction = ? WHERE discord_message_id = ?",
            (reaction, message_id),
        )
        conn.commit()
        logger.info(f"User reaction '{reaction}' recorded for message {message_id}")
    finally:
        if close_after:
            conn.close()


def get_recent_urls(hours: int = 24,
                     conn: Optional[sqlite3.Connection] = None) -> set:
    """Get URLs of topics sent in the last N hours (for dedup)."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        rows = conn.execute(
            "SELECT url FROM topics WHERE sent_at > datetime('now', ?)",
            (f"-{hours} hours",),
        ).fetchall()
        return {row["url"] for row in rows}
    finally:
        if close_after:
            conn.close()


def get_preference_summary(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Compute user preference summary from reaction history."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        rows = conn.execute("""
            SELECT region, source, subreddit, user_reaction, COUNT(*) as count
            FROM topics
            WHERE user_reaction IS NOT NULL
            GROUP BY region, source, subreddit, user_reaction
        """).fetchall()

        summary = {
            "total_engaged": 0,
            "total_skipped": 0,
            "region_engagement": {"india": 0, "worldwide": 0},
            "source_engagement": {},
            "subreddit_engagement": {},
        }

        for row in rows:
            reaction = row["user_reaction"]
            count = row["count"]
            if reaction in ("fire", "eyes", "save"):
                summary["total_engaged"] += count
                summary["region_engagement"][row["region"]] += count
                sub = row["subreddit"] or row["source"]
                summary["source_engagement"][sub] = (
                    summary["source_engagement"].get(sub, 0) + count
                )
                if row["subreddit"]:
                    summary["subreddit_engagement"][row["subreddit"]] = (
                        summary["subreddit_engagement"].get(row["subreddit"], 0) + count
                    )
            elif reaction in ("skip", "x"):
                summary["total_skipped"] += count

        return summary
    finally:
        if close_after:
            conn.close()