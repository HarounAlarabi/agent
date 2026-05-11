"""Trend Intelligence storage — extends content_engine.db with trend tables."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path


class TrendStorage:
    """Persists extracted trend patterns and monitored creator handles.

    Raw source text is NEVER stored — only hashes and abstract pattern metadata.
    """

    def __init__(self, db_path: Path):
        self._db = str(db_path)
        self._init_tables()

    def _connect(self):
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trends (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    fetched_at         TEXT NOT NULL,
                    source             TEXT,
                    source_hash        TEXT NOT NULL UNIQUE,
                    topic_context      TEXT,
                    hook_type          TEXT,
                    emotional_tone     TEXT,
                    content_format     TEXT,
                    engagement_trigger TEXT,
                    narrative_structure TEXT,
                    topic_angle        TEXT,
                    raw_engagement     REAL DEFAULT 0,
                    age_hours          REAL DEFAULT 0,
                    velocity_score     REAL DEFAULT 0,
                    freshness_score    REAL DEFAULT 0,
                    relevance_score    REAL DEFAULT 0,
                    overall_score      REAL DEFAULT 0,
                    status             TEXT DEFAULT 'new',
                    tags               TEXT DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS monitored_creators (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform   TEXT DEFAULT 'x',
                    handle     TEXT NOT NULL,
                    added_at   TEXT NOT NULL,
                    active     INTEGER DEFAULT 1,
                    UNIQUE(platform, handle)
                );

                CREATE TABLE IF NOT EXISTS trend_perspectives (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at          TEXT NOT NULL,
                    trend_id            INTEGER REFERENCES trends(id),
                    angle               TEXT,
                    content             TEXT,
                    language            TEXT,
                    tone                TEXT,
                    originality_passed  INTEGER DEFAULT 1,
                    voice_corrected     INTEGER DEFAULT 0,
                    draft_id            INTEGER,
                    posted              INTEGER DEFAULT 0
                );
            """)

    # ── Trends ────────────────────────────────────────────────────────────────

    def save_trend(self, trend: dict) -> int | None:
        """Return new row id, or None if source_hash already exists."""
        now = datetime.now().isoformat()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO trends
                       (fetched_at, source, source_hash, topic_context, hook_type,
                        emotional_tone, content_format, engagement_trigger,
                        narrative_structure, topic_angle, raw_engagement, age_hours,
                        velocity_score, freshness_score, relevance_score, overall_score,
                        status, tags)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        now,
                        trend.get("source", ""),
                        trend["source_hash"],
                        trend.get("topic_context", ""),
                        trend.get("hook_type", ""),
                        trend.get("emotional_tone", ""),
                        trend.get("content_format", ""),
                        trend.get("engagement_trigger", ""),
                        trend.get("narrative_structure", ""),
                        trend.get("topic_angle", ""),
                        float(trend.get("raw_engagement", 0)),
                        float(trend.get("age_hours", 0)),
                        float(trend.get("velocity_score", 0)),
                        float(trend.get("freshness_score", 0)),
                        float(trend.get("relevance_score", 0)),
                        float(trend.get("overall_score", 0)),
                        "new",
                        json.dumps(trend.get("tags", [])),
                    ),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_trends(
        self,
        status: str | None = "new",
        limit: int = 50,
        min_score: float = 0.0,
    ) -> list[dict]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM trends WHERE status=? AND overall_score>=?
                       ORDER BY overall_score DESC LIMIT ?""",
                    (status, min_score, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM trends WHERE overall_score>=?
                       ORDER BY overall_score DESC LIMIT ?""",
                    (min_score, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def mark_trend_used(self, trend_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE trends SET status='used' WHERE id=?", (trend_id,))

    def dismiss_trend(self, trend_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE trends SET status='dismissed' WHERE id=?", (trend_id,))

    def clear_old_trends(self, keep_days: int = 3) -> int:
        cutoff = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        cutoff_str = cutoff.isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM trends WHERE fetched_at < ? AND status != 'used'",
                (cutoff_str,),
            )
            return cur.rowcount

    def trend_count(self, status: str = "new") -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM trends WHERE status=?", (status,)
            ).fetchone()[0]

    # ── Monitored creators ────────────────────────────────────────────────────

    def add_creator(self, handle: str, platform: str = "x") -> bool:
        handle = handle.lstrip("@").strip().lower()
        now = datetime.now().isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO monitored_creators (platform, handle, added_at) VALUES (?,?,?)",
                    (platform, handle, now),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_creator(self, handle: str, platform: str = "x") -> None:
        handle = handle.lstrip("@").strip().lower()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM monitored_creators WHERE platform=? AND handle=?",
                (platform, handle),
            )

    def get_creators(self, platform: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM monitored_creators WHERE platform=? AND active=1 ORDER BY added_at DESC",
                    (platform,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM monitored_creators WHERE active=1 ORDER BY platform, added_at DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    # ── Perspectives ──────────────────────────────────────────────────────────

    def save_perspective(self, data: dict) -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO trend_perspectives
                   (created_at, trend_id, angle, content, language, tone,
                    originality_passed, voice_corrected, draft_id)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    data.get("trend_id"),
                    data.get("angle", ""),
                    data.get("content", ""),
                    data.get("language", "English"),
                    data.get("tone", ""),
                    int(data.get("originality_passed", True)),
                    int(data.get("voice_corrected", False)),
                    data.get("draft_id"),
                ),
            )
            return cur.lastrowid

    def mark_perspective_posted(self, perspective_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE trend_perspectives SET posted=1 WHERE id=?", (perspective_id,)
            )

    def get_recent_perspectives(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trend_perspectives ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
