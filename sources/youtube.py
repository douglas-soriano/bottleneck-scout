import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx
from youtube_transcript_api import YouTubeTranscriptApi

log = logging.getLogger(__name__)

YT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

PREFERRED_LANGS = ["pt-BR", "pt", "en"]


def extract_youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate if re.fullmatch(r"[a-zA-Z0-9_-]{11}", candidate) else None

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
            return candidate if candidate and re.fullmatch(r"[a-zA-Z0-9_-]{11}", candidate) else None
        match = re.search(r"/shorts/([a-zA-Z0-9_-]{11})", parsed.path)
        return match.group(1) if match else None

    return None


def yt_link_with_ts(youtube_id: str | None, url: str, seconds: int | None) -> str:
    if seconds and youtube_id:
        return f"https://www.youtube.com/watch?v={youtube_id}&t={int(seconds)}s"
    return url


class YouTubeProvider:
    source = "youtube"

    def can_handle(self, url: str) -> bool:
        return extract_youtube_id(url) is not None

    def external_id(self, url: str) -> str | None:
        return extract_youtube_id(url)

    def fetch_title(self, url: str) -> str | None:
        try:
            response = httpx.get(
                f"https://www.youtube.com/oembed?url={url}&format=json",
                timeout=10,
                follow_redirects=True,
            )
            if response.status_code == 200:
                return response.json().get("title")
        except Exception:
            pass
        return None

    def fetch_content(self, external_id: str) -> str | None:
        return get_transcript(external_id)

    def evidence_link(self, external_id: str | None, url: str, seconds: int | None) -> str:
        return yt_link_with_ts(external_id, url, seconds)


def get_transcript(youtube_id: str) -> str | None:
    """
    Fetch YouTube captions via youtube-transcript-api.
    Tries pt-BR, pt, en; accepts auto-generated captions.
    Returns formatted transcript string with [MM:SS] timestamps, or None.
    """
    api = YouTubeTranscriptApi()

    try:
        snippets = api.fetch(youtube_id, languages=PREFERRED_LANGS)
        snippets = list(snippets)
    except Exception as e1:
        log.info("Transcript: preferred languages failed (%s), trying any", e1)
        try:
            transcript_list = api.list(youtube_id)
            chosen = None
            candidates = list(transcript_list)
            manual = [t for t in candidates if not t.is_generated]
            auto = [t for t in candidates if t.is_generated]
            for lang in PREFERRED_LANGS:
                for transcript in manual:
                    if transcript.language_code == lang:
                        chosen = transcript
                        break
                if chosen:
                    break
            if not chosen:
                for lang in PREFERRED_LANGS:
                    for transcript in auto:
                        if transcript.language_code == lang:
                            chosen = transcript
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
                chosen.language_code,
                chosen.is_generated,
                youtube_id,
            )
            snippets = list(chosen.fetch())
        except Exception as e2:
            log.warning("Transcript: all attempts failed for %s: %s", youtube_id, e2)
            return None

    if not snippets:
        log.warning("Transcript: empty result for %s", youtube_id)
        return None

    parts = []
    for snippet in snippets:
        start = int(snippet.start)
        mm, ss = divmod(start, 60)
        parts.append(f"[{mm:02d}:{ss:02d}] {snippet.text}")

    log.info("Transcript: %d segments for %s", len(parts), youtube_id)
    return "\n".join(parts)
