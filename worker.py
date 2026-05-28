import re
import threading
import time
import logging
import httpx
import db
import gemini_client

log = logging.getLogger(__name__)

YT_PATTERN = re.compile(r'(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})')


def extract_youtube_id(url: str) -> str | None:
    m = YT_PATTERN.search(url)
    return m.group(1) if m else None


def yt_link_with_ts(youtube_id: str, url: str, seconds: int | None) -> str:
    if seconds and youtube_id:
        return f"https://www.youtube.com/watch?v={youtube_id}&t={int(seconds)}s"
    return url


def fetch_title(url: str) -> str | None:
    try:
        r = httpx.get(
            f"https://www.youtube.com/oembed?url={url}&format=json",
            timeout=10, follow_redirects=True
        )
        if r.status_code == 200:
            return r.json().get("title")
    except Exception:
        pass
    return None


def get_transcript(youtube_id: str) -> str | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
        try:
            items = YouTubeTranscriptApi.get_transcript(youtube_id, languages=["pt", "pt-BR", "pt-PT"])
        except NoTranscriptFound:
            items = YouTubeTranscriptApi.get_transcript(youtube_id)

        parts = []
        for item in items:
            t = int(item["start"])
            parts.append(f"[{t // 60:02d}:{t % 60:02d}] {item['text']}")
        return "\n".join(parts)
    except Exception:
        return None


def save_pains(video_id: int, topic_id: int, pains: list[dict], video_url: str):
    youtube_id = extract_youtube_id(video_url)

    for pain in pains:
        # Get current clusters (re-read each time so newly inserted ones are visible)
        clusters = db.get_clusters_for_topic(topic_id)
        cluster_id = gemini_client.find_cluster(pain, clusters)

        if cluster_id is None:
            cluster_id = db.insert_cluster(
                topic_id,
                pain.get("title", ""),
                pain.get("category"),
                pain.get("summary"),
                pain.get("quote"),
            )

        ts = pain.get("timestamp_seconds")
        pain_row = {
            **pain,
            "video_id": video_id,
            "topic_id": topic_id,
            "cluster_id": cluster_id,
            "youtube_link": yt_link_with_ts(youtube_id, video_url, ts),
        }
        db.insert_pain(pain_row)

    import datetime
    db.update_video(video_id, status="completed", processed_at=datetime.datetime.utcnow().isoformat())


def process_video(video: dict):
    video_id = video["id"]
    url = video["url"]
    youtube_id = video.get("youtube_id") or extract_youtube_id(url)
    topic_id = video["topic_id"]

    topic = db.get_topic(topic_id)
    topic_title = topic["title"] if topic else ""

    db.update_video(video_id, status="processing")

    # Fetch title in background
    title = fetch_title(url)
    if title:
        db.update_video(video_id, title=title)

    pains = None

    # Attempt 1: direct URL to Gemini
    try:
        pains = gemini_client.extract_pains_from_url(url, topic_title=topic_title)
        log.info("Video %d: extracted %d pains via URL", video_id, len(pains))
    except Exception as e:
        log.warning("Video %d: direct URL failed: %s", video_id, e)

    # Attempt 2: transcript
    if not pains and youtube_id:
        try:
            transcript = get_transcript(youtube_id)
            if transcript:
                pains = gemini_client.extract_pains_from_transcript(transcript, url, topic_title=topic_title)
                log.info("Video %d: extracted %d pains via transcript", video_id, len(pains))
        except Exception as e:
            log.warning("Video %d: transcript failed: %s", video_id, e)

    if not pains:
        db.update_video(
            video_id,
            status="waiting_manual_transcript",
            error_msg="Não foi possível obter transcrição automática. Cole a transcrição manualmente."
        )
        return

    try:
        save_pains(video_id, topic_id, pains, url)
    except Exception as e:
        log.error("Video %d: save_pains failed: %s", video_id, e)
        db.update_video(video_id, status="failed", error_msg=str(e))


def _loop():
    while True:
        try:
            videos = db.get_queued_videos()
            for video in videos:
                process_video(video)
        except Exception as e:
            log.error("Worker loop error: %s", e)
        time.sleep(5)


def start_worker():
    t = threading.Thread(target=_loop, daemon=True, name="queue-worker")
    t.start()
    log.info("Queue worker started")
    return t
