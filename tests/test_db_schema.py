import importlib
import sqlite3


def load_db(monkeypatch, path):
    monkeypatch.setenv("DB_PATH", str(path))
    import db

    importlib.reload(db)
    return db


def columns(path, table):
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    finally:
        conn.close()


def test_new_schema_uses_source_names(monkeypatch, tmp_path):
    db_path = tmp_path / "new.db"
    db = load_db(monkeypatch, db_path)

    db.init_db()

    video_columns = columns(db_path, "videos")
    pain_columns = columns(db_path, "pains")

    assert {"source", "external_id", "source_url"} <= video_columns
    assert "source_link" in pain_columns
    assert "youtube_id" not in video_columns
    assert "url" not in video_columns
    assert "youtube_link" not in pain_columns


def test_old_schema_migrates_youtube_fields(monkeypatch, tmp_path):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
        CREATE TABLE topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            youtube_id TEXT,
            status TEXT NOT NULL DEFAULT 'queued'
        );
        CREATE TABLE pain_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            title TEXT NOT NULL
        );
        CREATE TABLE pains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            cluster_id INTEGER,
            title TEXT NOT NULL,
            youtube_link TEXT
        );
        INSERT INTO topics (id, title) VALUES (1, 'Publishing');
        INSERT INTO videos (id, topic_id, url, youtube_id) VALUES
            (1, 1, 'https://youtu.be/abcdefghijk', 'abcdefghijk');
        INSERT INTO pains (id, video_id, topic_id, title, youtube_link) VALUES
            (1, 1, 1, 'Manual reporting', 'https://www.youtube.com/watch?v=abcdefghijk&t=30s');
        """)
        conn.commit()
    finally:
        conn.close()

    db = load_db(monkeypatch, db_path)
    db.init_db()

    video = db.get_video(1)
    pain = db.get_video_pains(1)[0]

    assert video["source"] == "youtube"
    assert video["external_id"] == "abcdefghijk"
    assert video["source_url"] == "https://youtu.be/abcdefghijk"
    assert pain["source_link"] == "https://www.youtube.com/watch?v=abcdefghijk&t=30s"
