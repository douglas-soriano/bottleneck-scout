from typing import Protocol


class SourceProvider(Protocol):
    source: str

    def can_handle(self, url: str) -> bool:
        ...

    def external_id(self, url: str) -> str | None:
        ...

    def fetch_title(self, url: str) -> str | None:
        ...

    def fetch_content(self, external_id: str) -> str | None:
        ...

    def evidence_link(self, external_id: str | None, url: str, seconds: int | None) -> str:
        ...


def get_provider_for_url(url: str) -> SourceProvider | None:
    from .tiktok import TikTokProvider
    from .youtube import YouTubeProvider

    providers: list[SourceProvider] = [YouTubeProvider(), TikTokProvider()]
    for provider in providers:
        if provider.can_handle(url):
            return provider
    return None
