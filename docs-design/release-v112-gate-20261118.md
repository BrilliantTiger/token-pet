# v1.1.2 — 실행 게이트, 조정자 서명, 릴리즈 운영자 지정

이 릴리즈의 조정자 `release-coordinator-v112`(2026-11-18)가 쓴다. 이 릴리즈에서 다른 역할은 맡지 않았다.
이 파일 하나가 AGENTS.md §6 항목 1–5 를 v1.1.2 에 대해 채운다. 게이트 조건 밖의 사실 둘(Apple 공증 계약,
Windows 산출물)은 맨 아래 "게이트 밖의 사실" 에 관측한 그대로 적는다.

## 무엇을 릴리즈하나
- **릴리즈할 커밋: main `ea8922d`** (PR #12, dev → main 머지). 트리 `e5022140…` 는 PR #11 의 끝 `9e2eeba`, dev `a9a330b` 와
  같다 — `git diff 9e2eeba ea8922d`, `git diff a9a330b ea8922d` 모두 출력 없음.
  - 바탕: main `75a7ddd`(v1.1.1 뒤의 사이트 주소 변경). 태그 `v1.1.1` 은 `d1b38bc`.
  - 수정(PR #10 → dev `1be91ac`, Linear TOK-42): `5b86e95` — 게이지가 하나일 때 필 폭을 인라인된 실제 줄로 잰다, 글자 예산의
    `SUMMARY_MIN_W` 바닥을 없앤다, `geom()` 의 W 에 필 바닥을 넣는다(검토 지적 F1). 셋 다 `claude_pet.py` 의 `run_gui` 안.
  - 테스트·핀: `3375ce1`, `6e6c2ba`, `99516c8`.
  - 릴리즈(PR #11 → dev `a9a330b`): `1c2ab4b` "release: ClaudePet v1.1.2" (APP_VERSION 1.1.2, RELEASE_NOTES v1.1.2,
    `verify_release_artifact.py` 사용 예의 버전 줄), `9e2eeba`(릴리즈 계약, 핀).
  - Windows: `git diff v1.1.1 ea8922d -- windows/` 출력 없음. Windows 판은 바뀐 코드 없이 같은 1.1.2 로 나간다.
- **이 기록 커밋은 `tok-42-release-v1.1.2-gate` 브랜치에만 있다.** 바탕은 `ea8922d` 이고 `docs-design/` 의 이 문서 하나만 더한다.
  main·dev 에 직접 올리지 않았고 PR 도 열지 않았다. 그래서 태그는 이 커밋이 아니라 `ea8922d` 에 단다(항목 5).
- **사용자 승인, 원문 그대로.** 사용자가 메인 세션(pill-width-dev)에 직접 쳤다. 조정자는 이를 전달받았다.
  - 릴리즈 커밋 `1c2ab4b` 메시지(그리고 PR #10·#11 본문)에 원문이 있는 셋:
    - 질문 "'적용'은 어디까지 할까요?" 에 "릴리스까지" 선택
    - "서명·공증·게시까지 다 진행해"
    - 질문 "v1.1.2 릴리스에 Windows 파일도 넣을까요?" 에 "Windows도 함께" 선택
  - 그 뒤, Windows PC 가 꺼져 있다는 말을 들은 다음: "어디까지 했는지 확인하고 릴리즈 하던지 해 빨리 내가 아까 보낸 이슈 랑 같이"
    — **이 문장은 이 기록 전에는 git·PR 어디에도 없다**(`1c2ab4b`·`9e2eeba` 메시지와 PR #10·#11·#12 본문을 읽어 확인).
    메인 세션이 조정자에게 전달했고, 이 기록이 처음 남기는 곳이다.
  - 이 말들은 릴리즈 순서 전체를 승인한다(AGENTS §6 일괄 승인). 게이트를 바꾸지 않고, 자격 없는 에이전트를 `[ASK-OP]`
    단계에 자격 있게 만들지도 않는다. 조정자가 승인을 주는 것도 아니다(§6 가드 4).
  - **조정자가 정하지 않는 범위 하나.** "내가 아까 보낸 이슈" 가 어느 이슈인지는 이 문장만으로 정해지지 않는다.
    TOK-42(Linear 생성 2026-11-18T01:50Z, Done)는 `ea8922d` 에 들어 있다. TOK-44 "[공통] Gemini — Antigravity CLI(agy)
    로그인으로 사용량 읽기"(생성 02:08Z, In Progress)는 들어 있지 않다 — 원격 브랜치와 열린 PR 이 없고, 그 워크트리
    (`tok-44-gemini-agy-usage`, `a9a330b`)에는 커밋 없이 추적되지 않은 `tests/test_gemini_usage.py` 하나뿐이다.
    이 게이트는 `ea8922d`(TOK-42 만)를 판정한다. TOK-44 까지 v1.1.2 에 넣으라는 뜻이었다면 이 게이트로는 안 된다 — 그 변경의
    §8 조건과 새 릴리즈 커밋, 새 게이트가 필요하다. CLAUDE.md 대로 승인 범위는 넓히지 않고 글자대로 읽는다. 메인 세션은
    운영자를 띄우기 전에 사용자에게 어느 이슈인지 확인한다.

## 항목 1 — §8 조건 (릴리즈 전체)
- **트레일러:** 여섯 커밋 모두 `Developer:` / `Verifier:` 가 있고 서로 다르다(`git log -1 --format='%(trailers)'`).
  프로덕션 커밋(`5b86e95`, `1c2ab4b`)은 Developer pill-width-dev / Verifier pill-width-tests, 테스트 커밋(`3375ce1`, `6e6c2ba`,
  `99516c8`, `9e2eeba`)은 그 반대. 머지 커밋 셋(`1be91ac`, `a9a330b`, `ea8922d`)은 GitHub PR 머지라 트레일러가 없고 내용을 더하지
  않는다 — `git diff 99516c8 1be91ac`, `git diff 9e2eeba a9a330b`, `git diff a9a330b ea8922d` 모두 출력 없음.
- **분리(Condition B), `git log --stat` 로 확인:** 테스트 커밋 넷은 `tests/` 만 건드린다(`test_single_gauge_pill_width.py`,
  `test_summary_layout.py`, `test_manual_update_transaction.py`, `test_upload_artifact_gate.py`, `test_v1_1_2_release_contract.py`
  (`test_v1_1_1_release_contract.py` 에서 이름 옮김)). Developer 커밋 둘은 `claude_pet.py`, `RELEASE_NOTES.md`,
  `verify_release_artifact.py` 만 건드린다. 두 집합은 겹치지 않는다.
- **먼저 빨강:**
  - `3375ce1`: 커밋 본문에 `75a7ddd` 에서의 빨강 failures=4(I1 68건, I2 38건, I3 2건, I4 16건)가 실패 메시지와 함께 있다.
    CI run 44218896805(headSha `3375ce13f791…`, 테스트만 더한 커밋): `Ran 1073 tests in 384.820s` / `FAILED (failures=4, skipped=15)`,
    실패 넷 모두 `test_single_gauge_pill_width` 안(로그에서 확인), `Windows — gating contract: success`.
    로컬 기록 `/Users/yeongyu/claude-pet-wt/red-run-single-gauge.txt`: HEAD `75a7ddd`, 테스트 파일 sha256 `40cf21f1…06ec`
    (= `3375ce1` 의 파일, 조정자가 다시 해시), `Ran 6 tests` / `FAILED (failures=4)`.
  - `6e6c2ba`(검토 2라운드): 커밋 본문에 모든 내용 예산 14건(`75a7ddd`), 짧은 내용 19건(need·예산 수정 위, W 바닥 전)이 있다.
    로컬 기록 `red-run-single-gauge-every-content.txt`: `75a7ddd` 의 `claude_pet.py`(sha256 `f7d4c10f…42c4`), `Ran 7 tests` /
    `FAILED (failures=5)`. `red-run-short-content.txt`: HEAD `3375ce1` + 작업 트리의 need·예산 수정, 테스트 파일 sha256
    `fd6ec4b0…fb7fb`(= `6e6c2ba` 의 파일), `Ran 1 test` / `FAILED (failures=1)`.
  - 초록: `green-run-single-gauge.txt` — HEAD `5b86e95`, `claude_pet.py` sha256 `99a7ef39…e1da`(= `5b86e95` 의 파일), 재핀 두 파일은
    아직 커밋 전(`99516c8` 로 커밋), `Ran 1075 tests in 313.186s` / `OK (skipped=8)`, `Ran 271 tests in 1.278s` / `OK (skipped=23)`.
  - 핀(`99516c8`, `9e2eeba`): 소스 해시 핀 하네스는 바뀐 소스를 거부하므로 핀 갱신이 곧 빨강→초록이다. `9e2eeba` 본문에
    `2fbfedd`(앞선 릴리즈 커밋 후보, 부모 `1be91ac`, `1c2ab4b` 로 대체됨 — 로컬에 있음)에서의 빨강 하나(사용 예가
    `--expect-version 1.1.1`)가 기록돼 있다.
- **검토자:** 별도 검토 에이전트 `pill-width-review`. 수정을 두 라운드 승인했다 — 1차 지적 F1(`geom()` W 바닥)은 `5b86e95` 에
  넣었고, F2(옛 need 를 복제한 `settle()`)는 검증자가 `6e6c2ba` 에서 정리했다. v1.1.2 노트 문구도 승인했다(제안 둘 반영).
  - **정정 하나.** `5b86e95` 메시지의 "Windows 포트의 같은 120 바닥 두 곳은 화면에 영향이 없어" 는 검토자 말대로 절반만 맞다.
    글자 예산 바닥(`windows/claude_pet_win.py` 의 `_pill_text_budget`)은 영향이 없지만, Windows `geom()` 의 W 는
    `max(pw + cp.BTN_R * 2 + 16, want + 2 * cp.SUMMARY_EDGE)` 로 `SUMMARY_MIN_W + 2·SUMMARY_EDGE` 바닥이 없다. 그래서 배율 0.3·짧은
    내용에서 macOS F1 과 같은 잘림이 Windows 에 있다. 원래 있던 결함이고 이 릴리즈가 만들지 않았다(조정자가 `ea8922d` 의 코드에서
    확인). Linear TOK-42 댓글(2026-11-18T02:48Z)에 후속으로 남아 있다. 막지 않는다: v1.1.2 의 `windows/` 는 v1.1.1 과 같다.
  - 검토자의 승인은 PR #10·#11 본문과 위 Linear 댓글로 전달받았다. GitHub PR 리뷰 객체는 없다(`gh pr view --json reviews` 가 빈 목록).
- **추적되지 않은 파일:** 이 기록 외에 아무것도 더하거나 지우지 않았다. 메인 체크아웃(`/Users/yeongyu/claude-pet`)과 다른 워크트리는
  건드리지 않았다. 조정자 worktree 는 `git worktree add … -b tok-42-release-v1.1.2-gate origin/main` 으로 새로 만들었다.
  Windows PC 에서는 조정자 전용 터미널을 따로 열어 읽기 명령만 돌리고 닫았다(아래).
- **§5:** PR #11 본문의 "공백 정규화 기준 230자" 는 조정자 측정(221자, 항목 3)과 다르다. 450자 한도에는 둘 다 들고, 계약 테스트는
  파일에서 직접 잰다. 노트 본문의 숫자는 버전뿐이다.

## 항목 2 — 깨끗한 트리에서 전체 스위트
- 조정자 worktree `/Users/yeongyu/claude-pet-wt/release-v112-gate`, HEAD `ea8922d`, `git status --porcelain` 출력 없음(실행 전
  2026-11-18T04:15:56Z, 실행 뒤 04:21:16Z 모두). Python 3.13.7(python.org, PyObjC). 저장소 루트에서:
  - `python3 -m unittest discover -s tests` → `Ran 1082 tests in 317.976s` / `OK (skipped=8)`, exit 0
  - `python3 -m unittest discover -s windows/tests -t .` → `Ran 271 tests in 1.281s` / `OK (skipped=23)`, exit 0
- 검증자 pill-width-tests 의 결과(`9e2eeba` 메시지, `1c2ab4b` 위): 1082 OK (skipped=8), 271 OK (skipped=23) — 위와 같다.
- Windows 실기기(사용자 PC, `ea8922d`, 아래 "Windows 산출물"): `python -m unittest discover -s windows/tests -t .` →
  `Ran 271 tests in 2.559s` / `OK`(건너뜀 없음; 메인 세션은 PySide6 가 있어서라고 전했다).
- CI (모두 `gh run view <id> -R BrilliantTiger/token-pet` 로 확인):

  | run | 대상 | 이벤트 | 결과 |
  | --- | --- | --- | --- |
  | 44218896805 | `3375ce1`(테스트만) | workflow_dispatch | macOS failure(위의 빨강 4건), Windows success |
  | 44225300658 | 브랜치 `99516c8` | workflow_dispatch | macOS·Windows success |
  | 44226180679 | PR #10 (`99516c8`) | pull_request | macOS·Windows success |
  | 44229890865 | 릴리즈 브랜치 `9e2eeba` | workflow_dispatch | macOS·Windows success |
  | 44230827484 | PR #11 (`9e2eeba`) | pull_request | macOS·Windows success |
  | 44231651076 | dev `a9a330b` | push | macOS·Windows success |
  | 44232562606 | PR #12 (`a9a330b`) | pull_request | macOS·Windows success |
  | 44233351176 | main `ea8922d` | dynamic | `pages-build-deployment` success — **테스트 실행이 아니다** |

  `tests` 워크플로는 main push 에 걸려 있지 않아(`on.push.branches: ["claude/**", "dev"]`) `ea8922d` 에는 테스트 실행이 없다.
  `ea8922d` 의 트리가 `a9a330b`·`9e2eeba` 와 같으므로 44229890865·44230827484·44231651076·44232562606 이 같은 트리를 검사했다.
  CI 의 Windows 작업은 `windows-latest` 의 게이팅 계약이고, 포트 자체 스위트 단계는 `continue-on-error` 다.
- 이 기록 커밋은 `docs-design/` 의 문서 하나만 더하므로 스위트 결과에 영향이 없다.

## 항목 3 — 릴리즈 노트
- v1.1.2 섹션(`git diff 1c2ab4b ea8922d -- RELEASE_NOTES.md` 출력 없음 — 릴리즈 커밋 뒤 바뀌지 않음): 최상위 불릿 3개, 중첩 0,
  221자(공백 정규화, 계약 테스트의 `_notes_block` 으로 잼), 불릿마다 1–2 문장, 해시·소스 경로·테스트 언급 없음, 크기·빈도의
  모호한 표현 없음. 숫자는 버전 1.1.2 뿐. 인용 "조회 중…" 은 `TR["ko"]["loading"]` 과 같다. 사용자가 할 일은 "업데이트만 받으면
  되고 따로 할 일은 없습니다" 로 적혀 있다. 문장마다 `tests/test_v1_1_2_release_contract.py` 의 `StagedV112NotesFormatTests` 가
  소스와 게이트 클래스(`tests/test_single_gauge_pill_width.py`)에 묶는다.
- "Windows도 같은 1.1.2로 나오지만 바뀐 점은 없습니다": `windows/` 는 v1.1.1 과 같고, `claude_pet.py` 에서 바뀐 함수는 모두 `run_gui`
  안이며 `windows/` 는 `run_gui` 를 부르지 않는다(계약 테스트).
- v1.1.1 은 published(태그 `v1.1.1` → `d1b38bc`, GitHub 릴리즈 "ClaudePet v1.1.1" Latest). 태그의 `RELEASE_NOTES.md` 에서
  `**v1.1.1**` 부터 끝까지가 `ea8922d` 의 같은 부분과 바이트 단위로 같다(24121 바이트, sha256 `cfb8295e…886b`). `**v1.1.2**` 위의
  머리말도 같다. `PublishedV111NotesContractTests` 가 이를 핀한다. 한 글자도 바뀌지 않았다.

## 항목 4 — 조정자 서명
- **인증:** v1.1.2(`ea8922d`)를 실행 단계에 들어가도 된다고 인증한다. **게이트: GREEN.**
- GREEN 은 항목 1–5 에 대한 판정이다. 운영자 단계가 성공한다는 예측이 아니고, 위 "조정자가 정하지 않는 범위"(TOK-44)를 정하지도 않는다.
- **Windows 실기기(사용자 PC), `ea8922d` 에서:** Windows 테스트 `Ran 271` OK, `build_win.py` 배포물 게이트 통과, 무서명(원래대로).
  릴리즈할 커밋 `ea8922d` 그 자체에서 만들었으므로(v1.1.1 처럼 앞선 커밋과의 diff 를 따질 것이 없다) 출하 바이트와 같은 소스다.
- **확인하지 못한 것:**
  - Developer ID 서명·공증된 v1.1.2 번들의 실제 Mac 실행(운영자가 빌드한 뒤에야 존재한다).
  - 실제 화면에서 필이 더 잘리지 않는지. 이 동작은 생산 클로저를 돌리는 테스트로만 확인됐고, 화면으로 보지 않았다.
  - Windows 의 `build_win.py`·테스트 exit 0 과 `pip install -r windows\requirements.txt` 는 전달받았다. 조정자는 로그의 요약 줄과
    산출물 해시만 직접 봤다(아래).
  - 검토자 승인의 원문(전달받음), 네 번째 승인 문장(전달받음, 이 기록 전에는 git 에 없음).
  - Windows 갱신 동작(아래)은 코드를 읽어 확인했을 뿐 실기기에서 보지 않았다.

## 항목 5 — 릴리즈 운영자
- **자격 없음:** 조정자 release-coordinator-v112(이 기록의 작성자); pill-width-dev(메인 세션, 개발자, 그리고 이번 Windows 빌드를 돌린
  세션); pill-width-tests(검증자); pill-width-review(검토자); gemini-agy-tests(이 릴리즈에 들지 않은 TOK-44 의 검증자 — 같은 시간에
  같은 저장소에서 일하는 세션이라 뺀다); 그 밖의 Windows 빌드 세션. 이전 릴리즈의 운영자(release-operator-v111 포함)도 다시 쓰지 않는다.
- **지정 운영자:** `release-operator-v112`. 이 파일이 커밋된 뒤 이 일 하나만을 위해 새로 만든다. 이 릴리즈에서
  개발자·검증자·검토자·조정자 어느 역할도 맡지 않았다.
  - 작업 트리: `ea8922d` 의 분리 워크트리(이 기록 브랜치가 아니다). 시작 전에 `git rev-parse HEAD` = `ea8922d91dbc…`,
    `git status --porcelain` 출력 없음을 기록한다.
  - 시작 전 확인(읽기 전용, 제출 없음): `xcrun notarytool history --keychain-profile claudepet-notary` 가 403 없이 돌아오는지 본다
    (아래 "Apple 공증"). 403 이면 `./release.sh build` 도 시작하지 않고 멈춰 넘긴다.
  - 하나씩, 단계마다 결과를 기록하고 첫 실패에서 멈춘다: `./release.sh build`, `sign`, `notarize`, `universal`, `dmg`,
    그다음 태그 `v1.1.2` 를 만들어 push, 그다음 `./release.sh publish`, 그다음 Windows 자산 둘 업로드(아래).
  - **태그는 main 의 `ea8922d` 에 단다. 이 기록 커밋에 달지 않는다.** 이 커밋은 브랜치에만 있어 main 이력에 없다. 출하 바이트는
    어느 쪽이든 같지만(이 커밋은 `docs-design/` 문서 하나), v1.1.2 는 main 의 커밋이어야 한다. 이 기록은 나중에 PR 로 main 에
    들어가며, 태그에서는 닿지 않는다(v1.1.1 은 게이트 기록 커밋 `d1b38bc` 에 태그했다 — 이번에는 다르다).
  - 시작 전 상태(2026-11-18 조정자 확인): `git ls-remote --tags origin 'v1.1.2*'` 출력 없음,
    `gh release view v1.1.2 -R BrilliantTiger/token-pet` → `release not found`. 그래서 `publish` 는 만드는 경로다(`--clobber` 아님).
  - `all` / `ship` / 맨 `./release.sh` 는 절대 실행하지 않는다.

## 게이트 밖의 사실 (관측 그대로)

### Apple 공증 — 계약
- 2026-11-18T04:16:23Z, 조정자 실행(읽기 전용, 제출 없음): `xcrun notarytool history --keychain-profile claudepet-notary` → exit 1:
  `Error: HTTP status code: 403. A required agreement is missing or has expired. This request requires an in-effect agreement that has not been signed or has expired. Ensure your team has signed the necessary legal agreements and that they are not expired.`
- 메인 세션이 전한 말: 사용자가 방금 Apple 계약을 받아들였고, 메인 세션의 마지막 확인에서는 아직 403 이었다(전파 중).
- 2026-11-18T04:21:47Z, 조정자가 같은 명령을 다시 실행 → exit 0, `Successfully received submission history.`, 맨 위 항목은
  2026-10-17T12:46:04Z `ClaudePet-universal.dmg` `Accepted`(v1.1.1). 지금은 거부하지 않는다.
- 운영자의 `notarize`·`universal`·`dmg` 는 공증 제출을 거치므로 이 명령이 403 없이 돌아오는 것이 전제다. 운영자는 시작 전에 다시
  확인하고 결과를 기록한다(항목 5). 계약은 계정 소유자만 다룰 수 있고, 에이전트가 풀 일이 아니다.

### Windows 산출물
- GitHub Actions 의 PC 러너는 꺼져 있다: 2026-11-18T04:16:24Z `gh api orgs/BrilliantTiger/actions/runners` → `token-pet-win-1`
  (Windows, X64) `status=offline`. 이번 빌드는 러너가 아니라 Orca 환경 "windows"(id `ff301039-54a9-4313-9857-f4057ffb1cf3`)로
  같은 사용자 PC 에 닿아 만들었다.
- **빌드 세션:** 메인 세션 pill-width-dev 가 그 PC 의 Orca 터미널로 돌렸다(그래서 운영자 자격이 없다, 항목 5). 전달받은 절차:
  워크트리 `C:/Users/yeongyu/orca/workspaces/claude-pet/rel112-win` 에서 `git checkout --detach ea8922d91dbcb177a20dcbc6b0f61cdcda08e8ae`,
  Python 3.13.15 venv 에 `pip install -r windows\requirements.txt`, `python -m unittest discover -s windows/tests -t .`(exit 0),
  `PYTHONUTF8=1`·`CLAUDE_PET_WIN_SIGN=off` 로 `python windows\build_win.py`(exit 0).
- **조정자가 직접 확인한 것**(같은 Orca 환경에 조정자 전용 터미널을 따로 열어 읽기 명령만 돌리고 닫았다, 2026-11-18, 두 산출물의 수정 시각 뒤):
  - `git log -1` = `ea8922d91dbcb177a20dcbc6b0f61cdcda08e8ae Merge pull request #12 from BrilliantTiger/dev`; `git status --porcelain` 은
    `?? winbuild.log`, `?? wintest.log` 뿐(추적 파일 수정 없음).
  - `.venv\pyvenv.cfg`: `version = 3.13.15`.
  - `wintest.log`: `Ran 271 tests in 2.559s` / `OK`.
  - `winbuild.log`: `ClaudePet v1.1.2 — Windows onedir 빌드`, `서명 없음 (CLAUDE_PET_WIN_SIGN=off)` 두 줄(ClaudePet.exe,
    claude-pet-win-setup.exe), `✅ 배포물 게이트 통과 (zip 멤버·레이아웃·버전 마커, 설치 파일 존재·크기)`.
  - 산출물(`release\` 아래, `Get-FileHash -Algorithm SHA256`), 전달받은 값과 같다:
    - `claude-pet-win.zip` 72,630,325 바이트, `99344d1522cbe3ba0df817b6ed5d1cf5b3c1e173abeb3f3dce9a5980c5b9e720` (수정 2026-11-18T04:17:38Z)
    - `claude-pet-win-setup.exe` 56,154,776 바이트, `75eef85fbda9a7c6490f1dff078ed19cec82dec7e043b48347092ec4eb87dc38` (수정 2026-11-18T04:17:58Z)
- **올리기:** 운영자가 `publish` 로 v1.1.2 릴리즈를 만든 뒤, 올릴 파일을 다시 해시해 위 값과 같은지 기록하고 같은 릴리즈에 올린다:
  `gh release upload v1.1.2 claude-pet-win.zip claude-pet-win-setup.exe -R BrilliantTiger/token-pet` (`--clobber` 없음).
  Windows 터미널의 `gh` 로 올리든 Mac 으로 복사해 올리든, 해시 확인은 올리는 쪽의 파일로 한다. 해시가 다르면 올리지 않고 멈춘다.
- **올라가기 전까지의 결과**(코드에서 확인, `ea8922d`): 설치된 Windows 판은 `releases/latest` 의 태그 1.1.2 가 더 새롭다고 본 뒤
  (`check_github_update_win` 은 버전을 먼저 비교한다) 자산을 고른다. `UPDATE_ASSET_NAMES_WIN` 의 `("AMD64","inno")` →
  `claude-pet-win-setup.exe`, `("AMD64","portable")` → `claude-pet-win.zip` 이 릴리즈에 없으면 `select_update_asset_win` 이
  `(None, "missing-asset")` 을 돌려주고 확인 결과는 `("error", "missing-asset")` 이다. `missing-asset` 은 일시적 이유
  (`bad-payload`, `fetch-failed:*`)가 아니므로 `stamps_cooldown` 이 참이고, `_run_update_check` 가 `_upd_cache["t"]` 를 찍어
  `UPDATE_CHECK_SEC`(3600초) 뒤에 다시 묻는다. 즉 publish 와 Windows 업로드 사이에는 설치된 Windows 판이 업데이트를 찾지 못하고
  한 시간마다 다시 확인하며, 우클릭 '업데이트 확인…' 은 `upd_failed`("업데이트를 확인하지 못했습니다. 잠시 후 다시 시도하세요.")를
  보여준다. 자산이 올라간 뒤의 다음 확인에서 받는다. 그래서 운영자는 publish 바로 다음에 Windows 자산을 올린다.
