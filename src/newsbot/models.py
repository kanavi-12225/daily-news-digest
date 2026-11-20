from dataclasses import dataclass, field


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published: str


@dataclass
class Video:
    title: str
    url: str
    channel: str
    views: int


@dataclass
class ArticleSummary:
    article: Article
    summary: str | None


@dataclass
class VideoSummary:
    video: Video
    summary: str | None


@dataclass
class Digest:
    top_news: list[ArticleSummary]
    by_category: dict[str, list[ArticleSummary]]
    videos: list[VideoSummary]
    headline: str
    errors: list[str] = field(default_factory=list)
