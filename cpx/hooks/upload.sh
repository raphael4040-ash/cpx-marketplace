#!/bin/sh
# CPX 자동 업로드 훅 (POSIX sh / macOS · Linux · Git Bash)
#
# Stop 훅은 모든 세션의 모든 턴에서 실행된다. 따라서 이 스크립트의 첫 번째 임무는
# "지금이 CPX 평가 턴이 아니면 아무것도 전송하지 않고 즉시 끝내는 것"이다.
# 게이트를 통과하기 전에는 네트워크를 절대 건드리지 않는다.
set -u

CPX_HOME="${HOME:-$USERPROFILE}/.cpx"

# 배포된 Cloudflare Worker 주소.
# 예전에는 CPX_ENDPOINT 환경변수로 덮어쓸 수 있었다. 환경변수는 프로젝트 설정만
# 건드려도 심을 수 있어서, 그것만으로 토큰과 전사가 통째로 남의 서버로 갔다.
# 이제 주소는 사용자 홈의 ~/.cpx/config 에서만 읽는다 (자체 배포용 탈출구는 유지).
ENDPOINT="https://cpx-upload.raphael40402652.workers.dev/upload"
if [ -f "$CPX_HOME/config" ]; then
  alt=$(sed -n 's/^endpoint=[[:space:]]*//p' "$CPX_HOME/config" 2>/dev/null | head -n1 | tr -d '\r\n')
  # https 가 아니면 무시한다 — 평문으로 토큰을 흘리지 않기 위해서다.
  case "$alt" in https://*) ENDPOINT="$alt" ;; esac
fi
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
# 'cpx-record' 만 찾으면 그 말이 오간 무관한 세션의 전사까지 올라간다.
# 진짜 기록 블록은 펜스 바로 뒤에 {"topic": 같은 JSON 이 붙으므로,
# 여는 중괄호와 따옴표까지 통째로 요구한다 — 형식을 글로 설명하는 세션은 통과못한다.
# (훅 페이로드는 JSON 이라 줄바꿈이 \n 두 글자로 들어 있다)
if ! grep -qF '```cpx-record\n{\"' "$hookfile" \
   && ! grep -qF '```cpx-record\r\n{\"' "$hookfile"; then
  exit 0
fi

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

# 토큰을 -H 로 넘기면 ps 에 그대로 뜼다 — 같은 기계의 다른 로컬 사용자에게 보인다.
# -K - 로 설정을 stdin 에서 읽게 해 프로세스 인자에서 토큰을 뺀다.
send() {
  printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" | curl -K - "$@"
}

if [ -n "$tp" ] && [ -f "$tp" ]; then
  # 전사가 길면 Firestore 문서 상한을 넘으므로 뒷부분만 보낸다.
  tail -n 3000 "$tp" > "$trfile" 2>/dev/null
  send -sS -m 20 -X POST "$ENDPOINT" \
    -F "hook=@$hookfile;type=application/json" \
    -F "transcript=@$trfile;type=application/jsonl" 2>/dev/null
else
  send -sS -m 20 -X POST "$ENDPOINT" \
    -F "hook=@$hookfile;type=application/json" 2>/dev/null
fi

exit 0
