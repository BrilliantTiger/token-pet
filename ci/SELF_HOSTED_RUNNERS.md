# 실기기 러너 (self-hosted) — 등록 절차

`tests.yml` 의 `real-macos` / `real-windows` 잡은 대표님의 Mac·Windows PC 에서 돈다. 그 기기에 실제로 깔린
CLI 와 실제 로그인 상태로 앱의 판정을 확인한다(`ci/real_machine_check.py`): 로그인돼 있으면 사용량 값이
바로 읽히고, 설정 줄이 [로그인]을 내밀지 않고, 흐름을 시작해도 창·프로세스가 뜨지 않는다.

**등록은 대표님 PC 에 프로그램을 깔고 로그인 항목을 만든다. 대표님 확인 뒤에만 한다.**

## 등록 전에 — 저장소 설정 (공개 저장소라서 필수)

이 저장소는 공개다. 포크의 PR 은 **포크가 고친 워크플로 파일**로 돈다 — 잡의 `if:` 와 `runs-on:` 도
포크가 바꿀 수 있다. 그래서 워크플로 안의 조건만으로는 막을 수 없고, 저장소 설정으로 막는다:

```sh
gh api -X PUT repos/BrilliantTiger/token-pet/actions/permissions/fork-pr-contributor-approval \
  -f approval_policy=all_external_contributors
```

(Settings → Actions → General → "Require approval for all external contributors". 2026-11-19 에 이 값으로
바꿨다 — 그 전의 `first_time_contributors` 는 한 번 머지된 적 있는 외부 기여자의 PR 을 승인 없이 돌린다.) 두 등록
스크립트는 이 값이 아니면 등록을 거절한다. 외부 PR 의 워크플로 실행을 승인하기 전에는 `.github/` 와
`ci/` 의 변경을 본다.

## 등록

| | 명령 | 러너가 도는 자리 |
| --- | --- | --- |
| macOS | `ci/register-runner-macos.sh` | 로그인한 사용자의 LaunchAgent (`~/actions-runner-token-pet`) |
| Windows | `powershell -ExecutionPolicy Bypass -File ci\register-runner-windows.ps1` | 로그인 때 시작하는 예약 작업 (`%USERPROFILE%\actions-runner-token-pet`) |

둘 다 `gh` 로그인이 필요하다(저장소 관리자 권한). 스크립트가 하는 일: 최신 actions/runner 를 받아 SHA-256 을
릴리스 노트의 값과 대조 → 저장소에 등록(라벨 `self-hosted` + `macOS`/`Windows`) → 로그인 때 자동 시작.

**두 잡은 막는 게이트다.** 러너가 내려가 있으면 잡은 대기하다 실패하고, 그동안 머지와 게시는 막힌다 —
실기기에서 확인하지 못한 것은 내보내지 않는다. 게시는 `main` 의 실기기 잡 두 개가 초록일 때만 한다.
세 제공자 중 하나도 로그인돼 있지 않은 기기에서는 잡이 실패한다(아무것도 검증하지 못한 것은 초록이 아니다).

서비스(데몬·Windows 서비스)로 돌리지 않는다 — 사용자의 키체인·자격 증명 관리자·CLI 로그인을 볼 수 없다.

macOS 러너는 **화면에 로그인한 사용자의 세션**에서 떠야 한다(`svc.sh install` 이 만드는 LaunchAgent). SSH 나
원격 셸에서 `./run.sh` 로 띄우면 로그인 키체인이 잠겨 있어 Claude Code·Gemini 의 로그인 정보를 읽지 못하고,
실기기 잡은 `login keychain locked: True` 를 찍고 실패한다(첫 등록 때 실제로 그랬다).

## 언제 도는가

같은 저장소의 PR, `main`·`dev` push, `v*` 태그, `workflow_dispatch`. 포크의 PR 에서는 돌지 않는다.

## 잡이 하지 않는 것

브라우저·터미널·로그인 창을 열지 않는다(그 자리는 전부 기록만 하는 대역이다). 로그에는 제공자 이름·
참/거짓·행 개수·오류 종류만 남는다 — 토큰·경로·계정·사용량 값은 남지 않는다.
