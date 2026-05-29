# Business Bottlenecks Finder

Local-first research tool that turns long-form market conversations into ranked business pains. Add YouTube links to a topic, let the worker fetch transcripts, and review the extracted bottlenecks grouped by recurring pain point.

The project is intentionally small: FastAPI, SQLite, Jinja templates, a table-backed queue, and Gemini for extraction/clustering.

## What It Does

- Creates research topics for a market or niche.
- Queues YouTube videos for processing.
- Accepts TikTok URLs as manual-transcript sources.
- Fetches transcripts when available.
- Falls back to manual transcript submission when captions are unavailable.
- Extracts business pains from transcripts with structured JSON output.
- Clusters similar pains and ranks them by reach, severity, confidence, and commercial actionability.
- Keeps processing idempotent: retrying a video replaces its previous pains instead of double-counting them.

## Architecture

```text
FastAPI routes
  -> SQLite-backed queue in videos
  -> background worker
  -> source provider (YouTube today)
  -> transcript/content
  -> Gemini extraction
  -> Gemini clustering
  -> pains + pain_clusters ranking
```

Key modules:

- `app.py`: HTTP routes and form handling.
- `worker.py`: queue loop and pipeline orchestration.
- `db.py`: SQLite schema, migrations, and queries.
- `gemini_client.py`: JSON-mode Gemini calls, prompt loading, and retry/backoff.
- `sources/`: minimal source-provider boundary. YouTube has automatic transcript fetching; TikTok is accepted as a manual-transcript source.
- `prompts/`: versioned extraction and clustering prompts.
- `tests/`: deterministic coverage for parsing, YouTube helpers, manual transcript queueing, and retry idempotency.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env`, then run:

```bash
uvicorn app:app
```

Open `http://127.0.0.1:8000`.

## Runtime Notes

The worker is an in-process background thread. For local usage, run a single Uvicorn process. Do not run with multiple Uvicorn workers, and avoid `--reload` for real processing runs, unless the worker is split into a separate process. Otherwise more than one worker can consume the same SQLite queue.

Manual transcript submission does not call Gemini inside the request. It saves the transcript, marks the item as `queued`, and lets the same worker path process it.

## Configuration

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash-lite
DB_PATH=data.db
ANALYSIS_OUTPUT_LANGUAGE=pt-BR
GEMINI_MAX_ATTEMPTS=3
GEMINI_RETRY_BASE_SECONDS=1
```

## Tests

```bash
pytest
```
