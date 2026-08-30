# CPX 자동 업로드 훅 (Windows PowerShell)
#
# upload.sh 와 동일한 역할. Git Bash 가 없는 Windows 에서만 실제로 동작한다.
# Stop 훅은 모든 세션의 모든 턴에서 실행되므로, 게이트를 통과하기 전에는
# 네트워크를 절대 건드리지 않는다.

$ErrorActionPreference = 'SilentlyContinue'

# sh 가 있으면 upload.sh 가 이미 처리한다. 중복 업로드를 막기 위해 여기서 빠진다.
if (Get-Command sh -ErrorAction SilentlyContinue) { exit 0 }

$cpxHome = Join-Path $env:USERPROFILE '.cpx'

# 배포된 Cloudflare Worker 주소.
# 예전에는 CPX_ENDPOINT 환경변수로 덮어쓸 수 있었다. 환경변수는 프로젝트 설정만
# 건드려도 심을 수 있어서, 그것만으로 토큰과 전사가 통째로 남의 서버로 갔다.
# 이제 주소는 사용자 홈의 ~/.cpx/config 에서만 읽는다 (자체 배포용 탈출구는 유지).
$endpoint = 'https://cpx-upload.raphael40402652.workers.dev/upload'
$cpxConfig = Join-Path $cpxHome 'config'
if (Test-Path $cpxConfig) {
  $line = @(Get-Content $cpxConfig) | Where-Object { $_ -match '^endpoint=' } | Select-Object -First 1
  if ($line) {
    $alt = ($line -replace '^endpoint=\s*', '').Trim()
    # https 가 아니면 무시한다 — 평문으로 토큰을 흘리지 않기 위해서다.
    if ($alt -like 'https://*') { $endpoint = $alt }
  }
}
$token = $env:CPX_TOKEN
if (-not $token) {
  $tokenPath = Join-Path $cpxHome 'token'
  if (Test-Path $tokenPath) { $token = (Get-Content $tokenPath -Raw).Trim() }
}
if (-not $token) { exit 0 }

$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue)
if (-not $curl) { exit 0 }

# 훅 입력(JSON)을 stdin 으로 받는다.
$payload = [Console]::In.ReadToEnd()
if (-not $payload) { exit 0 }

# --- 게이트 1: 평가 턴에만 동작한다 ---
# 'cpx-record' 를 문자열로 찾으면 그 말이 오간 무관한 세션의 전사까지 올라간다.
# 마지막 응답 안의 펜스 블록을 꾺어내 실제로 JSON 으로 파싱되는지까지 확인한다.
# 형식을 글로 설명하는 세션은 여기서 걸러진다.
$isRecordTurn = $false
try {
  $msg = (ConvertFrom-Json $payload -ErrorAction Stop).last_assistant_message
  if ($msg -and ($msg -match '(?s)```cpx-record\s*(\{.*?\})\s*```')) {
    try { ConvertFrom-Json $Matches[1] -ErrorAction Stop | Out-Null; $isRecordTurn = $true } catch { }
  }
} catch { }
if (-not $isRecordTurn) { exit 0 }

$dataDir = if ($env:CLAUDE_PLUGIN_DATA) { $env:CLAUDE_PLUGIN_DATA } else { $env:TEMP }
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

# --- 게이트 2: 같은 턴 중복 업로드 방지 ---
$sha = [System.Security.Cryptography.SHA1]::Create()
$key = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($payload))).Replace('-','')
$lock = Join-Path $dataDir 'cpx-last'
if ((Test-Path $lock) -and ((Get-Content $lock -Raw).Trim() -eq $key)) { exit 0 }
Set-Content -Path $lock -Value $key -Encoding ascii

$hookFile = Join-Path $dataDir ("cpx-hook-$PID.json")
$trFile   = Join-Path $dataDir ("cpx-tr-$PID.jsonl")
$cfgFile  = Join-Path $dataDir ("cpx-curl-$PID.conf")
[IO.File]::WriteAllText($hookFile, $payload, [Text.UTF8Encoding]::new($false))

try {
  # --- 전사 첨부 여부 ---
  $sendTranscript = $true
  $configPath = Join-Path $cpxHome 'config'
  if ((Test-Path $configPath) -and ((Get-Content $configPath -Raw) -match 'transcript=0')) {
    $sendTranscript = $false
  }

  $transcriptPath = $null
  if ($sendTranscript) {
    try {
      $transcriptPath = (ConvertFrom-Json $payload).transcript_path
    } catch { $transcriptPath = $null }
  }

  # 토큰을 -H 로 넘기면 프로세스 인자에 그대로 남는다. -K 설정 파일로 옮겨 뺀다.
  # (PowerShell 5.1 은 네이티브 stdin 에 BOM 을 붙여 -K - 를 못 쓴다)
  [IO.File]::WriteAllText($cfgFile, "header = `"Authorization: Bearer $token`"`n", [Text.UTF8Encoding]::new($false))

  $args = @(
    '-K', $cfgFile,
    '-sS', '-m', '20', '-X', 'POST', $endpoint,
    '-F', "hook=@$hookFile;type=application/json"
  )

  if ($transcriptPath -and (Test-Path $transcriptPath)) {
    # 전사가 길면 Firestore 문서 상한을 넘으므로 뒷부분만 보낸다.
    Get-Content $transcriptPath -Tail 3000 | Set-Content -Path $trFile -Encoding utf8
    $args += @('-F', "transcript=@$trFile;type=application/jsonl")
  }

  & curl.exe @args
} finally {
  Remove-Item $hookFile, $trFile, $cfgFile -Force -ErrorAction SilentlyContinue
}

exit 0
