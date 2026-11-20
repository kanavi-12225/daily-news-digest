# 뉴스·유튜브 요약 에이전트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 08:00, 19:00(KST)에 뉴스 TOP10, 분야별 TOP3, 유튜브 TOP10을 요약해 GitHub Pages 페이지로 올리고, 카카오톡 "나에게 보내기"로 한 줄 요약과 링크를 보낸다.

**Architecture:** 파이썬 스크립트 하나가 수집 → 요약 → 페이지 생성 → 카톡 전송을 순서대로 실행한다. 실행은 GitHub Actions 예약 실행이 맡고, 결과 HTML은 저장소의 `docs/`에 커밋해 GitHub Pages로 공개한다. 각 단계는 작은 모듈로 나눠 따로 테스트한다.

**Tech Stack:** Python 3.12, requests, feedparser, anthropic SDK, Jinja2, pytest, GitHub Actions, GitHub Pages, 카카오 REST API, YouTube Data API v3.

**Spec:** `docs/superpowers/specs/2026-11-20-news-agent-design.md`

## Global Constraints

- 월 비용은 10만 원 이내, 요약용 AI는 Claude 하나만 쓴다 (Claude Pro 구독과 API 요금은 별개이므로 API 키를 따로 발급한다).
- 키와 토큰은 코드나 저장소에 넣지 않고 GitHub Secrets와 환경변수로만 다룬다.
- 데이터는 공식 API와 RSS만 쓰고 크롤링하지 않는다. 페이지에는 제목, 짧은 요약, 원문 링크만 싣고 기사 원문 전체는 싣지 않는다.
- 카카오 텍스트 메시지는 200자 이하 (구현 시 카카오 문서에서 현재 한도를 확인한다).
- 뉴스 분야 6개, 이름은 정확히: `정치·사회`, `경제·산업`, `국제`, `IT·과학·인공지능`, `문화연예·스포츠`, `재난·환경·지역`. 분야별 3건, 전체 뉴스 10건, 유튜브 10건.
- 실행 시각: 08:00, 19:00 KST. 2회분은 페이지에서 구분한다.
- 코드는 Claude가 작성하고 사용자(파이썬 초보)에게 이유를 설명한다. 범위를 늘리지 않는다.
- 구현은 사용자가 정한 새 프로젝트 폴더에서 한다 (현재 임시 폴더가 아님). 시작 전에 폴더를 정하고 `git init`을 한다.
- GitHub Pages 무료 사용은 공개 저장소를 전제로 한다.

## Review Focus

1. RSS나 유튜브 API 한쪽이 실패하거나 0건을 돌려줄 때: 나머지로 페이지는 만들고, 실패한 칸에 "오늘은 가져오지 못했어요"를 표시한다.
2. Claude 응답이 약속한 JSON이 아닐 때: 요약 없이 제목과 링크만으로 페이지를 만들고 실행은 성공으로 끝낸다.
3. 기사 제목에 `<`, `&`, 따옴표가 있을 때: 페이지에서 HTML로 해석되지 않고 글자 그대로 보인다.
4. 같은 기사가 전체 TOP10과 분야 TOP3에 겹칠 때: 분야 칸에서는 중복 없이 채운다.
5. 카카오 액세스 토큰이 만료됐을 때: 갱신 후 재전송하고, 갱신도 실패하면 실행을 실패로 끝내 GitHub 실패 메일이 오게 한다.

---

## File Structure

```
newsbot/                     # 프로젝트 루트 (새 폴더)
  src/newsbot/
    models.py                # Article, Video, Digest 데이터 클래스
    config.py                # 분야 목록, 검색 키워드, 환경변수 읽기
    collect_news.py          # RSS 수집
    collect_youtube.py       # 유튜브 인기 동영상 수집
    summarize.py             # Claude API 요약
    render_page.py           # HTML 생성
    kakao.py                 # 토큰 갱신 + 나에게 보내기
    main.py                  # run(slot, dry_run) 오케스트레이션
  scripts/kakao_auth.py      # 최초 1회 카카오 토큰 발급 도우미
  templates/page.html.j2
  tests/                     # 모듈별 테스트
  docs/                      # GitHub Pages 출력 (index.html + archive/)
  .github/workflows/digest.yml
  requirements.txt
  .gitignore                 # .env 제외
```

---

### Task 1: 프로젝트 뼈대와 데이터 모델

**Files:**
- Create: `requirements.txt`, `.gitignore`, `src/newsbot/__init__.py`, `src/newsbot/models.py`, `src/newsbot/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: 
  - `Article(title: str, url: str, source: str, published: str)` (frozen dataclass)
  - `Video(title: str, url: str, channel: str, views: int)`
  - `Digest(top_news: list[ArticleSummary], by_category: dict[str, list[ArticleSummary]], videos: list[VideoSummary], headline: str, errors: list[str])`, 여기서 `ArticleSummary(article: Article, summary: str | None)`, `VideoSummary(video: Video, summary: str | None)`
  - `config.CATEGORIES: dict[str, str]` (분야 이름 → 검색 키워드 문자열)
  - `config.get_env(name: str) -> str` (없으면 `RuntimeError`)

- [ ] **Step 1: 실패하는 테스트 작성** — `test_categories_are_the_six_agreed_names_in_order`는 `list(CATEGORIES)`가 Global Constraints의 6개 이름과 순서까지 같은지 확인한다. `test_get_env_raises_when_missing`은 없는 변수에서 `RuntimeError`를 확인한다.
- [ ] **Step 2: 실행해서 실패 확인** — Run: `pytest tests/test_config.py -v` / Expected: FAIL (모듈 없음)
- [ ] **Step 3: 구현** — 위 인터페이스대로 `models.py`, `config.py`를 만든다. 검색 키워드는 분야별로 한국어 키워드 2~3개를 OR로 묶는다 (예: `국제` → `국제 OR 외교 OR 해외`). 키워드 값은 구현자 판단.
- [ ] **Step 4: 통과 확인** — Run: `pytest tests/test_config.py -v` / Expected: PASS
- [ ] **Step 5: 커밋** — `git add . && git commit -m "chore: project skeleton and models"`

---

### Task 2: 뉴스 수집

**Files:**
- Create: `src/newsbot/collect_news.py`
- Test: `tests/test_collect_news.py`, `tests/fixtures/news_rss_sample.xml`

**Interfaces:**
- Consumes: `Article`, `config.CATEGORIES`
- Produces:
  - `fetch_top_news(limit: int = 10) -> list[Article]`
  - `fetch_category_news(category: str, limit: int = 3, exclude_urls: set[str] = frozenset()) -> list[Article]`
  - 네트워크 실패 시 예외를 던지지 않고 빈 리스트를 반환한다 (`main`이 빈 리스트를 오류로 처리).

- [ ] **Step 1: 실패하는 테스트** — 저장해 둔 샘플 RSS XML을 `feedparser.parse`에 넘기도록 `fetch_*`가 받는 파서 함수를 주입 가능하게 하고, 다음을 검증한다: `test_top_news_returns_first_10_in_feed_order`, `test_category_news_skips_excluded_urls_and_still_returns_3`, `test_fetch_returns_empty_list_when_feed_raises`.
- [ ] **Step 2: 실행해서 실패 확인** — Run: `pytest tests/test_collect_news.py -v` / Expected: FAIL
- [ ] **Step 3: 구현** — Google News RSS(한국어/KR 설정)의 헤드라인 피드와 검색 피드를 쓴다. 순위는 피드 순서. 정확한 URL 형식은 구현 시 Google News RSS 현재 형식을 확인하고 `config.py`에 상수로 둔다.
- [ ] **Step 4: 통과 확인** — Run: `pytest tests/test_collect_news.py -v` / Expected: PASS
- [ ] **Step 5: 실제 호출로 눈 확인** — Run: `python -c "from newsbot.collect_news import fetch_top_news; print(fetch_top_news(3))"` / Expected: 오늘 기사 3건이 출력된다.
- [ ] **Step 6: 커밋** — `git commit -am "feat: news collection via RSS"`

---

### Task 3: 유튜브 인기 동영상 수집

**Files:**
- Create: `src/newsbot/collect_youtube.py`
- Test: `tests/test_collect_youtube.py`

**Interfaces:**
- Consumes: `Video`, `config.get_env`
- Produces: `fetch_trending(limit: int = 10, http_get=requests.get) -> list[Video]` (실패 시 빈 리스트)

- [ ] **Step 1: 실패하는 테스트** — `http_get`을 가짜로 주입해 `test_parses_title_channel_views_and_builds_watch_url`(URL은 `https://www.youtube.com/watch?v=<id>`), `test_returns_empty_when_api_returns_error_status`를 검증한다.
- [ ] **Step 2: 실행해서 실패 확인** — Run: `pytest tests/test_collect_youtube.py -v` / Expected: FAIL
- [ ] **Step 3: 구현** — YouTube Data API `videos.list`의 `chart=mostPopular`, `regionCode=KR`. 필요 파라미터는 구현 시 공식 문서에서 확인한다. 키는 `YOUTUBE_API_KEY`.
- [ ] **Step 4: 통과 확인** — Run: `pytest tests/test_collect_youtube.py -v` / Expected: PASS
- [ ] **Step 5: 커밋** — `git commit -am "feat: youtube trending collection"`

---

### Task 4: Claude 요약

**Files:**
- Create: `src/newsbot/summarize.py`
- Test: `tests/test_summarize.py`

**Interfaces:**
- Consumes: `Article`, `Video`, `Digest`와 관련 모델
- Produces: `summarize_digest(top_news: list[Article], by_category: dict[str, list[Article]], videos: list[Video], client) -> Digest`
  - `client`는 `anthropic.Anthropic`과 같은 `messages.create(...)` 인터페이스를 가진 객체 (테스트에서 가짜 주입).
  - 요약은 한 번의 호출로 JSON을 받아 처리한다. 모델은 `claude-haiku-5-5`를 기본으로 하되 `config`에서 바꿀 수 있게 한다.
  - `Digest.headline`은 카톡에 쓸 한 줄 요약이며 120자 이하.

- [ ] **Step 1: 실패하는 테스트** — 가짜 client가 정상 JSON을 돌려줄 때 `test_fills_summaries_and_headline`, 깨진 JSON을 돌려줄 때 `test_falls_back_to_titles_only_when_json_invalid` (summary는 `None`, headline은 "오늘의 뉴스가 도착했어요" 형태의 기본 문구, 예외 없음), 응답 headline이 120자를 넘을 때 `test_headline_is_truncated_to_120_chars`를 검증한다.
- [ ] **Step 2: 실행해서 실패 확인** — Run: `pytest tests/test_summarize.py -v` / Expected: FAIL
- [ ] **Step 3: 구현** — 프롬프트는 기사 제목만 보내고(원문 본문 없음) "항목별 1~2문장 한국어 요약 + 전체 한 줄 요약"을 JSON으로 요청한다. 요약은 사실만, 제목에 없는 내용을 지어내지 말라고 명시한다.
- [ ] **Step 4: 통과 확인** — Run: `pytest tests/test_summarize.py -v` / Expected: PASS
- [ ] **Step 5: 실제 호출 1회 확인** — `ANTHROPIC_API_KEY`를 설정하고 Task 2, 3의 실제 수집 결과로 한 번 호출한다. Expected: 요약이 채워진 Digest, 비용이 몇 원 수준인지 콘솔의 사용량에서 확인.
- [ ] **Step 6: 커밋** — `git commit -am "feat: claude summarization with fallback"`

---

### Task 5: HTML 페이지 생성

**Files:**
- Create: `src/newsbot/render_page.py`, `templates/page.html.j2`
- Test: `tests/test_render_page.py`

**Interfaces:**
- Consumes: `Digest`
- Produces:
  - `render_page(digest: Digest, slot: str, now: datetime) -> str` (`slot`은 `"morning"` 또는 `"evening"`)
  - `write_pages(html: str, slot: str, now: datetime, docs_dir: Path) -> Path` — `docs/archive/YYYY-MM-DD-<slot>.html`에 저장하고 `docs/index.html`도 같은 내용으로 갱신, 아카이브 경로를 반환한다.

- [ ] **Step 1: 실패하는 테스트** — `test_titles_are_html_escaped`(제목 `<script>x</script> & "a"`가 이스케이프되어 나온다), `test_errors_are_shown_as_notice`, `test_page_shows_slot_label_and_date`(아침/저녁 라벨), `test_write_pages_updates_index_and_archive`.
- [ ] **Step 2: 실행해서 실패 확인** — Run: `pytest tests/test_render_page.py -v` / Expected: FAIL
- [ ] **Step 3: 구현** — Jinja2 autoescape를 켠다. 모바일 화면에서 읽기 좋은 단일 열 레이아웃, 섹션 순서는 전체 TOP10 → 분야별 TOP3 → 유튜브 TOP10. 디자인 세부는 구현자 판단.
- [ ] **Step 4: 통과 확인** — Run: `pytest tests/test_render_page.py -v` / Expected: PASS
- [ ] **Step 5: 눈으로 확인** — 샘플 Digest로 만든 `docs/index.html`을 브라우저로 열어 휴대폰 너비에서 본다.
- [ ] **Step 6: 커밋** — `git commit -am "feat: html page rendering"`

---

### Task 6: 카카오 나에게 보내기

**Files:**
- Create: `src/newsbot/kakao.py`
- Test: `tests/test_kakao.py`

**Interfaces:**
- Produces:
  - `refresh_access_token(rest_api_key: str, refresh_token: str, post=requests.post) -> TokenPair` — `TokenPair(access_token: str, refresh_token: str | None)`. 카카오가 새 refresh token을 주지 않으면 `None`.
  - `send_memo(access_token: str, text: str, link_url: str, post=requests.post) -> None` — `text`는 200자로 잘라서 보내고, 실패 응답이면 `KakaoError`를 던진다.
  - `send_with_refresh(rest_api_key, access_token, refresh_token, text, link_url) -> TokenPair | None` — 만료 응답이면 갱신 후 재전송하고, 새 토큰이 생겼으면 반환한다.

- [ ] **Step 1: 실패하는 테스트** — `test_text_longer_than_200_is_truncated`, `test_send_failure_raises_kakao_error`, `test_expired_token_triggers_refresh_and_retry`, `test_refresh_failure_raises`.
- [ ] **Step 2: 실행해서 실패 확인** — Run: `pytest tests/test_kakao.py -v` / Expected: FAIL
- [ ] **Step 3: 구현** — 카카오 "나에게 보내기"(메모) 기본 템플릿(텍스트 + 링크) API와 토큰 갱신 API를 쓴다. 엔드포인트와 필드명은 구현 시 카카오 개발자 문서에서 현재 사양을 확인한다.
- [ ] **Step 4: 통과 확인** — Run: `pytest tests/test_kakao.py -v` / Expected: PASS
- [ ] **Step 5: 커밋** — `git commit -am "feat: kakao send-to-me with token refresh"`

---

### Task 7: 카카오 최초 인증 도우미 (사용자와 함께 진행)

**Files:**
- Create: `scripts/kakao_auth.py`
- 사전 준비 (사용자가 직접): 카카오 개발자 사이트에서 앱 등록, "카카오톡 메시지" 동의 항목 설정, REST API 키 확인, 리다이렉트 URI 등록

**Interfaces:**
- Produces: 터미널에서 실행하면 인증 URL을 안내하고, 사용자가 붙여 넣은 인가 코드로 `access_token`과 `refresh_token`을 받아 화면에 출력한다 (파일에 저장하지 않는다).

- [ ] **Step 1: 사용자와 함께 앱 등록** — Claude가 화면 단계별로 안내한다. 사용자가 키를 채팅에 붙여 넣지 않도록 하고, 로컬 `.env`에 직접 입력하게 한다.
- [ ] **Step 2: 스크립트 구현** — 위 흐름만 구현한다. 테스트는 생략하고 실제 1회 실행으로 확인한다.
- [ ] **Step 3: 실제 전송 확인** — 받은 토큰으로 `send_memo`를 한 번 호출한다. Expected: 사용자의 "나에게 보내기" 채팅방에 테스트 메시지가 도착한다.
- [ ] **Step 4: 커밋** — `git add scripts/kakao_auth.py && git commit -m "feat: kakao initial auth helper"` (`.env`는 `.gitignore`로 제외되어 있는지 `git status`로 확인)

---

### Task 8: 오케스트레이션

**Files:**
- Create: `src/newsbot/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: Task 2~6의 모든 함수
- Produces:
  - `run(slot: str, dry_run: bool = False, now: datetime | None = None) -> int` — 종료 코드 반환 (0 성공)
  - `python -m newsbot.main --slot morning|evening [--dry-run]`
  - 동작: 수집 → (분야별은 전체 TOP10 URL을 `exclude_urls`로 전달) → 요약 → 페이지 저장 → 카톡 전송. `dry_run`이면 전송과 저장 없이 결과를 출력만 한다. 수집이 빈 리스트인 항목은 `Digest.errors`에 사람이 읽을 문구로 기록하고 계속 진행한다. 세 수집원 모두 비었거나 카카오 전송이 최종 실패하면 0이 아닌 코드를 반환한다.
  - 카톡 문구: `"{headline}\n{page_url}"` 형태, `page_url`은 `PAGES_BASE_URL` 환경변수 + `/archive/...`.
  - 카카오 토큰이 갱신되어 새 refresh token이 생겼으면 `NEW_KAKAO_REFRESH_TOKEN` 값을 파일 `.new_refresh_token`(커밋 제외)에 기록한다. Task 9가 이 파일로 비밀 저장소를 갱신한다.

- [ ] **Step 1: 실패하는 테스트** — 수집/요약/전송을 가짜로 주입해 `test_partial_failure_still_renders_and_sends`(유튜브만 빈 리스트), `test_all_sources_empty_returns_nonzero`, `test_dry_run_does_not_send_or_write`, `test_categories_exclude_top_news_urls`.
- [ ] **Step 2: 실행해서 실패 확인** — Run: `pytest tests/test_main.py -v` / Expected: FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — Run: `pytest -v` / Expected: 전체 PASS
- [ ] **Step 5: 내 PC에서 드라이런 → 실제 1회 실행** — `python -m newsbot.main --slot morning --dry-run`으로 출력을 확인한 뒤, 옵션 없이 실행한다. Expected: 카톡에 링크가 오고, `docs/index.html`이 생긴다.
- [ ] **Step 6: 커밋** — `git commit -am "feat: end-to-end run"`

---

### Task 9: GitHub 자동 실행 (사용자와 함께 진행)

**Files:**
- Create: `.github/workflows/digest.yml`
- 사전 준비 (사용자가 직접): 공개 GitHub 저장소 생성과 푸시, Secrets 등록 (`ANTHROPIC_API_KEY`, `YOUTUBE_API_KEY`, `KAKAO_REST_API_KEY`, `KAKAO_ACCESS_TOKEN`, `KAKAO_REFRESH_TOKEN`, 비밀 갱신용 `GH_PAT`), Pages 설정에서 `docs/` 폴더 공개, `PAGES_BASE_URL` 변수 등록

**Interfaces:**
- Produces: 08:00 KST(= 23:00 UTC 전날), 19:00 KST(= 10:00 UTC)에 실행되는 워크플로. 수동 실행(`workflow_dispatch`)도 지원한다. 실행 후 `docs/` 변경분을 커밋·푸시하고, `.new_refresh_token`이 있으면 `gh secret set`으로 `KAKAO_REFRESH_TOKEN`을 갱신한다. 실행이 실패하면 GitHub 기본 실패 메일로 알린다.

- [ ] **Step 1: 워크플로 작성** — 위 인터페이스대로. `slot`은 실행 시각(UTC 시)으로 판단하거나 cron별로 지정한다 (구현자 판단).
- [ ] **Step 2: 사용자와 함께 저장소, Secrets, Pages 설정**
- [ ] **Step 3: 수동 실행으로 확인** — GitHub Actions 화면에서 `workflow_dispatch`로 한 번 실행한다. Expected: 초록 체크, 카톡 도착, Pages 주소에서 페이지가 열린다.
- [ ] **Step 4: 예약 실행 확인** — 다음 08:00 또는 19:00 이후에 실행 기록과 카톡을 확인한다. (GitHub 예약 실행은 몇 분에서 수십 분 늦을 수 있다. 정각이 아니어도 실패가 아니다.)
- [ ] **Step 5: 커밋** — `git commit -am "ci: scheduled digest workflow"`

---

### Task 10: 이틀 운영과 다듬기

- [ ] **Step 1: 이틀간(4회분) 도착 여부 확인** — 빠진 회차, 실패 메일, 이상한 요약을 기록한다.
- [ ] **Step 2: Claude API 사용량 확인** — 콘솔에서 4회분 비용을 보고 월 환산 금액을 설계서의 비용 목표와 비교해 사용자에게 알린다.
- [ ] **Step 3: 다듬기** — 기록한 문제 중 가장 거슬리는 것 최대 3개만 고친다. 새 기능은 추가하지 않는다.
- [ ] **Step 4: 커밋 후 완료 선언** — 다음 에이전트 후보(맛집 블로그, 아버지 장부 조사)는 별도 설계로 이어간다.

---

## Self-Review 결과

- **스펙 커버리지:** 일정(2회), 뉴스 TOP10/분야 TOP3(6분야)/유튜브 TOP10(Task 2~3), 요약(4), 링크 방식 페이지(5), 카톡(6~7), PC 없이 실행(9), 비용 확인(4, 10), 비밀 관리(Global Constraints, 9), 원문 비복제(Global Constraints, 4) 모두 대응 task가 있다.
- **타입 일관성:** `Article/Video/Digest/TokenPair`와 함수 이름이 Task 간에 일치한다.
- **알려진 위험:** 카카오 refresh token 갱신 저장(Task 8~9)이 가장 까다롭다. 갱신 토큰 유효기간이 지나면 수동 재발급(Task 7)이 필요할 수 있다. 외부 API 사양(Google News RSS, YouTube, 카카오)은 구현 시점의 공식 문서로 확인한다.
