import argparse
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from newsbot.collect_news import fetch_category_news, fetch_top_news
from newsbot.collect_youtube import fetch_trending
from newsbot.config import CATEGORIES, get_env
from newsbot.kakao import KakaoError, send_with_refresh
from newsbot.render_page import SLOT_LABELS, render_page, write_pages

KST = timezone(timedelta(hours=9))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"
TOKEN_FILE = PROJECT_ROOT / ".new_refresh_token"


def load_dotenv(path: Path) -> None:
    """KEY=VALUE 줄을 읽어 아직 설정되지 않은 환경변수만 채운다 (이미 있는 값은 덮어쓰지 않는다)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def _default_category(category: str, exclude_urls: set[str]):
    return fetch_category_news(category, 3, exclude_urls)


def _default_summarize(top, by_category, videos):
    import anthropic

    from newsbot.summarize import summarize_digest

    client = anthropic.Anthropic(api_key=get_env("ANTHROPIC_API_KEY"))
    return summarize_digest(top, by_category, videos, client)


def _default_send(text: str, link_url: str):
    return send_with_refresh(
        get_env("KAKAO_REST_API_KEY"),
        get_env("KAKAO_ACCESS_TOKEN"),
        get_env("KAKAO_REFRESH_TOKEN"),
        text,
        link_url,
        client_secret=os.environ.get("KAKAO_CLIENT_SECRET") or None,
    )


def run(
    slot: str,
    dry_run: bool = False,
    now: datetime | None = None,
    *,
    fetch_top=fetch_top_news,
    fetch_category=_default_category,
    fetch_videos=fetch_trending,
    summarize=_default_summarize,
    send=_default_send,
    docs_dir: Path = DOCS_DIR,
    token_file: Path = TOKEN_FILE,
) -> int:
    if slot not in SLOT_LABELS:
        raise ValueError(f"unknown slot: {slot!r}")
    now = now or datetime.now(KST)

    top = fetch_top()
    exclude = {a.url for a in top}
    by_category = {c: fetch_category(c, exclude) for c in CATEGORIES}
    videos = fetch_videos()

    if not top and not videos and not any(by_category.values()):
        print("수집된 항목이 하나도 없어 중단합니다.", file=sys.stderr)
        return 1

    notes = []
    if not top:
        notes.append("전체 뉴스 TOP10을 가져오지 못했어요.")
    for category, items in by_category.items():
        if not items:
            notes.append(f"{category} 분야 뉴스를 가져오지 못했어요.")
    if not videos:
        notes.append("유튜브 TOP10을 가져오지 못했어요.")

    digest = summarize(top, by_category, videos)
    digest = replace(digest, errors=notes + list(digest.errors))
    html = render_page(digest, slot, now)

    if dry_run:
        print(f"[dry-run] {digest.headline}")
        print(f"[dry-run] 뉴스 {len(top)}건, 분야 {sum(map(len, by_category.values()))}건, 유튜브 {len(videos)}건")
        for note in digest.errors:
            print(f"[dry-run] 알림: {note}")
        return 0

    base_url = get_env("PAGES_BASE_URL").rstrip("/")
    archive = write_pages(html, slot, now, docs_dir)
    page_url = f"{base_url}/archive/{archive.name}"

    try:
        pair = send(f"{digest.headline}\n{page_url}", page_url)
    except KakaoError as exc:
        print(f"카카오 전송 실패: {exc}", file=sys.stderr)
        return 1

    if pair is not None and pair.refresh_token:
        token_file.write_text(pair.refresh_token, encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="newsbot")
    parser.add_argument("--slot", choices=sorted(SLOT_LABELS), required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")
    return run(args.slot, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
