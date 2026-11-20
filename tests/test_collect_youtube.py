import pytest

from newsbot.collect_youtube import fetch_trending


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "SECRET-KEY")


def test_parses_title_channel_views_and_builds_watch_url():
    payload = {
        "items": [
            {
                "id": "abc123",
                "snippet": {"title": "제목", "channelTitle": "채널"},
                "statistics": {"viewCount": "12345"},
            },
            {"id": "nov", "snippet": {"title": "t", "channelTitle": "c"}, "statistics": {}},
        ]
    }
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        return FakeResponse(payload)

    videos = fetch_trending(limit=5, http_get=fake_get)
    assert videos[0].title == "제목"
    assert videos[0].channel == "채널"
    assert videos[0].views == 12345
    assert videos[0].url == "https://www.youtube.com/watch?v=abc123"
    assert videos[1].views == 0
    params = calls[0][1]
    assert params["chart"] == "mostPopular"
    assert params["regionCode"] == "KR"
    assert params["part"] == "snippet,statistics"
    assert params["maxResults"] == 5
    assert params["key"] == "SECRET-KEY"


def test_returns_empty_when_api_returns_error_status():
    assert fetch_trending(http_get=lambda *a, **k: FakeResponse({}, status=403)) == []


def test_returns_empty_on_network_error_without_leaking_key():
    def boom(*a, **k):
        raise ConnectionError("failed ?key=SECRET-KEY")

    assert fetch_trending(http_get=boom) == []


def test_returns_empty_on_malformed_payload():
    assert fetch_trending(http_get=lambda *a, **k: FakeResponse({"items": "x"})) == []


def test_missing_key_propagates(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY")
    with pytest.raises(RuntimeError):
        fetch_trending(http_get=lambda *a, **k: FakeResponse({}))
