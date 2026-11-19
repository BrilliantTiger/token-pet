# 실기기 러너 (self-hosted)

`tests.yml` 의 `real-macos` / `real-windows` 잡은 대표님의 집 Mac mini 와 Windows PC 에서 돈다. 그 기기에 실제로
깔린 CLI 와 실제 로그인 상태로 앱의 판정을 확인한다(`ci/real_machine_check.py`): 로그인돼 있으면 사용량 값이
바로 읽히고, 설정 줄이 [로그인]을 내밀지 않고, 흐름을 시작해도 창·프로세스가 뜨지 않는다.

**두 잡은 막는 게이트다.** 실패하거나 러너가 내려가 있으면(잡은 대기하다 실패한다) 머지와 게시가 막힌다 —
실기기에서 확인하지 못한 것은 내보내지 않는다. 게시는 `main` 의 실기기 잡 두 개가 초록일 때만 한다.
세 제공자 중 하나도 확인하지 못한 기기에서는 잡이 실패한다(아무것도 검증하지 못한 것은 초록이 아니다).

## 러너 — 이미 있는 조직 러너를 쓴다

새로 등록하지 않는다. BrilliantTiger 조직의 러너 그룹 `token-pet`(token-pet 저장소만, 공개 저장소 허용)에
있는 두 대를 쓴다:

| 러너 | 기기 | 워크플로의 `runs-on` |
| --- | --- | --- |
| `token-pet-mac-1` | 집 Mac mini | `[self-hosted, macOS, token-pet]` |
| `token-pet-win-1` | Windows PC | `[self-hosted, Windows, token-pet]` |

상태 확인: `gh api orgs/BrilliantTiger/actions/runners --jq '.runners[] | "\(.name) \(.status)"'`

회사 Mac mini 에는 러너를 두지 않는다(대표님 결정, 2026-11-19).

## 러너는 로그인한 사용자의 세션에서 돌아야 한다

실기기 잡이 보는 것은 사용자의 키체인·자격 증명 관리자·CLI 로그인이다. 그것이 안 보이는 자리에서 도는 러너는
아무것도 검증하지 못한다.

- **macOS — LaunchAgent 의 `SessionCreate` 를 지운다.** `svc.sh install` 이 만드는 plist 에는
  `SessionCreate = true` 가 들어 있고, 그러면 러너가 **새 보안 세션**에서 떠 로그인 키체인이 잠긴 것으로 보인다.
  앱은 잠긴 키체인에 묻지 않으므로 Claude Code·Gemini 의 값이 하나도 읽히지 않는다(2026-11-19 첫 실행이
  그랬다 — 같은 기기의 사용자 셸에서는 값이 읽혔다). 잡 로그의 첫 줄 `login keychain locked: True` 가 그 표시다.

  ```sh
  cd ~/actions-runner/token-pet-mac-1 && ./svc.sh stop
  /usr/libexec/PlistBuddy -c "Delete :SessionCreate" ~/Library/LaunchAgents/actions.runner.BrilliantTiger.token-pet-mac-1.plist
  ./svc.sh start
  ```

  `svc.sh install` 을 다시 하면 그 키가 되살아난다 — 다시 지운다. SSH 나 원격 셸에서 `./run.sh` 로 띄운 러너도
  같은 이유로 안 된다.
- **Windows — 서비스가 아니라 로그인한 사용자의 세션에서.** Windows 서비스는 세션 0 의 다른 계정으로 돌아
  사용자의 자격 증명 관리자와 CLI 로그인을 볼 수 없다.

## 공개 저장소라서 — 포크의 PR

포크의 PR 은 **포크가 고친 워크플로 파일**로 돈다 — 잡의 `if:` 와 `runs-on:` 도 포크가 바꿀 수 있다. 그래서
워크플로 안의 조건(같은 저장소의 PR 만)만으로는 부족하고, 저장소 설정이 함께 막는다:

```sh
gh api repos/BrilliantTiger/token-pet/actions/permissions/fork-pr-contributor-approval --jq .approval_policy
# all_external_contributors 여야 한다 (2026-11-19 에 이 값으로 바꿨다)
```

외부 PR 의 워크플로 실행을 승인하기 전에는 `.github/` 와 `ci/` 의 변경을 본다.

## 언제 도는가

같은 저장소의 PR, `main`·`dev` push, `v*` 태그, `workflow_dispatch`. 포크의 PR 에서는 돌지 않는다.

## 잡이 하지 않는 것

브라우저·터미널·로그인 창을 열지 않는다(그 자리는 전부 기록만 하는 대역이다). 로그에는 제공자 이름·
참/거짓·행 개수·오류 종류만 남는다 — 토큰·경로·계정·사용량 값은 남지 않는다.
