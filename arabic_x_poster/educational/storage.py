"""Educational Content Storage — extends content_engine.db."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .types import Difficulty, EduContentType, LearningSeries, ResourceCategory


class EducationalStorage:

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
                CREATE TABLE IF NOT EXISTS edu_resources (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    added_at            TEXT NOT NULL,
                    url                 TEXT NOT NULL,
                    url_hash            TEXT NOT NULL UNIQUE,
                    title               TEXT,
                    topic               TEXT,
                    category            TEXT,
                    difficulty          TEXT,
                    usefulness_score    REAL DEFAULT 5,
                    summary             TEXT,
                    original_commentary TEXT,
                    key_strength        TEXT,
                    audience            TEXT,
                    tags                TEXT DEFAULT '[]',
                    status              TEXT DEFAULT 'saved'
                );

                CREATE TABLE IF NOT EXISTS edu_learning_series (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at   TEXT NOT NULL,
                    last_post_at TEXT,
                    name         TEXT NOT NULL,
                    topic        TEXT NOT NULL,
                    description  TEXT,
                    post_count   INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS edu_trusted_feed (
                    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                    fetched_at                  TEXT NOT NULL,
                    source_id                   TEXT NOT NULL,
                    source_platform             TEXT NOT NULL,
                    title                       TEXT,
                    url                         TEXT NOT NULL,
                    url_hash                    TEXT NOT NULL UNIQUE,
                    summary                     TEXT,
                    published                   TEXT,
                    tags                        TEXT DEFAULT '[]',
                    educational_category        TEXT,
                    difficulty_level            TEXT,
                    educational_quality_score   REAL DEFAULT 5.0,
                    developer_relevance_score   REAL DEFAULT 5.0,
                    status                      TEXT DEFAULT 'new',
                    post_generated              INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS edu_posts (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at   TEXT NOT NULL,
                    content_type TEXT,
                    topic        TEXT,
                    difficulty   TEXT,
                    language     TEXT,
                    content      TEXT,
                    is_thread    INTEGER DEFAULT 0,
                    thread_json  TEXT DEFAULT '[]',
                    resource_id  INTEGER REFERENCES edu_resources(id),
                    series_id    INTEGER REFERENCES edu_learning_series(id),
                    draft_id     INTEGER,
                    posted       INTEGER DEFAULT 0,
                    tweet_id     TEXT
                );
            """)

    # ── Resources ─────────────────────────────────────────────────────────────

    def save_resource(self, resource) -> int | None:
        """Returns new row id or None if URL already exists."""
        now = datetime.now().isoformat()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO edu_resources
                       (added_at, url, url_hash, title, topic, category, difficulty,
                        usefulness_score, summary, original_commentary, key_strength,
                        audience, tags)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        now,
                        resource.url,
                        resource.url_hash,
                        resource.title,
                        resource.topic,
                        resource.category.value if hasattr(resource.category, "value") else str(resource.category),
                        resource.difficulty.value if hasattr(resource.difficulty, "value") else str(resource.difficulty),
                        resource.usefulness_score,
                        resource.summary,
                        resource.original_commentary,
                        resource.key_strength,
                        resource.audience,
                        json.dumps(resource.tags),
                    ),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_resources(
        self,
        category: str | None = None,
        difficulty: str | None = None,
        min_score: float = 0.0,
        limit: int = 50,
    ) -> list[dict]:
        with self._connect() as conn:
            clauses = ["usefulness_score >= ?"]
            params: list = [min_score]
            if category:
                clauses.append("category = ?")
                params.append(category)
            if difficulty:
                clauses.append("difficulty = ?")
                params.append(difficulty)
            where = " AND ".join(clauses)
            rows = conn.execute(
                f"SELECT * FROM edu_resources WHERE {where} ORDER BY usefulness_score DESC, added_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_resource(self, resource_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM edu_resources WHERE id=?", (resource_id,))

    def resource_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM edu_resources").fetchone()[0]

    # ── Learning series ───────────────────────────────────────────────────────

    def create_series(self, name: str, topic: str, description: str = "") -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO edu_learning_series (created_at, name, topic, description)
                   VALUES (?,?,?,?)""",
                (now, name, topic, description),
            )
            return cur.lastrowid

    def get_series(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM edu_learning_series ORDER BY last_post_at DESC, created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def increment_series(self, series_id: int) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE edu_learning_series SET post_count=post_count+1, last_post_at=? WHERE id=?",
                (now, series_id),
            )

    def delete_series(self, series_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE edu_posts SET series_id=NULL WHERE series_id=?", (series_id,))
            conn.execute("DELETE FROM edu_learning_series WHERE id=?", (series_id,))

    # ── Educational posts ─────────────────────────────────────────────────────

    def save_edu_post(self, data: dict) -> int:
        now = datetime.now().isoformat()
        thread_tweets = data.get("thread_tweets", [])
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO edu_posts
                   (created_at, content_type, topic, difficulty, language, content,
                    is_thread, thread_json, resource_id, series_id, draft_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    data.get("content_type", ""),
                    data.get("topic", ""),
                    data.get("difficulty", ""),
                    data.get("language", "English"),
                    data.get("content", ""),
                    int(data.get("is_thread", False)),
                    json.dumps(thread_tweets),
                    data.get("resource_id"),
                    data.get("series_id"),
                    data.get("draft_id"),
                ),
            )
            return cur.lastrowid

    def mark_posted(self, edu_post_id: int, tweet_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE edu_posts SET posted=1, tweet_id=? WHERE id=?",
                (tweet_id, edu_post_id),
            )

    def get_recent_edu_posts(self, limit: int = 20, series_id: int | None = None) -> list[dict]:
        with self._connect() as conn:
            if series_id is not None:
                rows = conn.execute(
                    "SELECT * FROM edu_posts WHERE series_id=? ORDER BY created_at DESC LIMIT ?",
                    (series_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM edu_posts ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["thread_tweets"] = json.loads(d.get("thread_json") or "[]")
            except Exception:
                d["thread_tweets"] = []
            result.append(d)
        return result

    def get_series_summaries(self, series_id: int, limit: int = 10) -> list[str]:
        """Return recent post content snippets for continuity prompting."""
        posts = self.get_recent_edu_posts(limit=limit, series_id=series_id)
        return [(p.get("content") or "")[:200] for p in posts]

    # ── Trusted feed ──────────────────────────────────────────────────────────

    def save_feed_item(self, item: dict) -> int | None:
        """Returns new row id or None if URL already exists."""
        now = datetime.now().isoformat()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO edu_trusted_feed
                       (fetched_at, source_id, source_platform, title, url, url_hash,
                        summary, published, tags, educational_category, difficulty_level,
                        educational_quality_score, developer_relevance_score)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        now,
                        item.get("source_id", ""),
                        item.get("source_platform", ""),
                        item.get("title", ""),
                        item.get("url", ""),
                        item.get("url_hash", ""),
                        item.get("summary", ""),
                        item.get("published", ""),
                        item.get("tags", "[]"),
                        item.get("educational_category", ""),
                        item.get("difficulty_level", "Intermediate"),
                        item.get("educational_quality_score", 5.0),
                        item.get("developer_relevance_score", 5.0),
                    ),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_feed_items(
        self,
        category: str | None = None,
        difficulty: str | None = None,
        source_id: str | None = None,
        min_quality: float = 0.0,
        status: str | None = "new",
        limit: int = 50,
    ) -> list[dict]:
        with self._connect() as conn:
            clauses = ["educational_quality_score >= ?"]
            params: list = [min_quality]
            if category:
                clauses.append("educational_category = ?")
                params.append(category)
            if difficulty:
                clauses.append("difficulty_level = ?")
                params.append(difficulty)
            if source_id:
                clauses.append("source_id = ?")
                params.append(source_id)
            if status:
                clauses.append("status = ?")
                params.append(status)
            where = " AND ".join(clauses)
            rows = conn.execute(
                f"SELECT * FROM edu_trusted_feed WHERE {where} "
                "ORDER BY educational_quality_score DESC, fetched_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_feed_item_used(self, item_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE edu_trusted_feed SET status='used', post_generated=1 WHERE id=?",
                (item_id,),
            )

    def delete_feed_item(self, item_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM edu_trusted_feed WHERE id=?", (item_id,))

    def feed_item_count(self, status: str | None = None) -> int:
        with self._connect() as conn:
            if status:
                return conn.execute(
                    "SELECT COUNT(*) FROM edu_trusted_feed WHERE status=?", (status,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM edu_trusted_feed").fetchone()[0]

    def clear_old_feed_items(self, keep_days: int = 14) -> int:
        """Delete feed items older than keep_days. Returns number deleted."""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM edu_trusted_feed WHERE fetched_at < ? AND status='new'",
                (cutoff,),
            )
            return cur.rowcount
