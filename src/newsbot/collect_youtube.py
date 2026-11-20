import requests

from newsbot.config import YOUTUBE_VIDEOS_URL, get_env
from newsbot.models import Video

WATCH_URL = "https://www.youtube.com/watch?v={id}"
MAX_RESULTS_CAP = 50  # videos.list allows maxResults 1..50


def fetch_trending(limit: int = 10, http_get=requests.get) -> list[Video]:
    # Missing key is a configuration error: let it propagate.
    api_key = get_env("YOUTUBE_API_KEY")
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": "KR",
        "maxResults": max(1, min(limit, MAX_RESULTS_CAP)),
        "key": api_key,
    }
    try:
        response = http_get(YOUTUBE_VIDEOS_URL, params=params, timeout=10)
        response.raise_for_status()
        videos = []
        for item in response.json()["items"]:
            video_id = item.get("id")
            snippet = item.get("snippet") or {}
            title = snippet.get("title")
            if not video_id or not title:
                continue
            views = (item.get("statistics") or {}).get("viewCount")
            videos.append(
                Video(
                    title=title,
                    url=WATCH_URL.format(id=video_id),
                    channel=snippet.get("channelTitle", ""),
                    views=int(views) if views else 0,
                )
            )
        return videos[:limit]
    except Exception:
        # Deliberately drop the exception: its message may embed the request URL (and key).
        return []
