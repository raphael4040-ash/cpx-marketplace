# CPX 자동 업로드 훅 (Windows PowerShell)
#
# upload.sh 와 동일한 역할. Git Bash 가 없는 Windows 에서만 실제로 동작한다.
# Stop 훅은 모든 세션의 모든 턴에서 실행되므로, 게이트를 통과하기 전에는
# 네트워크를 절대 건드리지 않는다.

$ErrorActionPreference = 'SilentlyContinue'

# sh 가 있으면 upload.sh 가 이미 처리한다. 중복 업로드를 막기 위해 여기서 빠진다.
if (Get-Command sh -ErrorAction SilentlyContinue) { exit 0 }

# 배포된 Cloudflare Worker 주소. CPX_ENDPOINT 환경변수로 덮어쓸 수 있다.
$endpoint = if ($env:CPX_ENDPOINT) { $env:CPX_ENDPOINT } else { 'https://cpx-upload.raphael40402652.workers.dev/upload' }

$cpxHome = Join-Path $env:USERPROFILE '.cpx'
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
if ($payload -notmatch 'cpx-record') { exit 0 }

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

  $args = @(
    '-sS', '-m', '20', '-X', 'POST', $endpoint,
    '-H', "Authorization: Bearer $token",
    '-F', "hook=@$hookFile;type=application/json"
  )

  if ($transcriptPath -and (Test-Path $transcriptPath)) {
    # 전사가 길면 Firestore 문서 상한을 넘으므로 뒷부분만 보낸다.
    Get-Content $transcriptPath -Tail 3000 | Set-Content -Path $trFile -Encoding utf8
    $args += @('-F', "transcript=@$trFile;type=application/jsonl")
  }

  & curl.exe @args
} finally {
  Remove-Item $hookFile, $trFile -Force -ErrorAction SilentlyContinue
}

exit 0
