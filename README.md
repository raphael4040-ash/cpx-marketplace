# CPX 시뮬레이터 플러그인

한국 의사국가시험 실기(CPX/OSCE) 대비 모의 표준화환자(SP) 시뮬레이터입니다.
Claude Code 안에서 문진·신체진찰을 연습하고 100점 배점으로 채점받으며,
결과는 웹 기록판의 본인 계정에 자동으로 쌓입니다.

📄 **[사용 설명서 PDF](https://cpx-practice.github.io/cpx-manual.pdf)** — 설치부터 면담·채점·기록판
사용법, 저장되는 것과 끄는 방법, 문제해결까지 담은 15쪽 문서입니다. 처음이라면 이것부터 보세요.
아래는 요약입니다.

## 설치 (유저용)

```bash
claude plugin marketplace add raphael4040-ash/cpx-marketplace
```

그다음 Claude Code 안에서:

```
/plugin install cpx@cpx-marketplace
```

설치 후 `/reload-plugins` 를 실행하라는 안내가 나오면 실행하세요.

## 사용법

| 명령 | 동작 |
|---|---|
| `/cpx:start` | 무작위 케이스로 연습 시작 (즉시 환자 역할 진입) |
| `/cpx:start 흉통` | 주제를 지정해서 시작 |
| `진찰` | 문진 종료 → 신체진찰 모드 |
| `평가` | 역할 종료 → 채점표 기반 피드백 |
| `/cpx:pair <코드>` | 웹 기록판과 연결 (최초 1회) |

국시원 공식 48개 임상표현을 모두 담고 있고, 입실 전 안내문(Doorway Information)은
현행 시험대로 제공하지 않습니다.

## 기록 자동 저장

`/cpx:pair` 로 한 번 연결해두면 `평가` 가 끝날 때마다 결과가 자동으로 올라갑니다.

**연결하지 않으면 아무것도 전송되지 않습니다.** 연결한 뒤에도 업로드 훅은
평가 메시지에 기록 블록이 있을 때만 동작하며, 그 외의 모든 대화는 네트워크를 타지 않습니다.

전사 저장을 끄려면 `~/.cpx/config` (Windows는 `%USERPROFILE%\.cpx\config`) 에:

```
transcript=0
```

연결을 끊으려면 `~/.cpx/token` 파일을 지우면 됩니다.

## 구조

```
cpx/
├─ .claude-plugin/plugin.json
├─ skills/
│  ├─ start/SKILL.md          SP 역할 지침 + 채점 형식
│  │  └─ refs/                topics.md(48개 임상표현), checklist.md(배점표)
│  └─ pair/SKILL.md           기록판 연결
└─ hooks/
   ├─ hooks.json              Stop 훅 등록
   ├─ upload.sh               macOS · Linux · Git Bash
   └─ upload.ps1              Git Bash 없는 Windows
```

## 운영자 배포 절차

1. 이 폴더를 GitHub 공개 레포로 올립니다 (레포 이름 `cpx-marketplace` 권장).
2. `REPLACE_ME` 를 모두 교체합니다:
   - `.claude-plugin/marketplace.json` — `owner.name`
   - `cpx/.claude-plugin/plugin.json` — `author.name`, `homepage`
   - `cpx/hooks/upload.sh`, `cpx/hooks/upload.ps1` — `ENDPOINT` (워커 주소)
   - 이 README의 설치 명령
3. 로컬 확인:

```bash
claude --plugin-dir ./cpx
```

4. 검증:

```bash
claude plugin validate ./cpx
```

케이스나 채점 기준을 고칠 때는 `cpx/.claude-plugin/plugin.json` 의 `version` 을 올려야
기존 유저에게 업데이트가 전달됩니다.

같은 변경이 두 곳에 더 걸립니다. 기록판 저장소의 `docs/topics.js`(케이스 목록)와
`manual/cpx-manual.html`(설명서 4장 배점, 부록 A 케이스 목록)입니다. 설명서 PDF 를 다시 뽑는
명령은 그 저장소 README 에 있습니다.
