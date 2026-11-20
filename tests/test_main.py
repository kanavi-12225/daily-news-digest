from datetime import datetime, timedelta, timezone

import json

import pytest

from newsbot.config import CATEGORIES
from newsbot.kakao import KakaoError, TokenPair
from newsbot.main import _default_summarize, load_dotenv, make_sender, run
from newsbot.models import Article, ArticleSummary, Digest, Video, VideoSummary

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 20, 8, 0, tzinfo=KST)
BASE_URL = "https://user.github.io/newsbot/"


def article(n: int) -> Article:
    return Article(title=f"기사 {n}", url=f"https://news.example/{n}", source="매체", published="")


def video(n: int) -> Video:
    return Video(title=f"영상 {n}", url=f"https://youtu.be/{n}", channel="채널", views=n)


def fake_summarize(top, cats, videos):
    return Digest(
        top_news=[ArticleSummary(a, None) for a in top],
        by_category={c: [ArticleSummary(a, None) for a in items] for c, items in cats.items()},
        videos=[VideoSummary(v, None) for v in videos],
        headline="오늘의 헤드라인",
    )


class Recorder:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result
        self.error = error

    def __call__(self, text, link_url):
        self.calls.append((text, link_url))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def pages_env(monkeypatch):
    monkeypatch.setenv("PAGES_BASE_URL", BASE_URL)


def go(tmp_path, send=None, top=None, cat=None, vids=None, summarize=None, **kwargs):
    send = send if send is not None else Recorder()
    code = run(
        "morning",
        now=NOW,
        fetch_top=lambda: [article(n) for n in range(10)] if top is None else top,
        fetch_category=cat or (lambda category, exclude_urls: [article(100 + len(category))]),
        fetch_videos=lambda: [video(n) for n in range(10)] if vids is None else vids,
        summarize=summarize or fake_summarize,
        send=send,
        docs_dir=tmp_path / "docs",
        token_file=tmp_path / ".new_refresh_token",
        message_file=tmp_path / ".digest_message",
        **kwargs,
    )
    return code, send


def test_partial_failure_still_renders_and_sends(tmp_path):
    code, send = go(tmp_path, vids=[])
    assert code == 0
    assert len(send.calls) == 1
    page = (tmp_path / "docs" / "archive" / "2026-11-20-morning.html").read_text(encoding="utf-8")
    assert "기사 0" in page
    assert "유튜브" in page and "가져오지 못했어요" in page
    assert (tmp_path / "docs" / "index.html").exists()


def test_all_sources_empty_returns_nonzero(tmp_path):
    code, send = go(tmp_path, top=[], cat=lambda category, exclude_urls: [], vids=[])
    assert code != 0
    assert send.calls == []
    assert not (tmp_path / "docs").exists()


def test_dry_run_does_not_send_or_write(tmp_path, capsys):
    code, send = go(tmp_path, dry_run=True)
    assert code == 0
    assert send.calls == []
    assert not (tmp_path / "docs").exists()
    assert "오늘의 헤드라인" in capsys.readouterr().out


def test_categories_exclude_top_news_urls(tmp_path):
    seen = {}

    def cat(category, exclude_urls):
        seen[category] = set(exclude_urls)
        return [article(200)]

    go(tmp_path, cat=cat)
    top_urls = {f"https://news.example/{n}" for n in range(10)}
    names = list(seen)
    assert names == list(CATEGORIES)
    assert seen[names[0]] == top_urls
    assert all(top_urls <= seen[name] for name in names)


def test_categories_do_not_repeat_articles_across_categories(tmp_path):
    pool = [article(n) for n in range(300, 330)]
    captured = {}

    def cat(category, exclude_urls):
        return [a for a in pool if a.url not in exclude_urls][:3]

    def spy(top, cats, videos):
        captured.update(cats)
        return fake_summarize(top, cats, videos)

    go(tmp_path, cat=cat, summarize=spy)
    urls = [a.url for items in captured.values() for a in items]
    assert len(urls) == 18 and len(set(urls)) == 18


def test_kakao_text_is_headline_newline_page_url(tmp_path):
    _, send = go(tmp_path)
    text, link = send.calls[0]
    url = "https://user.github.io/newsbot/archive/2026-11-20-morning.html"
    assert text == f"오늘의 헤드라인\n{url}"
    assert link == url


def test_send_failure_returns_nonzero(tmp_path):
    code, _ = go(tmp_path, send=Recorder(error=KakaoError("send memo failed: HTTP 500")))
    assert code != 0


def test_rotated_refresh_token_is_written_to_file(tmp_path):
    go(tmp_path, send=Recorder(result=TokenPair("a", "new-refresh")))
    assert (tmp_path / ".new_refresh_token").read_text(encoding="utf-8") == "new-refresh"


def test_no_token_file_when_refresh_token_not_rotated(tmp_path):
    go(tmp_path, send=Recorder(result=TokenPair("a", None)))
    go(tmp_path, send=Recorder(result=None))
    assert not (tmp_path / ".new_refresh_token").exists()


def test_unknown_slot_raises(tmp_path):
    with pytest.raises(ValueError):
        run("noon", now=NOW, docs_dir=tmp_path / "docs")


def test_load_dotenv_sets_missing_vars_only(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('# note\nNB_A=1\nNB_B="quoted value"\n\nNB_KEEP=file\n', encoding="utf-8")
    monkeypatch.delenv("NB_A", raising=False)
    monkeypatch.delenv("NB_B", raising=False)
    monkeypatch.setenv("NB_KEEP", "shell")
    load_dotenv(env_file)
    import os

    assert os.environ["NB_A"] == "1"
    assert os.environ["NB_B"] == "quoted value"
    assert os.environ["NB_KEEP"] == "shell"
    monkeypatch.delenv("NB_A")
    monkeypatch.delenv("NB_B")


def test_build_phase_writes_page_and_message_but_does_not_send(tmp_path):
    code, send = go(tmp_path, phase="build")
    assert code == 0
    assert send.calls == []
    url = "https://user.github.io/newsbot/archive/2026-11-20-morning.html"
    message = json.loads((tmp_path / ".digest_message").read_text(encoding="utf-8"))
    assert message == {"text": f"오늘의 헤드라인\n{url}", "link": url}
    assert (tmp_path / "docs" / "archive" / "2026-11-20-morning.html").exists()


def test_send_phase_sends_saved_message_without_collecting(tmp_path):
    go(tmp_path, phase="build")

    def boom(*_a, **_k):
        raise AssertionError("must not collect in send phase")

    send = Recorder()
    code = run(
        "morning",
        now=NOW,
        phase="send",
        fetch_top=boom,
        fetch_category=boom,
        fetch_videos=boom,
        summarize=boom,
        send=send,
        docs_dir=tmp_path / "docs",
        token_file=tmp_path / ".new_refresh_token",
        message_file=tmp_path / ".digest_message",
    )
    assert code == 0
    url = "https://user.github.io/newsbot/archive/2026-11-20-morning.html"
    assert send.calls == [(f"오늘의 헤드라인\n{url}", url)]


def test_send_phase_without_message_file_returns_nonzero(tmp_path):
    send = Recorder()
    code = run(
        "morning",
        now=NOW,
        phase="send",
        send=send,
        docs_dir=tmp_path / "docs",
        token_file=tmp_path / ".new_refresh_token",
        message_file=tmp_path / ".digest_message",
    )
    assert code != 0 and send.calls == []


def test_unknown_phase_raises(tmp_path):
    with pytest.raises(ValueError):
        run("morning", now=NOW, phase="bogus", docs_dir=tmp_path / "docs")


def test_sender_persists_rotated_token_even_when_resend_fails(tmp_path, monkeypatch):
    for name in ("KAKAO_REST_API_KEY", "KAKAO_ACCESS_TOKEN", "KAKAO_REFRESH_TOKEN"):
        monkeypatch.setenv(name, "x")

    def fake_send_with_refresh(*args, on_refresh=None, **kwargs):
        on_refresh(TokenPair("A2", "R9"))
        raise KakaoError("send memo failed: HTTP 500")

    monkeypatch.setattr("newsbot.main.send_with_refresh", fake_send_with_refresh)
    token_file = tmp_path / ".new_refresh_token"
    with pytest.raises(KakaoError):
        make_sender(token_file)("t", "https://x.io")
    assert token_file.read_text(encoding="utf-8") == "R9"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_default_summarize_skips_ai_when_key_missing_or_blank(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", value)
    digest = _default_summarize([article(1)], {"국제": [article(2)]}, [video(3)])
    assert digest.top_news[0].summary is None
    assert digest.errors == []
