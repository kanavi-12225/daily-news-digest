import json
import re

from newsbot.config import SUMMARY_MAX_TOKENS, SUMMARY_MODEL
from newsbot.models import Article, ArticleSummary, Digest, Video, VideoSummary

FALLBACK_HEADLINE = "오늘의 뉴스가 도착했어요"
HEADLINE_MAX = 120

SYSTEM_PROMPT = (
    "당신은 한국어 뉴스 요약 도우미입니다. 제공되는 것은 기사/영상의 제목뿐입니다. "
    "각 항목을 1문장(80자 이내)의 한국어로 요약하되, 제목이 뒷받침하는 사실만 쓰고 "
    "제목에 없는 내용은 절대 지어내지 마세요. "
    "마지막으로 전체를 아우르는 한 줄 요약(headline)을 120자 이내로 쓰세요. "
    "반드시 JSON 객체 하나만 출력하고 다른 설명은 쓰지 마세요."
)


def _build_prompt(top_news, by_category, videos) -> str:
    lines = ["[top_news]"]
    lines += [f"{i}. {a.title} ({a.source})" for i, a in enumerate(top_news)]
    for cat, arts in by_category.items():
        lines.append(f"[category: {cat}]")
        lines += [f"{i}. {a.title} ({a.source})" for i, a in enumerate(arts)]
    lines.append("[videos]")
    lines += [f"{i}. {v.title} (채널: {v.channel})" for i, v in enumerate(videos)]
    lines.append(
        '\n다음 형식의 JSON만 출력하세요. id는 위에 붙은 항목 번호(각 목록 안의 번호)이며, '
        '요약하지 못한 항목은 생략해도 됩니다:\n'
        '{"headline": "...", "top_news": [{"id": 0, "summary": "요약"}, ...], '
        '"by_category": {"카테고리명": [{"id": 0, "summary": "요약"}, ...]}, '
        '"videos": [{"id": 0, "summary": "요약"}, ...]}'
    )
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if m:
        text = m.group(1)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("response JSON is not an object")
    return data


def _by_id(values) -> dict[int, str]:
    result: dict[int, str] = {}
    if not isinstance(values, list):
        return result
    for item in values:
        if not isinstance(item, dict):
            continue
        item_id, summary = item.get("id"), item.get("summary")
        if isinstance(item_id, bool) or not isinstance(item_id, int):
            continue
        if isinstance(summary, str) and summary.strip():
            result.setdefault(item_id, summary.strip())
    return result


def _truncate(headline: str) -> str:
    if len(headline) <= HEADLINE_MAX:
        return headline
    return headline[: HEADLINE_MAX - 1] + "…"


def _assemble(top_news, by_category, videos, data, headline, errors) -> Digest:
    cat_data = data.get("by_category")
    if not isinstance(cat_data, dict):
        cat_data = {}
    top_map = _by_id(data.get("top_news"))
    video_map = _by_id(data.get("videos"))
    return Digest(
        top_news=[ArticleSummary(a, top_map.get(i)) for i, a in enumerate(top_news)],
        by_category={
            cat: [ArticleSummary(a, cmap.get(i)) for i, a in enumerate(arts)]
            for cat, arts in by_category.items()
            for cmap in [_by_id(cat_data.get(cat))]
        },
        videos=[VideoSummary(v, video_map.get(i)) for i, v in enumerate(videos)],
        headline=headline,
        errors=errors,
    )


def summarize_digest(
    top_news: list[Article],
    by_category: dict[str, list[Article]],
    videos: list[Video],
    client,
) -> Digest:
    try:
        response = client.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=SUMMARY_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": _build_prompt(top_news, by_category, videos)}
            ],
        )
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ValueError("max_tokens")
        # 생각(thinking) 블록 등이 앞에 올 수 있으므로 text 블록만 이어 붙인다
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        data = _parse_json(text)
    except Exception as exc:  # API failure or unparseable response; never include secrets
        reason = "max_tokens" if str(exc) == "max_tokens" else type(exc).__name__
        return _assemble(
            top_news,
            by_category,
            videos,
            {},
            FALLBACK_HEADLINE,
            [f"요약 생성 실패, 제목만 표시합니다 ({reason})"],
        )
    raw = data.get("headline")
    headline = _truncate(" ".join(raw.split())) if isinstance(raw, str) and raw.strip() else FALLBACK_HEADLINE
    return _assemble(top_news, by_category, videos, data, headline, [])


def titles_only_digest(
    top_news: list[Article],
    by_category: dict[str, list[Article]],
    videos: list[Video],
) -> Digest:
    """AI 요약 없이 제목과 링크만 담은 Digest. 요약을 일부러 끈 경우이므로 오류 알림은 없다."""
    return _assemble(top_news, by_category, videos, {}, FALLBACK_HEADLINE, [])
