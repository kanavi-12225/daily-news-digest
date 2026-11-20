import json

import pytest

from newsbot.kakao import KakaoError, TokenPair, refresh_access_token, send_memo, send_with_refresh


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def make_post(*responses):
    calls = []
    queue = list(responses)

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return queue.pop(0)

    post.calls = calls
    return post


def template(call):
    return json.loads(call[1]["data"]["template_object"])


def test_send_memo_payload():
    post = make_post(FakeResp(200, {"result_code": 0}))
    send_memo("AT", "hello", "https://x.io/p", post=post)
    url, kw = post.calls[0]
    assert url == "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    assert kw["headers"]["Authorization"] == "Bearer AT"
    t = template(post.calls[0])
    assert t["object_type"] == "text" and t["text"] == "hello"
    assert t["link"] == {"web_url": "https://x.io/p", "mobile_web_url": "https://x.io/p"}


def test_text_longer_than_200_is_truncated():
    post = make_post(FakeResp(200, {"result_code": 0}))
    send_memo("AT", "가" * 500, "https://x.io", post=post)
    text = template(post.calls[0])["text"]
    assert len(text) == 200 and text.endswith("…")


def test_text_of_exactly_200_untouched():
    post = make_post(FakeResp(200, {"result_code": 0}))
    send_memo("AT", "a" * 200, "https://x.io", post=post)
    assert template(post.calls[0])["text"] == "a" * 200


def test_send_failure_raises_kakao_error():
    post = make_post(FakeResp(400, {"msg": "bad", "code": -2}))
    with pytest.raises(KakaoError) as e:
        send_memo("SECRET_AT", "hi", "https://x.io", post=post)
    assert "400" in str(e.value) and "-2" in str(e.value)
    assert "SECRET_AT" not in str(e.value)


def test_non_json_failure_body():
    post = make_post(FakeResp(500, ValueError("no json")))
    with pytest.raises(KakaoError):
        send_memo("AT", "hi", "https://x.io", post=post)


def test_refresh_returns_pair_and_none_when_not_rotated():
    post = make_post(FakeResp(200, {"access_token": "A2"}))
    pair = refresh_access_token("KEY", "RT", post=post)
    assert pair == TokenPair("A2", None)
    d = post.calls[0][1]["data"]
    assert d == {"grant_type": "refresh_token", "client_id": "KEY", "refresh_token": "RT"}
    post = make_post(FakeResp(200, {"access_token": "A2", "refresh_token": "R2"}))
    assert refresh_access_token("KEY", "RT", post=post) == TokenPair("A2", "R2")


def test_refresh_failure_raises():
    post = make_post(FakeResp(400, {"error": "invalid_grant", "error_description": "expired", "error_code": "KOE322"}))
    with pytest.raises(KakaoError) as e:
        refresh_access_token("KEY_SECRET", "RT_SECRET", post=post)
    s = str(e.value)
    assert "400" in s and "KOE322" in s
    assert "KEY_SECRET" not in s and "RT_SECRET" not in s


def test_refresh_response_without_access_token_raises():
    with pytest.raises(KakaoError):
        refresh_access_token("K", "R", post=make_post(FakeResp(200, {})))


def test_expired_token_triggers_refresh_and_retry():
    post = make_post(
        FakeResp(401, {"msg": "expired", "code": -401}),
        FakeResp(200, {"access_token": "A2", "refresh_token": "R2"}),
        FakeResp(200, {"result_code": 0}),
    )
    pair = send_with_refresh("KEY", "A1", "R1", "hi", "https://x.io", post=post)
    assert pair == TokenPair("A2", "R2")
    assert post.calls[2][1]["headers"]["Authorization"] == "Bearer A2"


def test_send_success_returns_none_without_refresh():
    post = make_post(FakeResp(200, {"result_code": 0}))
    assert send_with_refresh("K", "A", "R", "hi", "https://x.io", post=post) is None
    assert len(post.calls) == 1


def test_non_expiry_failure_does_not_refresh():
    post = make_post(FakeResp(403, {"msg": "forbidden", "code": -3}))
    with pytest.raises(KakaoError):
        send_with_refresh("K", "A", "R", "hi", "https://x.io", post=post)
    assert len(post.calls) == 1


def test_refresh_failure_in_flow_raises():
    post = make_post(FakeResp(401, {"code": -401}), FakeResp(400, {"error": "invalid_grant"}))
    with pytest.raises(KakaoError):
        send_with_refresh("K", "A", "R", "hi", "https://x.io", post=post)


def test_retry_failure_raises():
    post = make_post(
        FakeResp(401, {"code": -401}),
        FakeResp(200, {"access_token": "A2"}),
        FakeResp(401, {"code": -401}),
    )
    with pytest.raises(KakaoError):
        send_with_refresh("K", "A", "R", "hi", "https://x.io", post=post)
    assert len(post.calls) == 3


def test_client_secret_included_only_when_given():
    post = make_post(FakeResp(200, {"access_token": "A"}))
    refresh_access_token("K", "R", post=post, client_secret="CS")
    assert post.calls[0][1]["data"]["client_secret"] == "CS"
    for empty in (None, ""):
        post = make_post(FakeResp(200, {"access_token": "A"}))
        refresh_access_token("K", "R", post=post, client_secret=empty)
        assert "client_secret" not in post.calls[0][1]["data"]


def test_client_secret_not_leaked_on_refresh_failure():
    post = make_post(FakeResp(401, {"code": -401}), FakeResp(400, {"error": "invalid_client", "error_code": "KOE010"}))
    with pytest.raises(KakaoError) as e:
        send_with_refresh("K", "A", "R", "hi", "https://x.io", post=post, client_secret="TOP_SECRET")
    assert "KOE010" in str(e.value) and "TOP_SECRET" not in str(e.value)
    assert post.calls[1][1]["data"]["client_secret"] == "TOP_SECRET"
