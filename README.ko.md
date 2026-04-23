# ddaro (따로)

> Language: [English](README.md) · **한국어**

**Worktree 기반 병렬 작업 플러그인.** Main을 건드리지 않고 격리된 worktree + branch 에서 작업, 삭제 검증 후 commit + push, 변경 규모별 자동 리뷰 후 merge. 세션/IDE 크래시 시에도 context MD 로 복원.

여러 Claude Code 세션을 동시에 돌릴 때, 또는 실험하면서 main 은 깨끗하게 유지하고 싶을 때 — ddaro 가 안전망 씌운 일회용 worktree 를 만들어줍니다. 각 worktree는 자기 branch, 자기 lock, 자기 디스크 메모리를 가져서 세션이 죽어도 맥락이 사라지지 않습니다.

---

## Quick Start

### 1. 마켓플레이스 등록 (처음 한 번만)

```
/plugin marketplace add https://github.com/minwoo-data/ddaro.git
```

### 2. 플러그인 설치

```
/plugin install ddaro@ddaro
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
| `/ddaro:summary [name]` | 크래시 복구용 내용 기반 요약 |
| `/ddaro:clean [name]` | merge 된 worktree 사후 정리 |
| `/ddaro:abandon <name>` | 3겹 보호 후 완전 폐기 |
| `/ddaro:setting` | 대화형 설정 메뉴 |
| `/ddaro:config [key]` | 직접 설정 변경 |

`/ddaro <subcommand>` 형태로도 호출 가능.

---

## 주요 기능

- **물리 격리** — 각 작업은 독립 git worktree + 독립 폴더. 병렬 Claude 세션 간 충돌 원천 차단.
- **삭제 검증 commit** — diff의 삭제 라인을 분류 (교체 / 포맷 / 순수 삭제 / 함수 제거 / 100줄+) 하여 위험한 것만 확인받음.
- **규모별 자동 리뷰** — 소 diff 는 삭제 재확인, 중 diff 는 `triad` 자동 호출, 대 diff 는 `prism` 자동 호출.
- **크래시 복구 context** — 매 commit 마다 `.ddaro/context/<sha>.md` 기록 + `CURRENT.md` 갱신. 세션/IDE 크래시 후 `/ddaro:summary` 한 번이면 복원.
- **3겹 보호**:
  - 1층: `protected_worktrees` config 목록
  - 2층: `.git/ddaro-owned` 소유권 플래그
  - 3층: `abandon` 시 `yes, I'm sure` 타이핑 확인
- **네이밍 전략** — 숫자(기본), 또는 동물 / 한국 도시 / 미국 주 / 과일 / 그리스 문자. `/ddaro:setting` 에서 전환.
- **언어 지원** — 모든 출력이 영어(기본) 또는 한국어. config 로 전환.

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

## 요구사항

- Claude Code (`/plugin` 지원 버전)
- Git 2.5+ (worktree 명령 필요)
- `gh` CLI (PR path 용 — 선택적, local merge 는 없어도 OK)
- Windows (Git Bash / WSL2), macOS, Linux 지원.

---

## 철학

Main worktree 는 **수신처** — 보기만 하지 직접 고치지 않음. 모든 작업은 ddaro worktree 에서 작업별로 하나씩. 작업 끝나면 리뷰 후 merge, worktree 는 정리. Main 은 깨끗하게, 히스토리는 의도적으로.

Context MD 층은 Claude 세션이 크래시나 재시작 시 망각하는 문제를 해결합니다. tmux 나 쉘 상태에 의존하는 대신, 매 commit 후 뭘 했는지 디스크에 기록. 그 파일이 메모리지 Claude 프로세스가 아닙니다.

---

## License

MIT — [LICENSE](LICENSE) 참조

## Author

Minwoo Park — [github.com/minwoo-data](https://github.com/minwoo-data)

## Contributing

Issues 와 PR 환영합니다: [github.com/minwoo-data/ddaro](https://github.com/minwoo-data/ddaro)
