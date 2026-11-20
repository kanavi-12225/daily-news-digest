from datetime import datetime

import pytest

from newsbot.config import CATEGORIES
from newsbot.models import Article, ArticleSummary, Digest, Video, VideoSummary
from newsbot.render_page import render_page, write_pages

NOW = datetime(2026, 11, 20, 7, 30)


def _art(title="제목", url="https://example.com/a", source="언론사", summary="요약"):
    return ArticleSummary(Article(title, url, source, "2026-11-20"), summary)


def _digest(**kw):
    base = dict(top_news=[_art()], by_category={}, videos=[], headline="헤드라인")
    base.update(kw)
    return Digest(**base)


def test_titles_are_html_escaped():
    bad = '<script>x</script> & "a"'
    d = _digest(
        top_news=[_art(title=bad, summary=bad, source=bad)],
        videos=[VideoSummary(Video(bad, "https://y.com/v", bad, 10), bad)],
    )
    html = render_page(d, "morning", NOW)
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt; &amp; &#34;a&#34;" in html


def test_errors_are_shown_as_notice():
    html = render_page(_digest(errors=["뉴스 수집 실패 <b>"]), "morning", NOW)
    assert "뉴스 수집 실패 &lt;b&gt;" in html
    assert 'class="notice"' in html


def test_page_shows_slot_label_and_date():
    m = render_page(_digest(), "morning", NOW)
    e = render_page(_digest(), "evening", NOW)
    assert "2026-11-20" in m and "아침" in m
    assert "저녁" in e and "아침" not in e.split("<body>")[1]


def test_unknown_slot_raises(tmp_path):
    with pytest.raises(ValueError):
        render_page(_digest(), "noon", NOW)
    with pytest.raises(ValueError):
        write_pages("x", "noon", NOW, tmp_path)


def test_javascript_url_is_not_linked():
    d = _digest(top_news=[_art(url="javascript:alert(1)")])
    html = render_page(d, "morning", NOW)
    assert 'href="javascript' not in html
    assert "<a " not in html.split("<body>")[1].split("전체 뉴스 TOP10")[1].split("분야별")[0]


def test_http_url_is_linked():
    html = render_page(_digest(), "morning", NOW)
    assert 'href="https://example.com/a"' in html


def test_section_order_and_empty_notices():
    d = _digest(top_news=[], by_category={CATEGORIES_FIRST: [_art(title="정치기사")]}, videos=[])
    html = render_page(d, "morning", NOW)
    names = ["전체 뉴스 TOP10", "분야별 TOP3", "유튜브 TOP10"]
    pos = [html.index(n) for n in names]
    assert pos == sorted(pos)
    assert "오늘은 가져오지 못했어요" in html
    cats = list(CATEGORIES)
    cpos = [html.index(c) for c in cats]
    assert cpos == sorted(cpos)
    assert html.count("오늘은 가져오지 못했어요") >= 1 + (len(cats) - 1) + 1


def test_none_summary_shows_title_and_link_only():
    d = _digest(top_news=[_art(title="무요약", summary=None)])
    html = render_page(d, "morning", NOW)
    assert "무요약" in html
    assert 'class="summary"' not in html


CATEGORIES_FIRST = next(iter(CATEGORIES))


def test_write_pages_updates_index_and_archive(tmp_path):
    docs = tmp_path / "docs"
    path = write_pages("<html>한글</html>", "evening", NOW, docs)
    assert path == docs / "archive" / "2026-11-20-evening.html"
    assert path.read_text(encoding="utf-8") == "<html>한글</html>"
    assert (docs / "index.html").read_text(encoding="utf-8") == "<html>한글</html>"
