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
        "top_news": [{"id": 0, "summary": "요약1"}],
        "by_category": {"경제·산업": [{"id": 0, "summary": "요약2"}]},
        "videos": [{"id": 0, "summary": "영상요약"}],
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
    assert "boom" not in str(digest.errors)


def _reply(ids):
    return FakeClient(
        json.dumps(
            {
                "headline": "h",
                "top_news": [{"id": i, "summary": f"s{i}"} for i in ids],
                "by_category": {},
                "videos": [],
            }
        )
    )


def _four():
    return [Article(f"제목{i}", f"http://a/{i}", "S", "d") for i in range(4)]


def test_omitted_middle_id_keeps_later_summaries_aligned():
    digest = summarize_digest(_four(), {}, [], _reply([0, 1, 3]))
    assert [s.summary for s in digest.top_news] == ["s0", "s1", None, "s3"]


def test_out_of_order_ids_map_correctly():
    digest = summarize_digest(_four(), {}, [], _reply([2, 0, 3, 1]))
    assert [s.summary for s in digest.top_news] == ["s0", "s1", "s2", "s3"]


def test_max_tokens_stop_reason_falls_back_with_note():
    top, cats, vids = _inputs()
    client = FakeClient('{"headline": "x"')
    orig = client.messages.create

    def create(**kw):
        r = orig(**kw)
        r.stop_reason = "max_tokens"
        return r

    client.messages.create = create
    digest = summarize_digest(top, cats, vids, client)
    assert digest.headline == FALLBACK_HEADLINE
    assert any("max_tokens" in e for e in digest.errors)


def test_headline_is_truncated_to_120_chars():
    top, cats, vids = _inputs()
    payload = {"headline": "가" * 300, "top_news": ["a"], "by_category": {}, "videos": []}
    digest = summarize_digest(top, cats, vids, FakeClient(json.dumps(payload)))
    assert len(digest.headline) == 120
    assert digest.headline.endswith("…")
