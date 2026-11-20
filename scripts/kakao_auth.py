"""카카오 토큰을 처음 한 번 발급받는 도우미 (사용자가 자기 PC 터미널에서 직접 실행).

실행:  .venv\\Scripts\\python scripts\\kakao_auth.py

흐름
1. 이 스크립트가 로그인/동의 주소를 보여 준다. 브라우저로 열어 카카오 로그인 후 동의한다.
2. 동의가 끝나면 주소창이 `<리다이렉트 주소>?code=...` 로 바뀐다 (페이지가 안 열려도 정상).
   주소창의 code= 뒤의 값을 복사해 이 스크립트에 붙여 넣는다.
3. 스크립트가 토큰을 받아 화면에 보여 주고, "나에게 보내기"로 테스트 메시지를 한 번 보낸다.

토큰은 화면에만 출력하고 파일에 저장하지 않는다. 화면의 값은 채팅에 붙여 넣지 말고
.env 파일(깃에 올라가지 않음)과 GitHub Secrets에만 직접 입력한다.
"""
import getpass
import os
import sys
from urllib.parse import urlencode

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from newsbot.config import KAKAO_TOKEN_URL  # noqa: E402
from newsbot.kakao import KakaoError, send_memo  # noqa: E402

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
DEFAULT_REDIRECT_URI = "http://localhost:3000/oauth"
TEST_LINK = "https://developers.kakao.com"


def _ask(prompt: str, env_name: str, secret: bool = False, required: bool = True) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    reader = getpass.getpass if secret else input
    value = reader(prompt).strip()
    if required and not value:
        sys.exit(f"{env_name} 값이 필요합니다.")
    return value


def main() -> int:
    rest_key = _ask("카카오 REST API 키: ", "KAKAO_REST_API_KEY", secret=True)
    client_secret = _ask(
        "Client Secret (사용 설정을 안 했다면 그냥 Enter): ",
        "KAKAO_CLIENT_SECRET",
        secret=True,
        required=False,
    )
    redirect_uri = os.environ.get("KAKAO_REDIRECT_URI", "").strip() or DEFAULT_REDIRECT_URI

    query = urlencode(
        {
            "client_id": rest_key,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "talk_message",
        }
    )
    print("\n1) 아래 주소를 브라우저에 붙여 넣고 카카오 로그인 후 동의하세요.")
    print(f"   {AUTHORIZE_URL}?{query}")
    print(f"\n2) 이동한 주소창의 `code=` 뒤에 있는 값만 복사하세요. (리다이렉트 주소: {redirect_uri})")
    code = input("   인가 코드: ").strip()
    if not code:
        sys.exit("인가 코드가 비어 있습니다.")

    form = {
        "grant_type": "authorization_code",
        "client_id": rest_key,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        form["client_secret"] = client_secret

    resp = requests.post(KAKAO_TOKEN_URL, data=form, timeout=15)
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code != 200 or not data.get("access_token"):
        reason = data.get("error_description") or data.get("error") or "알 수 없는 오류"
        sys.exit(f"토큰 발급 실패 (HTTP {resp.status_code}): {reason}")

    access, refresh = data["access_token"], data.get("refresh_token", "")
    print("\n3) 발급 완료. 아래 값을 .env 와 GitHub Secrets에 직접 입력하세요 (채팅에 붙여 넣지 마세요).")
    print(f"   KAKAO_ACCESS_TOKEN={access}")
    print(f"   KAKAO_REFRESH_TOKEN={refresh}")

    try:
        send_memo(access, "카카오 연동 테스트: 이 메시지가 보이면 성공이에요.", TEST_LINK)
    except KakaoError as exc:
        print(f"\n테스트 메시지 전송 실패: {exc}")
        return 1
    print("\n테스트 메시지를 보냈습니다. '나와의 채팅'을 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
