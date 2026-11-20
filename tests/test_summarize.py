import json
from types import SimpleNamespace

from newsbot.models import Article, Video
from newsbot.summarize import FALLBACK_HEADLINE, summarize_digest


class FakeMessages:
    def __init__(self, text=None, exc=None):
        self.text = text
        self.exc = exc
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return SimpleNamespace(content=[SimpleNamespace(text=self.text)])


class FakeClient:
    def __init__(self, text=None, exc=None):
        self.messages = FakeMessages(text, exc)


def _inputs():
    a1 = Article("제목1", "http://a/1", "출처A", "2026-11-20")
    a2 = Article("제목2", "http://a/2", "출처B", "2026-11-20")
    v1 = Video("영상1", "http://v/1", "채널X", 1000)
    return [a1], {"경제·산업": [a2]}, [v1]


def test_fills_summaries_and_headline():
    top, cats, vids = _inputs()
    payload = {
        "headline": "오늘의 한 줄",
        "top_news": ["요약1"],
        "by_category": {"경제·산업": ["요약2"]},
        "videos": ["영상요약"],
    }
    client = FakeClient("```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```")
    digest = summarize_digest(top, cats, vids, client)
    assert digest.headline == "오늘의 한 줄"
    assert digest.top_news[0].summary == "요약1"
    assert digest.by_category["경제·산업"][0].summary == "요약2"
    assert digest.videos[0].summary == "영상요약"
    assert digest.errors == []
    prompt = json.dumps(client.messages.calls[0]["messages"], ensure_ascii=False)
    assert "제목1" in prompt and "http://a/1" not in prompt


def test_falls_back_to_titles_only_when_json_invalid():
    top, cats, vids = _inputs()
    digest = summarize_digest(top, cats, vids, FakeClient("not json {"))
    assert digest.headline == FALLBACK_HEADLINE == "오늘의 뉴스가 도착했어요"
    assert digest.top_news[0].summary is None
    assert digest.by_category["경제·산업"][0].summary is None
    assert digest.videos[0].summary is None
    assert digest.errors


def test_falls_back_when_api_raises():
    top, cats, vids = _inputs()
    digest = summarize_digest(top, cats, vids, FakeClient(exc=RuntimeError("boom")))
    assert digest.headline == FALLBACK_HEADLINE
    assert digest.top_news[0].summary is None
    assert digest.errors


def test_headline_is_truncated_to_120_chars():
    top, cats, vids = _inputs()
    payload = {"headline": "가" * 300, "top_news": ["a"], "by_category": {}, "videos": []}
    digest = summarize_digest(top, cats, vids, FakeClient(json.dumps(payload)))
    assert len(digest.headline) == 120
    assert digest.headline.endswith("…")
