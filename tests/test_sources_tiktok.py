from sources import get_provider_for_url
from sources.tiktok import TikTokProvider


def test_tiktok_provider_accepts_video_urls():
    provider = TikTokProvider()

    assert provider.can_handle("https://www.tiktok.com/@example/video/1234567890")
    assert provider.external_id("https://www.tiktok.com/@example/video/1234567890") == "1234567890"


def test_tiktok_provider_uses_manual_transcript_fallback():
    provider = TikTokProvider()

    assert provider.fetch_title("https://www.tiktok.com/@example/video/1234567890") is None
    assert provider.fetch_content("1234567890") is None


def test_source_registry_resolves_tiktok_urls():
    provider = get_provider_for_url("https://www.tiktok.com/@example/video/1234567890")

    assert provider is not None
    assert provider.source == "tiktok"
