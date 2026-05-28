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
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

    try:
        # Try preferred languages first (manual or auto-generated)
        try:
            items = YouTubeTranscriptApi.get_transcript(
                youtube_id,
                languages=["pt-BR", "pt", "en"],
            )
            log.info("Transcript: preferred language found for %s", youtube_id)
        except Exception as e1:
            log.info("Transcript: preferred language failed (%s), trying any available", e1)
            # Fall back to any available transcript
            transcript_list = YouTubeTranscriptApi.list_transcripts(youtube_id)
            available = list(transcript_list)
            if not available:
                log.warning("Transcript: no transcripts available for %s", youtube_id)
                return None
            chosen = available[0]
            log.info(
                "Transcript: using %s (lang=%s, auto=%s)",
                youtube_id, chosen.language_code, chosen.is_generated
            )
            items = chosen.fetch()
    except TranscriptsDisabled:
        log.warning("Transcript: transcripts disabled for %s", youtube_id)
        return None
    except Exception as e:
        log.warning("Transcript: unexpected error for %s: %s", youtube_id, e)
        return None

    parts = []
    for item in items:
        start = int(item["start"])
        mm, ss = divmod(start, 60)
        parts.append(f"[{mm:02d}:{ss:02d}] {item['text']}")

    if not parts:
        log.warning("Transcript: fetched empty transcript for %s", youtube_id)
        return None

    log.info("Transcript: %d segments for %s", len(parts), youtube_id)
    return "\n".join(parts)


def save_pains(video_id: int, topic_id: int, pains: list[dict], video_url: str):
    import datetime
    youtube_id = extract_youtube_id(video_url)

    if not pains:
        db.update_video(video_id, status="completed", processed_at=datetime.datetime.utcnow().isoformat())
        return

    # Single batch call to assign all pains to existing clusters
    existing_clusters = db.get_clusters_for_topic(topic_id)
    assignments = gemini_client.find_clusters_batch(pains, existing_clusters)

    for pain, cluster_id in zip(pains, assignments):
        # Validate cluster_id still exists (race condition guard)
        if cluster_id is not None:
            valid = any(c["id"] == cluster_id for c in existing_clusters)
            if not valid:
                cluster_id = None

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

    # Step 1: get transcript via youtube-transcript-api
    transcript = None
    if youtube_id:
        transcript = get_transcript(youtube_id)
        if transcript:
            log.info("Video %d: transcript fetched (%d chars)", video_id, len(transcript))
        else:
            log.warning("Video %d: no transcript available", video_id)

    if not transcript:
        db.update_video(
            video_id,
            status="waiting_manual_transcript",
            error_msg="Não foi possível obter transcrição automática. Cole a transcrição manualmente."
        )
        return

    # Step 2: send transcript to Gemini
    try:
        pains = gemini_client.extract_pains_from_transcript(transcript, url, topic_title=topic_title)
        log.info("Video %d: extracted %d pains", video_id, len(pains))
    except Exception as e:
        log.error("Video %d: Gemini extraction failed: %s", video_id, e)
        db.update_video(video_id, status="failed", error_msg=str(e))
        return

    if not pains:
        log.warning("Video %d: Gemini returned no pains", video_id)

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
