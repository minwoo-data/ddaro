# ddaro (따로)

> Language: [English](README.md) · **한국어**

**여러 AI 코딩 세션을 돌려도 repo가 절대 꼬이지 않게.**

AI 코딩은 이제 병렬이 기본입니다. billing 전용 Claude 세션, auth 전용 세션, 실험용 세션. 그런데 git은 한 사람이 하나씩 하던 시절에 설계된 도구라, 두 세션이 같은 working tree를 건드리면 서로를 조용히 덮어씁니다. ddaro는 병렬 AI 개발을 위해 git workflow를 새로 짠 세션 격리 레이어입니다.

```
/ddaro:start   -> 안전하게 작업   (세션당 worktree + branch 새로 생성)
/ddaro:commit  -> 스냅샷         (삭제 검증 commit + auto-push + context MD)
/ddaro:merge   -> 리뷰 + merge   (규모별 리뷰 + 충돌 사전 체크)
```

여러 Claude Code 세션이 서로 코드를 덮어쓰거나, 작업이 조용히 사라진 적 있나요? ddaro는 각 세션을 자기 worktree와 branch에 구조적으로 격리시켜 충돌을 사전에 차단하고, merge할 때 덮어쓰는 것이 없는지 자동으로 확인합니다.

---

## 30초 데모

**ddaro 없이:**

Session A는 billing을 고치고 Session B는 auth를 리팩터링. 둘이 동시에 `src/services/`를 건드립니다. alt-tab 하는 순간 Session B가 Session A가 방금 저장한 파일을 덮어씀. commit은 정상처럼 보여서 일주일 뒤에야 fix가 사라진 걸 발견합니다.

**ddaro로:**

Session A에서 `/ddaro:start billing`, Session B에서 `/ddaro:start auth`. 세션 둘, 폴더 둘, branch 둘. 충돌 자체가 구조적으로 불가능. `/ddaro:merge` 시점에 ddaro가 diff를 보여주고, 대체 없이 지워지는 삭제를 플래그하며, `main`의 파일이 조용히 사라질 상황이면 merge를 거부합니다.

## 누가 써야 하는가

- **병렬 Claude Code 세션** - 세션들이 서로 편집을 덮어쓰는 것을 막는 가장 빠른 방법
- **위험한 리팩터링** - 임시 worktree에서 매 commit마다 auto-push 되어, 크래시나 잘못된 판단이 작업물을 먹을 수 없음
- **장기 실험 브랜치** - 각 worktree가 topic + lock 파일을 들고 있어 일주일 뒤에도 "이 브랜치가 뭐였지"가 명확
- **크래시가 잦은 환경** - 매 commit 후 plain-text context를 디스크에 기록. `/ddaro:summary` 한 번이면 전체 그림 복원.

## 자매 도구 (같은 마켓플레이스)

- **[prism](https://github.com/minwoo-data/prism)** - 5-agent 병렬 코드 리뷰 + singleton 검증. 주요 PR 전에 사용.
- **[triad](https://github.com/minwoo-data/triad)** - 디자인 문서 3관점 숙의 (LLM 명확성 / 아키텍처 / 엔드유저).
- **[mangchi](https://github.com/minwoo-data/mangchi)** - Claude + Codex cross-model 반복 코드 다듬기.

---

## Quick Start

### 1. haroom_plugins 마켓플레이스 등록 (처음 한 번만)

```
/plugin marketplace add https://github.com/minwoo-data/haroom_plugins.git
```

`ddaro` 는 haroom 플러그인 (prism, triad, mangchi) 과 함께 **haroom_plugins** aggregator 를 통해 배포됩니다.

### 2. 플러그인 설치

```
/plugin install ddaro
```

### 3. 사용

```
/ddaro:start           # 새 격리 worktree 생성 (첫 실행 시 설정 프롬프트)
/ddaro:commit          # 안전 검증 + commit + push + context 스냅샷
/ddaro:merge           # 규모별 리뷰 + merge + 정리
```

설치/업데이트 후 Claude Code 재시작.

---

## Commands

| 명령 | 역할 |
|---|---|
| `/ddaro:start [name]` | 새 worktree + branch + lock 생성 |
| `/ddaro:commit [msg]` | 전체 stage, 삭제 검증, 확인, commit, push, context MD 기록 |
| `/ddaro:merge` | 충돌 사전 확인, 규모별 리뷰, merge, y/n 정리 |
| `/ddaro:status` | 현재 worktree 상태 (branch, commits, push, lock) |
| `/ddaro:list` | ddaro 소유 worktree 전체 기술 요약 |
| `/ddaro:summary [name]` | 읽기 전용 내용 요약 |
| `/ddaro:resume` | worktree 선택 + 요약 + cd + paste prompt (크래시 복구 / 며칠 뒤 재개) |
| `/ddaro:clear [name]` | merge 된 worktree 사후 정리 (v0.1.2에서 `/ddaro:clean`에서 rename) |
| `/ddaro:abandon <name>` | 3겹 보호 후 완전 폐기 |
| `/ddaro:setting` | 대화형 설정 메뉴 |
| `/ddaro:config [key]` | 직접 설정 변경 |

`/ddaro <subcommand>` 형태로도 호출 가능.

---

## 주요 기능

- **물리 격리** - 각 작업은 독립 git worktree + 독립 폴더. 병렬 Claude 세션 간 충돌 원천 차단.
- **삭제 검증 commit** - diff의 삭제 라인을 분류 (교체 / 포맷 / 순수 삭제 / 함수 제거 / 100줄+) 하여 위험한 것만 확인받음.
- **규모별 자동 리뷰** - 소 diff 는 삭제 재확인, 중 diff 는 `triad` 자동 호출, 대 diff 는 `prism` 자동 호출.
- **크래시 복구 context** - 매 commit 마다 `.ddaro/context/<sha>.md` 기록 + `CURRENT.md` 갱신. 세션/IDE 크래시 후 `/ddaro:summary` 한 번이면 복원.
- **3겹 보호**:
  - 1층: `protected_worktrees` config 목록
  - 2층: `.ddaro/OWNED` 소유권 플래그
  - 3층: `abandon` 시 `yes, I'm sure` 타이핑 확인
- **네이밍 전략** - 숫자(기본), 또는 동물 / 한국 도시 / 미국 주 / 과일 / 그리스 문자. `/ddaro:setting` 에서 전환.
- **언어 지원** - 모든 출력이 영어(기본) 또는 한국어. config 로 전환.

---

## 설정

첫 `/ddaro:start` 시 5단계 설정:

1. 언어 (english / korean)
2. Main worktree (ddaro 가 절대 건드리지 않을 폴더)
3. 보호 목록 (다른 작업용 폴더)
4. 네이밍 전략 (`d-number` / `d-pool` / `ddaro-number` / `ddaro-pool`)
5. Name pool (`korea_city` / `animal` / `us_state` / `fruit` / `greek`)

나중 변경: `/ddaro:setting` (메뉴) 또는 `/ddaro:config <key> <value>`.

Config 파일 위치: `<main-worktree>/.ddaro/config.json`

---

## 실제 사용 예

```
/ddaro:start billing-fix
# → myapp-d-billing-fix worktree + d-billing-fix branch 생성
# → 새 터미널용 복붙 프롬프트 출력

# ... 새 worktree 에서 편집, Claude 실행 ...

/ddaro:commit "재현 테스트"
# → stage, 삭제 검증, commit, push
# → .ddaro/context/<ts>-<sha>.md 기록

/ddaro:commit "날짜 계산 fix"

/ddaro:merge
# → origin fetch, 충돌 dry-run, 규모 측정 (소/중/대)
# → 중/대면 자동 리뷰
# → PR 생성 또는 local merge
# → worktree 정리 y/n

# 나중에 크래시 복구:
cd myapp-d-billing-fix
claude
/ddaro:summary
# → 뭘 했고 어디서 끊겼고 다음 뭐 할지 전체 복원
```

---

## 업데이트

```
/plugin update
```

그 후 Claude Code 재시작.

---

## 문제 해결

### 설치했는데 `/ddaro:*` 명령이 안 나와요

Plugin 은 Claude Code 시작 시에만 로드됩니다. `/ddaro:start` 및 기타 subcommand 가 안 뜨면:

1. **Claude Code 재시작** - install/update 후 반드시 필요.
2. `/plugin` 실행해서 `ddaro` 가 **enabled** 인지 확인.
3. 목록에 있지만 비활성이면: `/plugin enable ddaro@ddaro`.
4. 그래도 안 뜨면 `~/.claude.json` 열어서 `enabledPlugins` 에 `ddaro` 항목이 있는지 확인. `{}` 로 비어있으면 설치 미완료 → `/plugin install ddaro@ddaro` 재실행.

증상 체크: `/ddaro` 가 local skill 만 잡히고 namespace 형태 (`/ddaro:start`, `/ddaro:commit`, …) 가 안 보이면 plugin 이 로드되지 않은 상태.

### Marketplace add 는 됐는데 install 이 실패

- 쉘에서 `https://github.com/minwoo-data/ddaro.git` 에 git clone 가능한지 확인.
- Marketplace 제거 후 재등록: `/plugin marketplace remove ddaro` 후 Quick Start 1번 다시.

---

## 요구사항

- Claude Code (`/plugin` 지원 버전)
- Git 2.5+ (worktree 명령 필요)
- `gh` CLI (PR path 용 - 선택적, local merge 는 없어도 OK)
- Windows (Git Bash / WSL2), macOS, Linux 지원.

---

## 철학

Main worktree 는 **수신처** - 보기만 하지 직접 고치지 않음. 모든 작업은 ddaro worktree 에서 작업별로 하나씩. 작업 끝나면 리뷰 후 merge, worktree 는 정리. Main 은 깨끗하게, 히스토리는 의도적으로.

Context MD 층은 Claude 세션이 크래시나 재시작 시 망각하는 문제를 해결합니다. tmux 나 쉘 상태에 의존하는 대신, 매 commit 후 뭘 했는지 디스크에 기록. 그 파일이 메모리지 Claude 프로세스가 아닙니다.

---

## License

MIT - [LICENSE](LICENSE) 참조

## Author

haroom - [github.com/minwoo-data](https://github.com/minwoo-data)

## Contributing

Issues 와 PR 환영합니다: [github.com/minwoo-data/ddaro](https://github.com/minwoo-data/ddaro)
