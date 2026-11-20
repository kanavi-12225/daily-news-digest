from pathlib import Path

import feedparser

from newsbot.collect_news import fetch_category_news, fetch_top_news

FIXTURE = Path(__file__).parent / "fixtures" / "news_rss_sample.xml"


def fake_parse(_url):
    return feedparser.parse(FIXTURE.read_text(encoding="utf-8"))


def test_top_news_returns_first_10_in_feed_order():
    articles = fetch_top_news(limit=10, parse=fake_parse)
    assert len(articles) == 10
    assert [a.url for a in articles] == [
        f"https://news.example.com/article/{i}" for i in range(1, 11)
    ]
    assert articles[0].title == "기사 제목 1 - 매체1"
    assert articles[0].source == "매체1"
    assert articles[0].published.startswith("Fri, 20 Nov 2026")


def test_missing_source_becomes_empty_string():
    articles = fetch_top_news(limit=12, parse=fake_parse)
    assert articles[11].source == ""


def test_category_news_skips_excluded_urls_and_still_returns_3():
    exclude = {
        "https://news.example.com/article/1",
        "https://news.example.com/article/2",
    }
    articles = fetch_category_news(
        "경제·산업", limit=3, exclude_urls=exclude, parse=fake_parse
    )
    assert [a.url for a in articles] == [
        f"https://news.example.com/article/{i}" for i in (3, 4, 5)
    ]


def test_category_news_requests_search_feed_with_category_keywords():
    seen = []

    def spy(url):
        seen.append(url)
        return fake_parse(url)

    fetch_category_news("국제", parse=spy)
    assert "news.google.com/rss/search?q=" in seen[0]
    assert "%EA%B5%AD%EC%A0%9C" in seen[0]  # URL-encoded "국제"
    assert "when%3A1d" in seen[0]  # only the last day


def test_fetch_returns_empty_list_when_feed_raises():
    def boom(_url):
        raise OSError("network down")

    assert fetch_top_news(parse=boom) == []
    assert fetch_category_news("국제", parse=boom) == []


def test_unknown_category_returns_empty_list():
    assert fetch_category_news("없는분류", parse=fake_parse) == []


def test_retries_with_growing_delays_when_feed_comes_back_empty(monkeypatch):
    delays = []
    monkeypatch.setattr("newsbot.collect_news._sleep", delays.append)
    calls = []

    def flaky(url):
        calls.append(url)
        return feedparser.parse("") if len(calls) < 3 else fake_parse(url)

    articles = fetch_top_news(limit=3, parse=flaky)
    assert len(articles) == 3
    assert len(calls) == 3
    assert delays == [2.0, 4.0]


def test_gives_up_after_four_attempts_and_returns_empty_list(monkeypatch):
    delays = []
    monkeypatch.setattr("newsbot.collect_news._sleep", delays.append)
    calls = []

    def always_empty(url):
        calls.append(url)
        return feedparser.parse("")

    assert fetch_top_news(parse=always_empty) == []
    assert len(calls) == 4
    assert delays == [2.0, 4.0, 8.0]


def test_does_not_retry_when_feed_already_has_entries(monkeypatch):
    delays = []
    monkeypatch.setattr("newsbot.collect_news._sleep", delays.append)
    calls = []

    def once(url):
        calls.append(url)
        return fake_parse(url)

    fetch_top_news(parse=once)
    assert len(calls) == 1 and delays == []
