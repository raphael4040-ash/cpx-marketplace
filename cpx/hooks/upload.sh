#!/bin/sh
# CPX 자동 업로드 훅 (POSIX sh / macOS · Linux · Git Bash)
#
# Stop 훅은 모든 세션의 모든 턴에서 실행된다. 따라서 이 스크립트의 첫 번째 임무는
# "지금이 CPX 평가 턴이 아니면 아무것도 전송하지 않고 즉시 끝내는 것"이다.
# 게이트를 통과하기 전에는 네트워크를 절대 건드리지 않는다.
set -u

# 배포된 Cloudflare Worker 주소. CPX_ENDPOINT 환경변수로 덮어쓸 수 있다.
ENDPOINT="${CPX_ENDPOINT:-https://cpx-upload.raphael40402652.workers.dev/upload}"

CPX_HOME="${HOME:-$USERPROFILE}/.cpx"
TOKEN="${CPX_TOKEN:-}"
[ -n "$TOKEN" ] || TOKEN=$(cat "$CPX_HOME/token" 2>/dev/null | tr -d '\r\n')

# 연결 안 된 사용자 / curl 없는 환경에서는 조용히 끝낸다.
[ -n "$TOKEN" ] || exit 0
command -v curl >/dev/null 2>&1 || exit 0

datadir="${CLAUDE_PLUGIN_DATA:-${TMPDIR:-/tmp}}"
mkdir -p "$datadir" 2>/dev/null || datadir="${TMPDIR:-/tmp}"
hookfile="$datadir/cpx-hook-$$.json"
trfile="$datadir/cpx-tr-$$.jsonl"

cleanup() { rm -f "$hookfile" "$trfile"; }
trap cleanup EXIT

cat > "$hookfile"

# --- 게이트 1: 평가 턴에만 동작한다 ---
grep -q 'cpx-record' "$hookfile" || exit 0

# --- 게이트 2: 같은 턴 중복 업로드 방지 (sh/ps1 훅이 둘 다 도는 환경 대비) ---
key=$(cksum < "$hookfile" | cut -d' ' -f1)
lock="$datadir/cpx-last"
[ "$(cat "$lock" 2>/dev/null)" = "$key" ] && exit 0
printf '%s' "$key" > "$lock"

# --- 전사 첨부 여부 ---
send_transcript=1
if [ -f "$CPX_HOME/config" ] && grep -q '^transcript=0' "$CPX_HOME/config" 2>/dev/null; then
  send_transcript=0
fi

tp=""
if [ "$send_transcript" = "1" ]; then
  # JSON 안의 Windows 경로는 백슬래시가 이스케이프돼 두 개로 들어온다. 먼저 슬래시로 바꿔두면
  # Git Bash 가 읽을 수 있는 형태가 되고, 경로에 백슬래시가 남지 않아 단순 추출이 안전해진다.
  tp=$(sed 's|\\|/|g' "$hookfile" \
       | sed -n 's|.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*|\1|p' \
       | head -n1)
fi

if [ -n "$tp" ] && [ -f "$tp" ]; then
  # 전사가 길면 Firestore 문서 상한을 넘으므로 뒷부분만 보낸다.
  tail -n 3000 "$tp" > "$trfile" 2>/dev/null
  curl -sS -m 20 -X POST "$ENDPOINT" \
    -H "Authorization: Bearer $TOKEN" \
    -F "hook=@$hookfile;type=application/json" \
    -F "transcript=@$trfile;type=application/jsonl" 2>/dev/null
else
  curl -sS -m 20 -X POST "$ENDPOINT" \
    -H "Authorization: Bearer $TOKEN" \
    -F "hook=@$hookfile;type=application/json" 2>/dev/null
fi

exit 0
