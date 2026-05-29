import threading
import time
import logging
from datetime import UTC, datetime

import db
import gemini_client
from sources import get_provider_for_url

log = logging.getLogger(__name__)


# ── Pain saving & clustering ──────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def save_pains(video_id: int, topic_id: int, pains: list[dict], video_url: str):
    provider = get_provider_for_url(video_url)
    external_id = provider.external_id(video_url) if provider else None

    db.delete_pains_for_video(video_id)
    log.info("Video %d: cleared existing pains before saving", video_id)

    if not pains:
        db.update_video(video_id, status="completed", processed_at=_now_iso())
        log.info("Video %d: completed with no pains", video_id)
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
            "source_link": (
                provider.evidence_link(external_id, video_url, ts)
                if provider
                else video_url
            ),
        })

    db.update_video(video_id, status="completed", processed_at=_now_iso())
    log.info("Video %d: saved %d pains", video_id, len(pains))


# ── Video processing ──────────────────────────────────────────────────────────

def process_video(video: dict):
    video_id = video["id"]
    url = video["source_url"]
    source = video.get("source") or "youtube"
    provider = get_provider_for_url(url)
    external_id = video.get("external_id")
    if not external_id and provider:
        external_id = provider.external_id(url)
    topic_id = video["topic_id"]

    topic = db.get_topic(topic_id)
    topic_title = topic["title"] if topic else ""

    db.delete_pains_for_video(video_id)
    db.update_video(video_id, status="processing", error_msg=None)
    log.info(
        "Video %d: processing source=%s external_id=%s",
        video_id,
        source,
        external_id,
    )

    title = provider.fetch_title(url) if provider else None
    if title:
        db.update_video(video_id, title=title)

    transcript = video.get("transcript")
    if not transcript and provider and external_id:
        transcript = provider.fetch_content(external_id)

    if not transcript:
        db.update_video(
            video_id,
            status="waiting_manual_transcript",
            error_msg="Could not fetch captions automatically. Paste the transcript manually.",
        )
        log.info("Video %d: waiting for manual transcript", video_id)
        return

    log.info("Video %d: transcript %d chars", video_id, len(transcript))
    db.update_video(video_id, transcript=transcript, source=source, external_id=external_id, source_url=url)

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
