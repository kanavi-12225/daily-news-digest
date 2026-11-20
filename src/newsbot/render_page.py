from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from newsbot.config import CATEGORIES

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"
SLOT_LABELS = {"morning": "아침", "evening": "저녁"}

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"], default=True),
)


def _safe_url(url: str) -> str | None:
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return None
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return url.strip()
    return None


_env.filters["safe_url"] = _safe_url


def _label(slot: str) -> str:
    try:
        return SLOT_LABELS[slot]
    except KeyError:
        raise ValueError(f"Unknown slot: {slot!r}") from None


def render_page(digest, slot: str, now: datetime) -> str:
    label = _label(slot)
    return _env.get_template("page.html.j2").render(
        digest=digest,
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        label=label,
        categories=list(CATEGORIES),
    )


def write_pages(html: str, slot: str, now: datetime, docs_dir: Path) -> Path:
    _label(slot)
    docs_dir = Path(docs_dir)
    archive_dir = docs_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"{now.strftime('%Y-%m-%d')}-{slot}.html"
    archive.write_text(html, encoding="utf-8")
    (docs_dir / "index.html").write_text(html, encoding="utf-8")
    return archive
