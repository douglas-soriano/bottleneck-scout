import pytest

from gemini_client import _parse_json


def test_parse_json_accepts_plain_json_array():
    assert _parse_json('[{"title": "Manual reporting"}]') == [{"title": "Manual reporting"}]


def test_parse_json_accepts_markdown_fenced_json():
    text = """```json
[{"title": "Slow onboarding"}]
```"""
    assert _parse_json(text) == [{"title": "Slow onboarding"}]


def test_parse_json_extracts_json_from_extra_text():
    text = 'Here is the result: [{"title": "High churn"}] done.'
    assert _parse_json(text) == [{"title": "High churn"}]


def test_parse_json_raises_for_non_json_text():
    with pytest.raises(ValueError):
        _parse_json("no json here")
