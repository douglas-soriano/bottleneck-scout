import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "data.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'youtube',
    external_id TEXT,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    error_msg TEXT,
    transcript TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pain_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    summary TEXT,
    best_quote TEXT,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    cluster_id INTEGER,
    title TEXT NOT NULL,
    summary TEXT,
    category TEXT,
    area TEXT,
    timestamp_seconds INTEGER,
    source_link TEXT,
    quote TEXT,
    speaker_context TEXT,
    who_suffers TEXT,
    business_impact TEXT,
    severity INTEGER DEFAULT 3,
    confidence TEXT DEFAULT 'medium',
    opportunity TEXT,
    commercial_actionability INTEGER DEFAULT 3,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    FOREIGN KEY (cluster_id) REFERENCES pain_clusters(id)
);

CREATE TRIGGER IF NOT EXISTS cleanup_empty_clusters
AFTER DELETE ON pains
WHEN OLD.cluster_id IS NOT NULL
BEGIN
    DELETE FROM pain_clusters
    WHERE id = OLD.cluster_id
    AND NOT EXISTS (SELECT 1 FROM pains WHERE cluster_id = OLD.cluster_id);
END;
"""


def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(conn: sqlite3.Connection, table: str, columns: set[str], column: str, definition: str):
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        columns.add(column)


@contextmanager
def db():
    conn = _conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        topic_columns = _columns(conn, "topics")
        _add_column(conn, "topics", topic_columns, "created_at", "TEXT")

        video_columns = _columns(conn, "videos")
        _add_column(conn, "videos", video_columns, "source", "TEXT NOT NULL DEFAULT 'youtube'")
        _add_column(conn, "videos", video_columns, "external_id", "TEXT")
        _add_column(conn, "videos", video_columns, "source_url", "TEXT")
        _add_column(conn, "videos", video_columns, "title", "TEXT")
        _add_column(conn, "videos", video_columns, "error_msg", "TEXT")
        _add_column(conn, "videos", video_columns, "transcript", "TEXT")
        _add_column(conn, "videos", video_columns, "created_at", "TEXT")
        _add_column(conn, "videos", video_columns, "processed_at", "TEXT")
        if "url" in video_columns:
            conn.execute("UPDATE videos SET source_url = COALESCE(source_url, url)")
        if "youtube_id" in video_columns:
            conn.execute("UPDATE videos SET external_id = COALESCE(external_id, youtube_id)")

        cluster_columns = _columns(conn, "pain_clusters")
        _add_column(conn, "pain_clusters", cluster_columns, "category", "TEXT")
        _add_column(conn, "pain_clusters", cluster_columns, "summary", "TEXT")
        _add_column(conn, "pain_clusters", cluster_columns, "best_quote", "TEXT")

        pain_columns = _columns(conn, "pains")
        _add_column(conn, "pains", pain_columns, "summary", "TEXT")
        _add_column(conn, "pains", pain_columns, "category", "TEXT")
        _add_column(conn, "pains", pain_columns, "area", "TEXT")
        _add_column(conn, "pains", pain_columns, "timestamp_seconds", "INTEGER")
        _add_column(conn, "pains", pain_columns, "source_link", "TEXT")
        _add_column(conn, "pains", pain_columns, "quote", "TEXT")
        _add_column(conn, "pains", pain_columns, "speaker_context", "TEXT")
        _add_column(conn, "pains", pain_columns, "who_suffers", "TEXT")
        _add_column(conn, "pains", pain_columns, "business_impact", "TEXT")
        _add_column(conn, "pains", pain_columns, "severity", "INTEGER DEFAULT 3")
        _add_column(conn, "pains", pain_columns, "confidence", "TEXT DEFAULT 'medium'")
        _add_column(conn, "pains", pain_columns, "opportunity", "TEXT")
        _add_column(conn, "pains", pain_columns, "commercial_actionability", "INTEGER DEFAULT 3")
        _add_column(conn, "pains", pain_columns, "created_at", "TEXT")
        if "youtube_link" in pain_columns:
            conn.execute("UPDATE pains SET source_link = COALESCE(source_link, youtube_link)")


# ── Topics ───────────────────────────────────────────────────────────────────

def get_topics() -> list[dict]:
    with db() as conn:
        rows = conn.execute("""
            SELECT t.*, COUNT(v.id) as video_count
            FROM topics t
            LEFT JOIN videos v ON v.topic_id = t.id
            GROUP BY t.id
            ORDER BY t.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_topic(topic_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    return dict(row) if row else None


def create_topic(title: str) -> int:
    with db() as conn:
        cur = conn.execute("INSERT INTO topics (title) VALUES (?)", (title,))
        return cur.lastrowid


def update_topic(topic_id: int, title: str):
    with db() as conn:
        conn.execute("UPDATE topics SET title = ? WHERE id = ?", (title, topic_id))


def delete_topic(topic_id: int):
    with db() as conn:
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))


# ── Videos ───────────────────────────────────────────────────────────────────

def get_video(video_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    return dict(row) if row else None


def get_videos_by_topic(topic_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE topic_id = ? ORDER BY created_at DESC",
            (topic_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_video_by_source_id(topic_id: int, source: str, external_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            """
            SELECT * FROM videos
            WHERE topic_id = ?
            AND source = ?
            AND external_id = ?
            """,
            (topic_id, source, external_id)
        ).fetchone()
    return dict(row) if row else None


def add_item(topic_id: int, source: str, source_url: str, external_id: str | None) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO videos (topic_id, source, external_id, source_url)
            VALUES (?, ?, ?, ?)
            """,
            (topic_id, source, external_id, source_url)
        )
        return cur.lastrowid


def update_video(video_id: int, **kwargs):
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [video_id]
    with db() as conn:
        conn.execute(f"UPDATE videos SET {cols} WHERE id = ?", vals)


def delete_video(video_id: int):
    with db() as conn:
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))


def delete_pains_for_video(video_id: int):
    with db() as conn:
        conn.execute("DELETE FROM pains WHERE video_id = ?", (video_id,))


def get_queued_videos() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE status = 'queued' ORDER BY created_at LIMIT 5"
        ).fetchall()
    return [dict(r) for r in rows]


def has_active_videos(topic_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE topic_id = ? AND status IN ('queued','processing')",
            (topic_id,)
        ).fetchone()
    return row[0] > 0


# ── Pains & Clusters ─────────────────────────────────────────────────────────

def get_clusters_for_topic(topic_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, summary, category FROM pain_clusters WHERE topic_id = ?",
            (topic_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def insert_cluster(topic_id: int, title: str, category: str | None,
                   summary: str | None, best_quote: str | None) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO pain_clusters (topic_id, title, category, summary, best_quote) VALUES (?,?,?,?,?)",
            (topic_id, title, category, summary, best_quote)
        )
        return cur.lastrowid


def insert_pain(pain: dict) -> int:
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO pains (video_id, topic_id, cluster_id, title, summary, category, area,
                timestamp_seconds, source_link, quote, speaker_context, who_suffers,
                business_impact, severity, confidence, opportunity, commercial_actionability)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pain["video_id"], pain["topic_id"], pain.get("cluster_id"),
            pain.get("title", ""), pain.get("summary"), pain.get("category"), pain.get("area"),
            pain.get("timestamp_seconds"), pain.get("source_link"),
            pain.get("quote"), pain.get("speaker_context"), pain.get("who_suffers"),
            pain.get("business_impact"), pain.get("severity", 3),
            pain.get("confidence", "medium"), pain.get("opportunity"),
            pain.get("commercial_actionability", 3)
        ))
        return cur.lastrowid


def get_video_pains(video_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute("""
            SELECT p.*, pc.title as cluster_title
            FROM pains p
            LEFT JOIN pain_clusters pc ON p.cluster_id = pc.id
            WHERE p.video_id = ?
            ORDER BY COALESCE(p.timestamp_seconds, 999999), p.severity DESC
        """, (video_id,)).fetchall()
    return [dict(r) for r in rows]


def get_topic_ranking(topic_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute("""
            SELECT
                pc.id,
                pc.title,
                pc.category,
                pc.summary,
                pc.best_quote,
                COUNT(DISTINCT p.video_id) as video_count,
                COUNT(p.id) as mention_count,
                ROUND(AVG(p.severity), 1) as avg_severity,
                ROUND(AVG(CASE p.confidence WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END), 1) as avg_confidence,
                ROUND(AVG(COALESCE(p.commercial_actionability, 3)), 1) as avg_actionability
            FROM pain_clusters pc
            JOIN pains p ON p.cluster_id = pc.id
            WHERE pc.topic_id = ?
            AND COALESCE(p.commercial_actionability, 3) >= 3
            GROUP BY pc.id
            ORDER BY video_count DESC, avg_actionability DESC, mention_count DESC, avg_severity DESC, avg_confidence DESC
        """, (topic_id,)).fetchall()
    return [dict(r) for r in rows]


def get_cluster(cluster_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM pain_clusters WHERE id = ?", (cluster_id,)).fetchone()
    return dict(row) if row else None


def get_cluster_pains(cluster_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute("""
            SELECT p.*, v.source_url as video_url, v.title as video_title,
                v.external_id, v.source
            FROM pains p
            JOIN videos v ON p.video_id = v.id
            WHERE p.cluster_id = ?
            ORDER BY p.severity DESC, COALESCE(p.timestamp_seconds, 999999)
        """, (cluster_id,)).fetchall()
    return [dict(r) for r in rows]
