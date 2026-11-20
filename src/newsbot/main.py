import argparse
import json
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
MESSAGE_FILE = PROJECT_ROOT / ".digest_message"
PHASES = ("all", "build", "send")


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


def _persist_refresh_token(pair, token_file: Path) -> None:
    if pair is not None and pair.refresh_token:
        token_file.write_text(pair.refresh_token, encoding="utf-8")


def make_sender(token_file: Path):
    """카카오 전송 함수를 만든다. 토큰이 갱신되면 재전송 전에 바로 파일에 남긴다."""

    def send(text: str, link_url: str):
        return send_with_refresh(
            get_env("KAKAO_REST_API_KEY"),
            get_env("KAKAO_ACCESS_TOKEN"),
            get_env("KAKAO_REFRESH_TOKEN"),
            text,
            link_url,
            client_secret=os.environ.get("KAKAO_CLIENT_SECRET") or None,
            on_refresh=lambda pair: _persist_refresh_token(pair, token_file),
        )

    return send


def _deliver(send, text: str, link_url: str, token_file: Path) -> int:
    try:
        pair = send(text, link_url)
    except KakaoError as exc:
        print(f"카카오 전송 실패: {exc}", file=sys.stderr)
        return 1
    _persist_refresh_token(pair, token_file)
    return 0


def run(
    slot: str,
    dry_run: bool = False,
    now: datetime | None = None,
    *,
    phase: str = "all",
    fetch_top=fetch_top_news,
    fetch_category=_default_category,
    fetch_videos=fetch_trending,
    summarize=_default_summarize,
    send=None,
    docs_dir: Path = DOCS_DIR,
    token_file: Path = TOKEN_FILE,
    message_file: Path = MESSAGE_FILE,
) -> int:
    if slot not in SLOT_LABELS:
        raise ValueError(f"unknown slot: {slot!r}")
    if phase not in PHASES:
        raise ValueError(f"unknown phase: {phase!r}")
    send = send or make_sender(token_file)

    if phase == "send":
        try:
            message = json.loads(message_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("보낼 메시지 파일이 없습니다. 먼저 --phase build 를 실행하세요.", file=sys.stderr)
            return 1
        return _deliver(send, message["text"], message["link"], token_file)

    now = now or datetime.now(KST)

    top = fetch_top()
    exclude = {a.url for a in top}
    by_category = {}
    for category in CATEGORIES:
        items = fetch_category(category, set(exclude))
        by_category[category] = items
        exclude.update(a.url for a in items)  # 분야끼리도 같은 기사가 겹치지 않게 한다
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
    text = f"{digest.headline}\n{page_url}"

    if phase == "build":
        message_file.write_text(json.dumps({"text": text, "link": page_url}, ensure_ascii=False), encoding="utf-8")
        return 0
    return _deliver(send, text, page_url, token_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="newsbot")
    parser.add_argument("--slot", choices=sorted(SLOT_LABELS), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--phase",
        choices=PHASES,
        default="all",
        help="build: 페이지만 만들고 메시지를 저장, send: 저장된 메시지만 전송, all: 둘 다 (기본)",
    )
    args = parser.parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")
    return run(args.slot, dry_run=args.dry_run, phase=args.phase)


if __name__ == "__main__":
    raise SystemExit(main())
