import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

import db
import worker
from sources import get_provider_for_url

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    worker.start_worker()
    yield


app = FastAPI(title="Bottleneck Scout", lifespan=lifespan)


# ── Topics ───────────────────────────────────────────────────────────────────

@app.get("/")
def topics_list(request: Request):
    return templates.TemplateResponse(request, "topics.html", {
        "topics": db.get_topics(),
    })


@app.post("/topics")
def create_topic(title: str = Form(...)):
    title = title.strip()
    if not title:
        raise HTTPException(400, "Title is required")
    topic_id = db.create_topic(title)
    return RedirectResponse(f"/topics/{topic_id}", status_code=303)


@app.get("/topics/{topic_id}/edit")
def edit_topic_form(request: Request, topic_id: int):
    topic = db.get_topic(topic_id)
    if not topic:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "edit_topic.html", {"topic": topic})


@app.post("/topics/{topic_id}/edit")
def edit_topic(topic_id: int, title: str = Form(...)):
    title = title.strip()
    if not title:
        raise HTTPException(400, "Title is required")
    db.update_topic(topic_id, title)
    return RedirectResponse("/", status_code=303)


@app.post("/topics/{topic_id}/delete")
def delete_topic(topic_id: int):
    db.delete_topic(topic_id)
    return RedirectResponse("/", status_code=303)


# ── Topic page ────────────────────────────────────────────────────────────────

@app.get("/topics/{topic_id}")
def topic_page(request: Request, topic_id: int):
    topic = db.get_topic(topic_id)
    if not topic:
        raise HTTPException(404)
    videos = db.get_videos_by_topic(topic_id)
    ranking = db.get_topic_ranking(topic_id)
    active = db.has_active_videos(topic_id)
    return templates.TemplateResponse(request, "topic.html", {
        "topic": topic,
        "videos": videos,
        "ranking": ranking,
        "has_active": active,
    })


@app.get("/topics/{topic_id}/videos-partial", response_class=HTMLResponse)
def videos_partial(request: Request, topic_id: int):
    topic = db.get_topic(topic_id)
    if not topic:
        raise HTTPException(404)
    videos = db.get_videos_by_topic(topic_id)
    active = db.has_active_videos(topic_id)
    return templates.TemplateResponse(request, "_videos_partial.html", {
        "topic": topic,
        "videos": videos,
        "has_active": active,
    })


# ── Videos ────────────────────────────────────────────────────────────────────

@app.post("/topics/{topic_id}/videos")
def add_videos(topic_id: int, urls: str = Form(...)):
    topic = db.get_topic(topic_id)
    if not topic:
        raise HTTPException(404)

    for line in urls.splitlines():
        url = line.strip()
        if not url:
            continue
        provider = get_provider_for_url(url)
        if not provider:
            continue
        external_id = provider.external_id(url)
        if not external_id:
            continue
        if db.get_video_by_source_id(topic_id, provider.source, external_id):
            continue
        db.add_item(topic_id, provider.source, url, external_id)
        log.info("Queued source topic_id=%d source=%s external_id=%s", topic_id, provider.source, external_id)

    return RedirectResponse(f"/topics/{topic_id}", status_code=303)


@app.post("/videos/{video_id}/delete")
def delete_video(video_id: int):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(404)
    topic_id = video["topic_id"]
    db.delete_video(video_id)
    return RedirectResponse(f"/topics/{topic_id}", status_code=303)


@app.post("/videos/{video_id}/ignore")
def ignore_video(video_id: int):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(404)
    db.update_video(video_id, status="ignored")
    return RedirectResponse(f"/topics/{video['topic_id']}", status_code=303)


@app.post("/videos/{video_id}/transcript")
def submit_transcript(video_id: int, transcript: str = Form(...)):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(404)

    transcript = transcript.strip()
    if not transcript:
        return RedirectResponse(f"/topics/{video['topic_id']}", status_code=303)

    db.delete_pains_for_video(video_id)
    db.update_video(video_id, status="queued", transcript=transcript, error_msg=None)
    log.info("Manual transcript queued video_id=%d chars=%d", video_id, len(transcript))

    return RedirectResponse(f"/topics/{video['topic_id']}", status_code=303)


@app.post("/videos/{video_id}/retry")
def retry_video(video_id: int):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(404)
    db.delete_pains_for_video(video_id)
    db.update_video(video_id, status="queued", error_msg=None)
    log.info("Retry queued video_id=%d", video_id)
    return RedirectResponse(f"/topics/{video['topic_id']}", status_code=303)


@app.get("/videos/{video_id}")
def video_detail(request: Request, video_id: int):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(404)
    topic = db.get_topic(video["topic_id"])
    pains = db.get_video_pains(video_id)
    return templates.TemplateResponse(request, "video.html", {
        "video": video,
        "topic": topic,
        "pains": pains,
    })


# ── Clusters ──────────────────────────────────────────────────────────────────

@app.get("/clusters/{cluster_id}")
def cluster_detail(request: Request, cluster_id: int):
    cluster = db.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(404)
    topic = db.get_topic(cluster["topic_id"])
    pains = db.get_cluster_pains(cluster_id)
    return templates.TemplateResponse(request, "cluster.html", {
        "cluster": cluster,
        "topic": topic,
        "pains": pains,
    })
