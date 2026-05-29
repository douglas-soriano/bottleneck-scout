from sources.youtube import extract_youtube_id, yt_link_with_ts


def test_extract_youtube_id_supports_common_url_shapes():
    assert extract_youtube_id("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert extract_youtube_id("https://youtu.be/abcdefghijk") == "abcdefghijk"
    assert extract_youtube_id("https://www.youtube.com/shorts/abcdefghijk") == "abcdefghijk"


def test_extract_youtube_id_rejects_unknown_urls():
    assert extract_youtube_id("https://example.com/watch?v=abcdefghijk") is None


def test_yt_link_with_ts_adds_timestamp_when_available():
    assert (
        yt_link_with_ts("abcdefghijk", "https://youtu.be/abcdefghijk", 95)
        == "https://www.youtube.com/watch?v=abcdefghijk&t=95s"
    )


def test_yt_link_with_ts_falls_back_to_original_url_without_timestamp():
    assert yt_link_with_ts("abcdefghijk", "https://youtu.be/abcdefghijk", None) == "https://youtu.be/abcdefghijk"
