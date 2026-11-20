import feedparser

from newsbot.config import CATEGORIES, GOOGLE_NEWS_TOP_URL, google_news_search_url
from newsbot.models import Article


def _to_articles(url: str, parse) -> list[Article]:
    try:
        feed = parse(url)
        articles = []
        for entry in feed.entries:
            link = entry.get("link", "")
            title = entry.get("title", "")
            if not link or not title:
                continue
            source = entry.get("source") or {}
            articles.append(
                Article(
                    title=title,
                    url=link,
                    source=source.get("title", ""),
                    published=entry.get("published", ""),
                )
            )
        return articles
    except Exception:
        return []


def fetch_top_news(limit: int = 10, parse=feedparser.parse) -> list[Article]:
    return _to_articles(GOOGLE_NEWS_TOP_URL, parse)[:limit]


def fetch_category_news(
    category: str,
    limit: int = 3,
    exclude_urls: set[str] = frozenset(),
    parse=feedparser.parse,
) -> list[Article]:
    keywords = CATEGORIES.get(category)
    if keywords is None:
        return []
    articles = _to_articles(google_news_search_url(keywords), parse)
    return [a for a in articles if a.url not in exclude_urls][:limit]
