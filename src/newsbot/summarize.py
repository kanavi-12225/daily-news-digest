import json
import re

from newsbot.config import SUMMARY_MAX_TOKENS, SUMMARY_MODEL
from newsbot.models import Article, ArticleSummary, Digest, Video, VideoSummary

FALLBACK_HEADLINE = "오늘의 뉴스가 도착했어요"
HEADLINE_MAX = 120

SYSTEM_PROMPT = (
    "당신은 한국어 뉴스 요약 도우미입니다. 제공되는 것은 기사/영상의 제목뿐입니다. "
    "각 항목을 1~2문장의 한국어로 요약하되, 제목이 뒷받침하는 사실만 쓰고 "
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
        '\n다음 형식의 JSON만 출력하세요. 각 배열은 위 항목 순서와 개수를 그대로 따릅니다:\n'
        '{"headline": "...", "top_news": ["요약", ...], '
        '"by_category": {"카테고리명": ["요약", ...]}, "videos": ["요약", ...]}'
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


def _pick(values, i) -> str | None:
    if isinstance(values, list) and i < len(values):
        v = values[i]
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _truncate(headline: str) -> str:
    if len(headline) <= HEADLINE_MAX:
        return headline
    return headline[: HEADLINE_MAX - 1] + "…"


def _assemble(top_news, by_category, videos, data, headline, errors) -> Digest:
    cat_data = data.get("by_category")
    if not isinstance(cat_data, dict):
        cat_data = {}
    return Digest(
        top_news=[
            ArticleSummary(a, _pick(data.get("top_news"), i))
            for i, a in enumerate(top_news)
        ],
        by_category={
            cat: [ArticleSummary(a, _pick(cat_data.get(cat), i)) for i, a in enumerate(arts)]
            for cat, arts in by_category.items()
        },
        videos=[
            VideoSummary(v, _pick(data.get("videos"), i)) for i, v in enumerate(videos)
        ],
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
        data = _parse_json(response.content[0].text)
    except Exception as exc:  # API failure or unparseable response; never include secrets
        reason = f"{type(exc).__name__}"
        return _assemble(
            top_news,
            by_category,
            videos,
            {},
            FALLBACK_HEADLINE,
            [f"요약 생성 실패, 제목만 표시합니다 ({reason})"],
        )
    raw = data.get("headline")
    headline = _truncate(raw.strip()) if isinstance(raw, str) and raw.strip() else FALLBACK_HEADLINE
    return _assemble(top_news, by_category, videos, data, headline, [])
