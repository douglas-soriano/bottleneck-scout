import re
import threading
import time
import logging
import httpx
import db
import gemini_client

log = logging.getLogger(__name__)

YT_PATTERN = re.compile(r'(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})')

YT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

PREFERRED_LANGS = ["pt-BR", "pt", "en"]


# ── YouTube ID / link helpers ─────────────────────────────────────────────────

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


# ── Transcript fetching ───────────────────────────────────────────────────────

def get_transcript(youtube_id: str) -> str | None:
    """
    Fetch YouTube captions via youtube-transcript-api.
    Tries pt-BR, pt, en; accepts auto-generated captions.
    Returns formatted transcript string with [MM:SS] timestamps, or None.
    """
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()

    try:
        snippets = api.fetch(youtube_id, languages=["pt-BR", "pt", "en"])
        snippets = list(snippets)
    except Exception as e1:
        log.info("Transcript: preferred languages failed (%s), trying any", e1)
        try:
            transcript_list = api.list(youtube_id)
            # Pick best available: prefer manual, then auto; prefer pt-BR/pt/en
            chosen = None
            candidates = list(transcript_list)
            manual = [t for t in candidates if not t.is_generated]
            auto   = [t for t in candidates if t.is_generated]
            for lang in PREFERRED_LANGS:
                for t in manual:
                    if t.language_code == lang:
                        chosen = t
                        break
                if chosen:
                    break
            if not chosen:
                for lang in PREFERRED_LANGS:
                    for t in auto:
                        if t.language_code == lang:
                            chosen = t
                            break
                    if chosen:
                        break
            if not chosen:
                chosen = candidates[0] if candidates else None
            if not chosen:
                log.warning("Transcript: no tracks available for %s", youtube_id)
                return None
            log.info(
                "Transcript: using lang=%s auto=%s for %s",
                chosen.language_code, chosen.is_generated, youtube_id
            )
            snippets = list(chosen.fetch())
        except Exception as e2:
            log.warning("Transcript: all attempts failed for %s: %s", youtube_id, e2)
            return None

    if not snippets:
        log.warning("Transcript: empty result for %s", youtube_id)
        return None

    parts = []
    for s in snippets:
        start = int(s.start)
        mm, ss = divmod(start, 60)
        parts.append(f"[{mm:02d}:{ss:02d}] {s.text}")

    log.info("Transcript: %d segments for %s", len(parts), youtube_id)
    return "\n".join(parts)


# ── Pain saving & clustering ──────────────────────────────────────────────────

def save_pains(video_id: int, topic_id: int, pains: list[dict], video_url: str):
    import datetime
    youtube_id = extract_youtube_id(video_url)

    if not pains:
        db.update_video(video_id, status="completed", processed_at=datetime.datetime.utcnow().isoformat())
        return

    existing_clusters = db.get_clusters_for_topic(topic_id)
    assignments = gemini_client.find_clusters_batch(pains, existing_clusters)

    for pain, cluster_id in zip(pains, assignments):
        if cluster_id is not None:
            if not any(c["id"] == cluster_id for c in existing_clusters):
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
        db.insert_pain({
            **pain,
            "video_id": video_id,
            "topic_id": topic_id,
            "cluster_id": cluster_id,
            "youtube_link": yt_link_with_ts(youtube_id, video_url, ts),
        })

    db.update_video(video_id, status="completed", processed_at=datetime.datetime.utcnow().isoformat())


# ── Video processing ──────────────────────────────────────────────────────────

def process_video(video: dict):
    video_id = video["id"]
    url = video["url"]
    youtube_id = video.get("youtube_id") or extract_youtube_id(url)
    topic_id = video["topic_id"]

    topic = db.get_topic(topic_id)
    topic_title = topic["title"] if topic else ""

    db.update_video(video_id, status="processing")

    title = fetch_title(url)
    if title:
        db.update_video(video_id, title=title)

    # Step 1: fetch transcript
    transcript = get_transcript(youtube_id) if youtube_id else None

    if not transcript:
        db.update_video(
            video_id,
            status="waiting_manual_transcript",
            error_msg="Não foi possível obter transcrição automática. Cole a transcrição manualmente.",
        )
        return

    log.info("Video %d: transcript %d chars", video_id, len(transcript))

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


# ── Background worker loop ────────────────────────────────────────────────────

def _loop():
    while True:
        try:
            for video in db.get_queued_videos():
                process_video(video)
        except Exception as e:
            log.error("Worker loop error: %s", e)
        time.sleep(5)


def start_worker():
    t = threading.Thread(target=_loop, daemon=True, name="queue-worker")
    t.start()
    log.info("Queue worker started")
    return t
