#!/usr/bin/env bash
# 이번 실행이 어느 회차(아침/저녁)인지, 건너뛸지를 정해서 `key=value` 줄로 출력한다.
# 입력(환경변수): EVENT_NAME, INPUT_SLOT, FORCE, SCHEDULE, (테스트용) KST_HOUR, KST_DATE, SENT_DIR
set -eu

HOUR="${KST_HOUR:-$(TZ=Asia/Seoul date +%H)}"
DATE="${KST_DATE:-$(TZ=Asia/Seoul date +%F)}"
SENT_DIR="${SENT_DIR:-.sent}"
HOUR=$((10#$HOUR))
SKIP=false
REASON=""

if [ "${EVENT_NAME:-}" = "schedule" ]; then
  # 어느 cron이 깨웠는지로 회차를 정한다 (늦게 시작돼도 원래 회차 그대로)
  case "${SCHEDULE:-}" in
    "7 23 * * *"|"37 23 * * *"|"7 0 * * *"|"37 0 * * *") SLOT=morning ;;
    "7 10 * * *"|"37 10 * * *"|"7 11 * * *"|"37 11 * * *") SLOT=evening ;;
    *) SLOT=""; SKIP=true; REASON="unknown schedule" ;;
  esac
  # 자기 시간대를 한참 지난 예비 실행은 버린다 (엉뚱한 때 메시지가 가지 않게)
  if [ "$SKIP" = false ]; then
    if [ "$SLOT" = morning ] && { [ "$HOUR" -lt 6 ] || [ "$HOUR" -gt 13 ]; }; then
      SKIP=true; REASON="morning backup outside 06-13 KST"
    elif [ "$SLOT" = evening ] && [ "$HOUR" -lt 17 ]; then
      SKIP=true; REASON="evening backup outside 17-23 KST"
    fi
  fi
else
  SLOT="${INPUT_SLOT:-}"
  case "$SLOT" in morning|evening) ;; *) SLOT=""; SKIP=true; REASON="invalid slot" ;; esac
fi

# 이미 보낸 회차는 어떤 트리거든 건너뛴다 (일부러 다시 보내려면 force)
if [ "$SKIP" = false ] && [ "${FORCE:-false}" != "true" ] && [ -f "$SENT_DIR/$DATE-$SLOT" ]; then
  SKIP=true; REASON="already sent"
fi

[ -n "$REASON" ] && echo "skip reason: $REASON" >&2
echo "value=$SLOT"
echo "date=$DATE"
echo "skip=$SKIP"
