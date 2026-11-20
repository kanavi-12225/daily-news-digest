import json
from dataclasses import dataclass

import requests

from newsbot.config import KAKAO_MEMO_SEND_URL, KAKAO_TEXT_MAX, KAKAO_TOKEN_URL

TIMEOUT = 15
EXPIRED_STATUS = 401
EXPIRED_CODE = -401


class KakaoError(Exception):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str | None


def _body(resp) -> dict:
    try:
        data = resp.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _describe(action: str, resp) -> str:
    body = _body(resp)
    parts = [f"{action} failed: HTTP {resp.status_code}"]
    # Only whitelisted response fields; never request headers/body.
    for key in ("code", "msg", "error", "error_code", "error_description"):
        if key in body:
            parts.append(f"{key}={body[key]}")
    return " ".join(parts)


def _truncate(text: str) -> str:
    if len(text) <= KAKAO_TEXT_MAX:
        return text
    return text[: KAKAO_TEXT_MAX - 1] + "…"


def _is_expired(resp) -> bool:
    return resp.status_code == EXPIRED_STATUS and _body(resp).get("code") == EXPIRED_CODE


def _send(access_token: str, text: str, link_url: str, post):
    template = {
        "object_type": "text",
        "text": _truncate(text),
        "link": {"web_url": link_url, "mobile_web_url": link_url},
    }
    return post(
        KAKAO_MEMO_SEND_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=TIMEOUT,
    )


def refresh_access_token(rest_api_key: str, refresh_token: str, post=requests.post) -> TokenPair:
    resp = post(
        KAKAO_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": rest_api_key,
            "refresh_token": refresh_token,
        },
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise KakaoError(_describe("token refresh", resp))
    body = _body(resp)
    access = body.get("access_token")
    if not isinstance(access, str) or not access:
        raise KakaoError("token refresh failed: response has no access_token")
    new_refresh = body.get("refresh_token")
    return TokenPair(access, new_refresh if isinstance(new_refresh, str) and new_refresh else None)


def send_memo(access_token: str, text: str, link_url: str, post=requests.post) -> None:
    resp = _send(access_token, text, link_url, post)
    if resp.status_code != 200:
        raise KakaoError(_describe("send memo", resp))


def send_with_refresh(
    rest_api_key: str,
    access_token: str,
    refresh_token: str,
    text: str,
    link_url: str,
    post=requests.post,
) -> TokenPair | None:
    resp = _send(access_token, text, link_url, post)
    if resp.status_code == 200:
        return None
    if not _is_expired(resp):
        raise KakaoError(_describe("send memo", resp))
    pair = refresh_access_token(rest_api_key, refresh_token, post=post)
    send_memo(pair.access_token, text, link_url, post=post)
    return pair
