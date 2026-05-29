import importlib


def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import db

    importlib.reload(db)
    db.init_db()
    return db


def test_save_pains_replaces_existing_video_pains(monkeypatch, tmp_path):
    db = fresh_db(monkeypatch, tmp_path)
    import worker

    importlib.reload(worker)
    monkeypatch.setattr(worker.gemini_client, "find_clusters_batch", lambda pains, clusters: [None] * len(pains))

    topic_id = db.create_topic("Publishing")
    video_id = db.add_item(topic_id, "youtube", "https://youtu.be/abcdefghijk", "abcdefghijk")

    first = [{
        "title": "Manual reports",
        "summary": "Teams copy data by hand.",
        "category": "operational",
        "timestamp_seconds": 10,
        "severity": 4,
        "confidence": "high",
        "commercial_actionability": 5,
    }]
    second = [{
        "title": "Slow approvals",
        "summary": "Approvals block releases.",
        "category": "operational",
        "timestamp_seconds": 20,
        "severity": 3,
        "confidence": "medium",
        "commercial_actionability": 4,
    }]

    worker.save_pains(video_id, topic_id, first, "https://youtu.be/abcdefghijk")
    worker.save_pains(video_id, topic_id, second, "https://youtu.be/abcdefghijk")

    pains = db.get_video_pains(video_id)
    ranking = db.get_topic_ranking(topic_id)

    assert [pain["title"] for pain in pains] == ["Slow approvals"]
    assert len(ranking) == 1
    assert ranking[0]["mention_count"] == 1
    assert ranking[0]["video_count"] == 1


def test_manual_transcript_submission_requeues_without_llm(monkeypatch, tmp_path):
    db = fresh_db(monkeypatch, tmp_path)
    import app

    importlib.reload(app)

    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("LLM should not run in the HTTP request")

    monkeypatch.setattr(app.worker.gemini_client, "extract_pains_from_transcript", fail_if_called)

    topic_id = db.create_topic("Publishing")
    video_id = db.add_item(topic_id, "youtube", "https://youtu.be/abcdefghijk", "abcdefghijk")
    db.update_video(video_id, status="waiting_manual_transcript")

    response = app.submit_transcript(video_id, " [00:01] Manual work hurts margins. ")
    video = db.get_video(video_id)

    assert response.status_code == 303
    assert video["status"] == "queued"
    assert video["transcript"] == "[00:01] Manual work hurts margins."
    assert called is False


def test_retry_requeues_and_clears_stale_pains(monkeypatch, tmp_path):
    db = fresh_db(monkeypatch, tmp_path)
    import app

    importlib.reload(app)

    topic_id = db.create_topic("Publishing")
    video_id = db.add_item(topic_id, "youtube", "https://youtu.be/abcdefghijk", "abcdefghijk")
    cluster_id = db.insert_cluster(topic_id, "Manual reports", "operational", None, None)
    db.insert_pain({
        "video_id": video_id,
        "topic_id": topic_id,
        "cluster_id": cluster_id,
        "title": "Manual reports",
        "commercial_actionability": 5,
    })
    db.update_video(video_id, status="failed", error_msg="temporary failure")

    response = app.retry_video(video_id)
    video = db.get_video(video_id)

    assert response.status_code == 303
    assert video["status"] == "queued"
    assert video["error_msg"] is None
    assert db.get_video_pains(video_id) == []
    assert db.get_topic_ranking(topic_id) == []
