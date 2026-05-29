import os
import json
import logging
import time
from pathlib import Path

from google import genai
from google.genai import types

log = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def _build_extraction_prompt(topic_title: str) -> str:
    market = topic_title.strip() if topic_title.strip() else "the analyzed market"
    output_language = os.environ.get("ANALYSIS_OUTPUT_LANGUAGE", "pt-BR")
    template = (PROMPTS_DIR / "extraction.md").read_text(encoding="utf-8")
    return template.format(market=market, output_language=output_language)


def _client():
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _model():
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")


def _json_config():
    return types.GenerateContentConfig(response_mime_type="application/json")


def _generate_json(contents):
    attempts = int(os.environ.get("GEMINI_MAX_ATTEMPTS", "3"))
    delay = float(os.environ.get("GEMINI_RETRY_BASE_SECONDS", "1"))
    client = _client()
    last_error = None

    for attempt in range(attempts):
        try:
            started = time.monotonic()
            log.info("Gemini call attempt=%d model=%s", attempt + 1, _model())
            response = client.models.generate_content(
                model=_model(),
                contents=contents,
                config=_json_config(),
            )
            elapsed = time.monotonic() - started
            log.info("Gemini call succeeded attempt=%d elapsed=%.2fs", attempt + 1, elapsed)
            return response
        except Exception as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            sleep_for = delay * (2 ** attempt)
            log.warning("Gemini call failed, retrying in %.1fs: %s", sleep_for, exc)
            time.sleep(sleep_for)

    raise last_error


def _parse_json(text: str) -> list | dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop first line (```json or ```) and last line (```)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [idx for idx in (text.find("["), text.find("{")) if idx != -1]
        ends = [idx for idx in (text.rfind("]"), text.rfind("}")) if idx != -1]
        if not starts or not ends:
            raise
        return json.loads(text[min(starts):max(ends) + 1])


def extract_pains_from_transcript(transcript: str, video_url: str = "", topic_title: str = "") -> list[dict]:
    base_prompt = _build_extraction_prompt(topic_title)
    prompt = f"{base_prompt}\n\nVideo transcript{' (' + video_url + ')' if video_url else ''}:\n\n{transcript[:60000]}"
    response = _generate_json(prompt)
    result = _parse_json(response.text)
    if isinstance(result, list):
        return result
    return []


def find_clusters_batch(pains: list[dict], clusters: list[dict]) -> list[int | None]:
    """Single Gemini call to assign all pains to existing clusters.
    Returns a list of cluster_id (int) or None, one per pain, in the same order."""
    if not clusters or not pains:
        return [None] * len(pains)

    pains_text = "\n".join(
        f"{i}. {p.get('title', '')} - {(p.get('summary') or '')[:80]}"
        for i, p in enumerate(pains)
    )
    clusters_text = "\n".join(
        f"ID {c['id']}: {c['title']} - {(c.get('summary') or '')[:80]}"
        for c in clusters
    )

    template = (PROMPTS_DIR / "clustering.md").read_text(encoding="utf-8")
    prompt = template.format(
        pain_count=len(pains),
        pains_text=pains_text,
        clusters_text=clusters_text,
    )

    try:
        response = _generate_json(prompt)
        data = _parse_json(response.text)
        if isinstance(data, list):
            result = []
            for item in data[:len(pains)]:
                try:
                    result.append(int(item) if item is not None else None)
                except (TypeError, ValueError):
                    result.append(None)
            while len(result) < len(pains):
                result.append(None)
            return result
    except Exception as e:
        log.warning("Batch cluster failed: %s", e)

    return [None] * len(pains)
