from urllib.parse import urlparse


class TikTokProvider:
    source = "tiktok"

    def can_handle(self, url: str) -> bool:
        return "tiktok.com" in urlparse(url).netloc.lower()

    def external_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        if "video" in parts:
            idx = parts.index("video")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return parsed.path.strip("/") or url

    def fetch_title(self, url: str) -> str | None:
        return None

    def fetch_content(self, external_id: str) -> str | None:
        return None

    def evidence_link(self, external_id: str | None, url: str, seconds: int | None) -> str:
        return url
