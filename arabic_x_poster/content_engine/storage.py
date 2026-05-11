"""SQLite storage for generated content, drafts, continuity memory, and analytics."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path


class ContentStorage:
    def __init__(self, db_path: Path):
        self._db = str(db_path)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS posts (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at        TEXT NOT NULL,
                    topic             TEXT,
                    post_type         TEXT,
                    tone              TEXT,
                    audience_level    TEXT,
                    platform          TEXT,
                    language          TEXT,
                    hooks             TEXT,
                    selected_hook     TEXT,
                    hook_scores       TEXT,
                    raw_content       TEXT,
                    humanized_content TEXT,
                    intent_profile    TEXT,
                    tags              TEXT,
                    status            TEXT DEFAULT 'draft',
                    scheduled_for     TEXT,
                    posted_at         TEXT,
                    tweet_id          TEXT,
                    likes             INTEGER DEFAULT 0,
                    retweets          INTEGER DEFAULT 0,
                    replies           INTEGER DEFAULT 0,
                    impressions       INTEGER DEFAULT 0,
                    bookmarks         INTEGER DEFAULT 0,
                    profile_visits    INTEGER DEFAULT 0,
                    performance_score REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS continuity_memory (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    summary    TEXT,
                    topics     TEXT,
                    post_id    INTEGER REFERENCES posts(id)
                );

                CREATE TABLE IF NOT EXISTS post_patterns (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at         TEXT NOT NULL,
                    source_hash        TEXT NOT NULL UNIQUE,
                    hook_type          TEXT,
                    content_format     TEXT,
                    emotional_tone     TEXT,
                    narrative_structure TEXT,
                    topic_angle        TEXT,
                    engagement_trigger TEXT,
                    post_length        TEXT,
                    engagement_score   REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS pattern_clusters (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at          TEXT NOT NULL,
                    template_name       TEXT,
                    template_structure  TEXT,
                    hook_type           TEXT,
                    content_format      TEXT,
                    emotional_tone      TEXT,
                    narrative_structure TEXT,
                    topic_angle         TEXT,
                    engagement_trigger  TEXT,
                    pattern_count       INTEGER DEFAULT 1,
                    avg_engagement      REAL DEFAULT 0,
                    source_hashes       TEXT
                );
            """)
            self._migrate(conn)

    def _migrate(self, conn) -> None:
        """Add any columns missing from older DB versions."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
        new_cols = {
            "audience_level": "TEXT",
            "intent_profile": "TEXT",
            "tags": "TEXT",
            "status": "TEXT DEFAULT 'draft'",
            "scheduled_for": "TEXT",
            "impressions": "INTEGER DEFAULT 0",
            "bookmarks": "INTEGER DEFAULT 0",
            "profile_visits": "INTEGER DEFAULT 0",
            "performance_score": "REAL DEFAULT 0",
        }
        for col, typedef in new_cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {typedef}")

    # ── Write ─────────────────────────────────────────────────────────────────

    def save_draft(self, data: dict) -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO posts
                   (created_at, topic, post_type, tone, audience_level, platform, language,
                    hooks, selected_hook, hook_scores, raw_content, humanized_content,
                    intent_profile, tags, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    data.get("topic", ""),
                    data.get("post_type", ""),
                    data.get("tone", ""),
                    data.get("audience_level", ""),
                    data.get("platform", ""),
                    data.get("language", ""),
                    json.dumps(data.get("hooks", [])),
                    data.get("selected_hook", ""),
                    json.dumps(data.get("hook_scores", [])),
                    data.get("raw_content", ""),
                    data.get("humanized_content", ""),
                    json.dumps(data.get("intent_profile", {})),
                    json.dumps(data.get("tags", [])),
                    "draft",
                ),
            )
            post_id = cur.lastrowid
            summary = (data.get("humanized_content") or data.get("raw_content") or "")[:300]
            conn.execute(
                """INSERT INTO continuity_memory (created_at, summary, topics, post_id)
                   VALUES (?,?,?,?)""",
                (now, summary, json.dumps([data.get("topic", "")]), post_id),
            )
            return post_id

    def mark_posted(self, post_id: int, tweet_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE posts SET status='posted', posted_at=?, tweet_id=? WHERE id=?",
                (datetime.now().isoformat(), tweet_id, post_id),
            )

    def schedule_post(self, post_id: int, scheduled_for: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE posts SET status='scheduled', scheduled_for=? WHERE id=?",
                (scheduled_for, post_id),
            )

    def update_engagement(
        self,
        post_id: int,
        likes: int = 0,
        retweets: int = 0,
        replies: int = 0,
        impressions: int = 0,
        bookmarks: int = 0,
        profile_visits: int = 0,
    ) -> None:
        perf = self._calc_performance(likes, retweets, replies, impressions, bookmarks)
        with self._connect() as conn:
            conn.execute(
                """UPDATE posts SET likes=?, retweets=?, replies=?, impressions=?,
                   bookmarks=?, profile_visits=?, performance_score=? WHERE id=?""",
                (likes, retweets, replies, impressions, bookmarks, profile_visits, perf, post_id),
            )

    @staticmethod
    def _calc_performance(likes, retweets, replies, impressions, bookmarks) -> float:
        weighted = likes * 2 + retweets * 4 + replies * 5 + bookmarks * 6
        if impressions > 0:
            return round((weighted / impressions) * 1000, 2)
        return float(weighted)

    def delete_draft(self, post_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM continuity_memory WHERE post_id=?", (post_id,))
            conn.execute("DELETE FROM posts WHERE id=?", (post_id,))

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_recent_posts(self, limit: int = 30) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_continuity_context(self, limit: int = 5) -> str:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT summary, created_at FROM continuity_memory
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        if not rows:
            return "No previous posts yet — this is the first one."
        return "\n".join(f"[{r[1][:10]}] {r[0]}" for r in rows)

    def get_analytics(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            posted = conn.execute("SELECT COUNT(*) FROM posts WHERE status='posted'").fetchone()[0]
            scheduled = conn.execute("SELECT COUNT(*) FROM posts WHERE status='scheduled'").fetchone()[0]
            avg_eng = conn.execute(
                "SELECT AVG(performance_score) FROM posts WHERE status='posted' AND performance_score > 0"
            ).fetchone()[0] or 0
            type_rows = conn.execute(
                "SELECT post_type, COUNT(*) AS n FROM posts GROUP BY post_type ORDER BY n DESC LIMIT 5"
            ).fetchall()
        return {
            "total_generated": total,
            "total_posted": posted,
            "total_scheduled": scheduled,
            "avg_performance": round(float(avg_eng), 2),
            "top_types": [(r[0], r[1]) for r in type_rows],
        }

    def get_performance_insights(self) -> dict:
        with self._connect() as conn:
            best_types = conn.execute(
                """SELECT post_type, AVG(performance_score) AS avg, COUNT(*) AS n
                   FROM posts WHERE status='posted' AND performance_score > 0
                   GROUP BY post_type ORDER BY avg DESC LIMIT 5"""
            ).fetchall()
            best_topics = conn.execute(
                """SELECT topic, AVG(performance_score) AS avg, COUNT(*) AS n
                   FROM posts WHERE status='posted' AND performance_score > 0
                   GROUP BY topic ORDER BY avg DESC LIMIT 5"""
            ).fetchall()
            best_tones = conn.execute(
                """SELECT tone, AVG(performance_score) AS avg
                   FROM posts WHERE status='posted' AND performance_score > 0
                   GROUP BY tone ORDER BY avg DESC LIMIT 5"""
            ).fetchall()
        return {
            "best_types": [(r[0], round(float(r[1]), 2), r[2]) for r in best_types],
            "best_topics": [(r[0], round(float(r[1]), 2), r[2]) for r in best_topics],
            "best_tones": [(r[0], round(float(r[1]), 2)) for r in best_tones],
        }

    def get_scheduled_posts(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM posts WHERE status='scheduled' ORDER BY scheduled_for ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Pattern library ───────────────────────────────────────────────────────

    def save_pattern(self, pattern) -> bool:
        """Persist a PostPattern. Returns False if source_hash already exists."""
        from .pattern_engine import PostPattern
        now = datetime.now().isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO post_patterns
                       (created_at, source_hash, hook_type, content_format, emotional_tone,
                        narrative_structure, topic_angle, engagement_trigger, post_length, engagement_score)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        now,
                        pattern.source_hash,
                        pattern.hook_type,
                        pattern.content_format,
                        pattern.emotional_tone,
                        pattern.narrative_structure,
                        pattern.topic_angle,
                        pattern.engagement_trigger,
                        pattern.post_length,
                        pattern.engagement_score,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False  # duplicate

    def get_patterns(self) -> list:
        """Return all stored PostPattern objects."""
        from .pattern_engine import PostPattern
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM post_patterns ORDER BY engagement_score DESC"
            ).fetchall()
        result = []
        for r in rows:
            result.append(PostPattern(
                hook_type=r["hook_type"] or "",
                content_format=r["content_format"] or "",
                emotional_tone=r["emotional_tone"] or "",
                narrative_structure=r["narrative_structure"] or "",
                topic_angle=r["topic_angle"] or "",
                engagement_trigger=r["engagement_trigger"] or "",
                post_length=r["post_length"] or "short",
                engagement_score=float(r["engagement_score"] or 0),
                source_hash=r["source_hash"] or "",
            ))
        return result

    def save_clusters(self, clusters: list) -> None:
        """Replace all clusters with a fresh set."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM pattern_clusters")
            for c in clusters:
                conn.execute(
                    """INSERT INTO pattern_clusters
                       (created_at, template_name, template_structure, hook_type, content_format,
                        emotional_tone, narrative_structure, topic_angle, engagement_trigger,
                        pattern_count, avg_engagement, source_hashes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        now,
                        c.template_name,
                        c.template_structure,
                        c.hook_type,
                        c.content_format,
                        c.emotional_tone,
                        c.narrative_structure,
                        c.topic_angle,
                        c.engagement_trigger,
                        c.pattern_count,
                        c.avg_engagement,
                        json.dumps(c.source_hashes),
                    ),
                )

    def get_clusters(self) -> list:
        """Return all PatternCluster objects ordered by avg_engagement desc."""
        from .pattern_engine import PatternCluster
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pattern_clusters ORDER BY avg_engagement DESC, pattern_count DESC"
            ).fetchall()
        result = []
        for r in rows:
            hashes = json.loads(r["source_hashes"] or "[]")
            result.append(PatternCluster(
                template_name=r["template_name"] or "",
                template_structure=r["template_structure"] or "",
                hook_type=r["hook_type"] or "",
                content_format=r["content_format"] or "",
                emotional_tone=r["emotional_tone"] or "",
                narrative_structure=r["narrative_structure"] or "",
                topic_angle=r["topic_angle"] or "",
                engagement_trigger=r["engagement_trigger"] or "",
                pattern_count=int(r["pattern_count"] or 1),
                avg_engagement=float(r["avg_engagement"] or 0),
                source_hashes=hashes,
            ))
        return result

    def pattern_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM post_patterns").fetchone()[0]

    def delete_all_patterns(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM post_patterns")
            conn.execute("DELETE FROM pattern_clusters")
