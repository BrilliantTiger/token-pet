# v1.2.0 — 실행 게이트, 조정자 판정, 릴리스 운영자 지정

이 릴리스의 조정자 `release-coordinator-v120`(2026-11-19)가 쓴다. 이 릴리스에서 다른 역할은 맡지 않았다.
이 파일 하나가 AGENTS.md §6 항목 1–5 를 v1.2.0 에 대해 채운다. 게이트 조건 밖의 사실(Apple 공증, Windows 산출물)은
맨 아래 "게이트 밖의 사실" 에 관측한 그대로 적는다.

**판정을 먼저 적는다: 게이트 GREEN (`0707dee`).** 조정자의 첫 판정은 "아직 GREEN 이 아니다" 였고(검토자 서명이 없는 변경), 그 서명이 채워진 뒤 GREEN 으로 고쳤다 — 경과는 항목 1 과 4 에 있다.

## 무엇을 릴리스하나
- **릴리스할 커밋: main `0707deeaedba921aa0f0c6e8a0f33ffdb9e404a6`** (PR #15, dev → main 머지, 2026-11-19T05:52:07Z).
  트리 `95d7443211fae7b372649fdc3947af1a6e5611c7` 는 dev `ed84aed`, PR #17 의 끝 `20196e6` 과 같다(`git rev-parse <c>^{tree}` 셋 다 같은 값).
  - 바탕: 태그 `v1.1.2` → `ea8922d`. `git log --no-merges v1.1.2..0707dee` 는 36 커밋, 머지 커밋은 다섯.
  - PR #13 → dev `e4d9901` (TOK-44, TOK-47): macOS Gemini(Antigravity) 사용량 — `agy -p /usage` 읽기, 로그인 확인, 브라우저 막기.
    13 커밋 `bda5759`…`d1e52c8`.
  - PR #14 → dev `1f51bc6` (TOK-43): `01cbb2a`(릴리스 계약), **`e12bc8d` "release: ClaudePet v1.2.0"**(APP_VERSION 1.2.0,
    RELEASE_NOTES v1.2.0, `verify_release_artifact.py` 사용 예, CLAUDE.md), `d793135`(핀), `cddc332`(노트·문서 검토 반영).
  - PR #16 → dev `a494274` (TOK-57): `2ce8dd5` — `tests.yml` 이 main push 에서도 돈다.
  - PR #17 → dev `ed84aed` (TOK-48, TOK-50~54, TOK-55, TOK-59, TOK-43): Windows Gemini 읽기(`23aa7da`), 설정 창 "AI 연결"에서
    세 CLI 설치·로그인(`6601c24`), v8 수정(`3115ff5`), 문서(`eaab3f4`, `4892d9f`, `90c6138`), **v1.2.0 노트 다시 씀(`2eaa903`)**,
    업데이트 확인 저장소 이름(`c3224e1`: `GITHUB_REPO = "BrilliantTiger/token-pet"`, `windows/installer.iss` 링크 두 줄), 테스트·핀 열 커밋.
  - **버전을 올린 커밋 `e12bc8d` 뒤에 제품 변경이 더 들어갔다**(PR #16, #17 — `claude_pet.py`, `windows/claude_pet_win.py`,
    `windows/installer.iss`, `RELEASE_NOTES.md`). `APP_VERSION` 은 `e12bc8d` 부터 `0707dee` 까지 `"1.2.0"` 그대로다. 이 게이트는
    `e12bc8d` 가 아니라 `0707dee` 의 트리 전체를 판정한다. PR #15 본문은 PR #13·#14 만 적고 있어 실제 내용(#16·#17 포함)보다 좁다.
  - `git diff --stat v1.1.2 0707dee`: 25 파일, +10412 −398. 그중 `windows/` 8 파일 +683 −80 — 이번에는 Windows 판 코드가 바뀐다.
- **이 기록 커밋은 `tok-43-release-v1.2.0-gate` 브랜치에만 있다.** 바탕은 `0707dee` 이고 `docs-design/` 의 이 문서 하나만 더한다.
  main·dev 에 올리지 않았고 PR 도 열지 않았다. 태그는 이 커밋이 아니라 `0707dee` 에 단다(항목 5).

## 사용자 승인 — 원문 그대로
조정자는 사용자의 말을 직접 듣지 않았다. 메인 세션의 브리프(`briefs/rel120-gate-coordinator.md`)가 "사용자가 메인 세션에 직접 침"
이라며 전한 일곱 줄과, 조정자의 질문에 메인 세션이 더 전한 두 줄(8·9, 아래)이다. 조정자는 승인을 주지 않고(§6 가드 4), 범위를 넓히지 않고 글자대로 적는다.

1. "잼미니 구현 빨리 끝내고 릴리즈해 그리고 버전 관리는 이제 major, minor, fix/build 이렇게 가자 이 버전 규칙은 너가 정하고"
2. 질문 답 "1.2.0은 Antigravity만, API 키는 다음"
3. "그럼 어여 수정해!"
4. 질문 답 "1.2.0에 Windows도 넣기 (추천)"
5. "gemini, codex, claude code 모두 cli가 설치 안되어잇음 설치 가능하게 해놔야지 사람이 설정에서 설치 버튼 누르면 알아서 설치되게끔 그리고 로그인까지 마무리 시켜야지"
6. "이슈 없으면 너가 하면 되지 뭘 나한테 시키지?"
7. "빌드랑 서명 공증 최대 20분 안넘기는데?"

- **git·PR 에 이미 있는 것:** 1–3 은 `e12bc8d` 메시지와 PR #14·#15 본문에, 4·5 는 PR #17 본문에 있다(4 는 "(추천)" 없이
  "1.2.0에 Windows도 넣기"). **6·7 은 이 기록 전에는 git·PR 어디에도 없다**(`e12bc8d` 메시지와 PR #13–#17 본문을 읽어 확인).
  이 기록이 처음 남기는 곳이다.
- **글자대로 읽으면:**
  - 1 은 Gemini 구현을 끝낸 뒤의 릴리스를 시킨다("릴리즈해"). 이 저장소에서 릴리스는 CLAUDE.md "Release procedure" 의 순서
    (빌드·서명·공증·태그·push·게시)이고, 조정자는 이를 그 순서 전체에 대한 일괄 승인(AGENTS §6)으로 읽는다. 1 이 나온 때의 범위는
    2 가 정한 대로 macOS Antigravity 였고, 4·5 가 같은 1.2.0 에 Windows Gemini 와 CLI 설치·로그인을 넣으라고 했다.
  - 6·7 은 문장만으로는 무엇에 대한 말인지 정해지지 않는다. 조정자가 메인 세션에 물었고, 메인 세션이 맥락을 이렇게 전했다
    (2026-11-19, 사용자가 아니라 메인 세션의 말이다):
    - 6 은 메인 세션이 "PR #15(dev→main) 머지는 대표님 몫" 이라고 적은 표에 대한 답이다 — 머지를 메인 세션이 하라는 뜻.
      서명·공증에 관한 말이 아니다.
    - 7 은 메인 세션이 적은 "7. Windows 빌드, 서명·공증·게시 1시간~1시간 반" 에 대한 답이다 — 그 단계가 그렇게 오래 걸리지
      않는다는 말.
  - 메인 세션은 그 뒤에 사용자가 친 두 문장을 원문으로 더 전했다:
    8. "그래서 릴리즈 했어?"
    9. "서버 공증이랑 등등 다?"
    8·9 도 이 기록 전에는 git·PR 어디에도 없다.
  - 그래서 `[ASK-OP]`(서명·공증)와 `[ASK]`(push·게시)의 근거는 1 의 "릴리즈해" 다. 7·8·9 는 사용자가 "서명·공증·게시" 가 적힌
    계획을 보고 그 단계를 막지 않고 더 빨리 하라고 했으며, 그 뒤 릴리스와 공증이 끝났는지를 물었다는 것을 보여 준다. 셋 다
    묻는 문장이고, v1.1.2 때의 "서명·공증·게시까지 다 진행해" 처럼 단계를 하나하나 시킨 문장은 이번에는 없다. 조정자는 1 과
    7·8·9 를 함께 읽어 릴리스 순서 전체에 대한 일괄 승인이 있다고 본다. 6 은 PR #15 머지에 대한 것으로, 이미 끝난 일이다.
  - 이 말들은 게이트를 바꾸지 않고, 자격 없는 에이전트를 `[ASK-OP]` 단계에 자격 있게 만들지도 않는다.
- **조정자가 받은 아홉 줄에 없는 결정 셋**(브리프·PR 본문에 메인 세션이 전한 말로만 있다): TOK-59 "이건 당장 해야하는거 아니냐?"
  (`briefs/repo-name-now.md`), TOK-57 선택지 "tests.yml에 main 추가 (추천)"(`briefs/tok57-ci.md`, PR #16), Gemini 로그인
  "그냥 가이드하면 되지" / "터미널창 띄워두고"(PR #17). 셋 다 구현 범위에 관한 말이고 릴리스 단계 승인이 아니다.

## 항목 1 — §8 조건 (릴리스 전체)
- **트레일러(§8-1):** 머지가 아닌 36 커밋 모두 `Developer:` / `Verifier:` 가 있고 서로 다르다
  (`git log --no-merges --format='%h %(trailers:key=Developer,valueonly) %(trailers:key=Verifier,valueonly)' v1.1.2..0707dee`).
  - `bda5759`…`90fd32b` 여섯: 테스트 커밋은 Developer gemini-agy-tests / Verifier gemini-dev, 제품 커밋은 그 반대.
  - `68280ce` 부터 서른: 테스트 커밋은 Developer gemini-tests-v2 / Verifier gemini-dev-v2, 제품·문서·CI 커밋은 그 반대.
  - 머지 커밋 다섯(`e4d9901`, `1f51bc6`, `a494274`, `ed84aed`, `0707dee`)은 GitHub PR 머지라 트레일러가 없고 내용을 더하지 않는다 —
    각각 둘째 부모(`d1e52c8`, `cddc332`, `2ce8dd5`, `20196e6`, `ed84aed`)와의 `git diff --stat` 이 출력 없음.
- **분리(§8-2, Condition B), `git log --name-only` 로 확인:** 테스트 커밋 열아홉은 `tests/` 와 `windows/tests/` 만 건드린다.
  나머지 열일곱(Developer 쪽)은 `claude_pet.py`, `windows/claude_pet_win.py`, `windows/win_update.py`, `windows/installer.iss`,
  `logos/gemini.svg`, `verify_release_artifact.py`, `RELEASE_NOTES.md`, `CLAUDE.md`, `.github/workflows/tests.yml` 만 건드린다.
  두 집합은 겹치지 않는다. (`23aa7da` 는 제품 파일과 함께 `tests.yml` 을 고쳤다 — 워크플로는 `tests/` 가 아니다.)
- **먼저 빨강(§8-3):** 기록은 `/Users/yeongyu/claude-pet-wt/` 의 `red-run-*.txt` 와 `briefs/*-REPORT.md` 다. 조정자는 각 파일의
  `Ran …` / `FAILED …` 줄을 읽었고, 다시 돌리지는 않았다. `failures` 는 subTest 까지 센 수라 `Ran` 보다 클 수 있다.

  | 테스트 커밋 | 기록 | 기록된 빨강 |
  | --- | --- | --- |
  | `bda5759` | `red-run-gemini.txt` | `Ran 32` / `FAILED (failures=90)` |
  | `9d76bf4` | `red-run-gemini-keychain-quiet.txt`(`e5cde29` 의 `claude_pet.py` 사본), `red-run-gemini-pill.txt` | `Ran 8` / `failures=9`, `Ran 8` / `failures=8`; `Ran 24` / `failures=48` |
  | `e1634ae` | `red-run-gemini-round3.txt`, `red-run-gemini-agy-lazy.txt`(둘 다 `8eb4ccb`, `claude_pet.py` sha256 `6d2e4ba9d7edd27e…`) | `Ran 12` / `failures=6`, `Ran 24` / `failures=1`, `Ran 32` / `OK`; `Ran 9` / `failures=3` |
  | `68280ce` | `red-run-gemini-v2.txt`, `red-run-gemini-v3.txt` | `Ran 42` / `failures=43`; `Ran 63` / `failures=39` |
  | `7347417` | `red-run-gemini-v5.txt` | `Ran 67` / `failures=44` |
  | `66f60d6` | `red-run-gemini-v6.txt` | `Ran 68` / `failures=3` |
  | `01cbb2a` | `red-run-rel120.txt` | `Ran 79` / `failures=8` |
  | `33c010d`, `d7ee6bc` | `red-run-v7-W.txt`(HEAD `a494274`, 2026-11-19T01:01Z) | `Ran 87` / `failures=21`; `Ran 10` / `failures=9` |
  | `3376ef9` | `red-run-v7-I.txt`(`a494274` 의 사본, 02:27Z) | `Ran 42` / `failures=91`; `Ran 4` / `8`; `Ran 2` / `1`; `Ran 5` / `2`; `Ran 2` / `2` |
  | `144d668` | `red-run-v8.txt`(`eaab3f4` 워크트리, 03:50Z) | `Ran 18` / `failures=29`; `Ran 2` / `6`; `Ran 2` / `1`; `Ran 2` / `1` |
  | `c35671b` | `briefs/v8-notes-verifier-REPORT.md` | `Ran 81` / `FAILED (failures=3)` — 실패 출력 전문은 보고에 없고 요약 줄만 있다 |
  | `2c11c94` | `red-run-v8-ci-fix.txt`(HEAD `2eaa903`, 05:02Z), CI run 44460979904(`2eaa903`, macOS failure) | `Ran 1` / `failures=1` → 고친 뒤 `OK` |
  | `2fc7548` | `briefs/repo-now-verifier-REPORT.md`(HEAD `2c11c94`) | `Ran 5` / `failures=4`; `Ran 8` / `failures=6`; `Ran 81` / `failures=1` — 요약 줄만 |
  | 핀 다섯(`d1e52c8`, `d793135`, `15de295`, `63b8ddc`, `20196e6`) | — | 소스 해시 핀 하네스는 바뀐 소스를 거부하므로 핀 갱신이 곧 빨강→초록이다 |

  - 앞의 여섯 파일(`red-run-gemini*.txt` 중 `…-v2`, `-v3`, `-v5`, `-v6`, `red-run-gemini.txt`, `-pill`)과 `red-run-rel120.txt` 에는
    어느 커밋에서 돌렸는지 적은 머리 줄이 없다. 대상 커밋은 PR #13·#14 본문과 보고서가 전한 것이다.
  - `2ce8dd5`(TOK-57)는 동작 변경이 아니라 CI 설정이고 이를 읽는 테스트가 없다. 빨강 기록이 없고, Verifier 는 diff 와 YAML 파싱을
    확인했다(`briefs/tok57-ver-REPORT.md`).
- **검토자(§8-4):** `gemini-agy-review`(Gemini/agy, 읽기 전용; 보고 `briefs/agy-*-review-REPORT.md`)와, 마지막 변경에 대해
  `release-reviewer-v120`(Claude, 독립; 보고 `briefs/rel120-final-review-REPORT.md`).

  | 검토 | 대상 | 판정 |
  | --- | --- | --- |
  | `agy-final-review` | `a9a330b..63d5420` | 승인 불가(미로그인 `agy` 가 timeout 으로 빠짐) → v5·v6 에서 고침 |
  | `agy-v6-review` | `a9a330b..9c3a021` (PR #13 의 제품 diff 전부) | **승인** |
  | `agy-rel120-review` | `e12bc8d` | 수정 필요(노트 첫 줄 한 곳) → `cddc332` 에 제안 문장대로 반영. 반영 뒤의 재확인 기록은 없다 |
  | `agy-v7-review` | `a494274..6601c24` | 수정 필요(B1–B5) |
  | `agy-v8-review` | `6601c24..4892d9f` | **승인** |
  | `rel120-final-review` (`release-reviewer-v120`) | `4892d9f..0707dee`, `1f51bc6..2ce8dd5` | **승인** |

  - **마지막 변경의 검토.** `agy-v8-review` 의 범위는 `4892d9f` 에서 끝난다. 그 뒤의 `63b8ddc`, `90c6138`, `c35671b`, `2eaa903`,
    `2c11c94`, `2fc7548`, `c3224e1`, `20196e6` 과 범위 밖이던 `2ce8dd5`(TOK-57)에는 조정자가 처음 볼 때 검토자의 서명이 어디에도
    없었다(`briefs/agy-*REPORT.md` 에 이 해시들과 `token-pet` 이 나오지 않았고, PR #15·#16·#17 은 리뷰·댓글 0, PR #17 본문의 리뷰
    절은 v7→v8 만 적는다). `git diff 4892d9f 0707dee --stat` 은 10 파일 +266 −66 이고, 테스트가 아닌 것은 `RELEASE_NOTES.md`
    (v1.2.0 절 전체를 다시 씀, `2eaa903` — 문구는 Verifier 의 초안을 Developer 가 그대로 커밋했다고 `briefs/v8-notes-dev-REPORT.md`
    가 적는다), `claude_pet.py` 한 줄(`GITHUB_REPO`, `c3224e1`), `windows/installer.iss` 두 줄, `CLAUDE.md` 11 줄(추가·삭제 합)이다.
  - **그 서명은 `release-reviewer-v120` 이 채웠다**(Claude, 이 검토 하나를 위해 만든 독립 세션; 개발자·검증자가 아니다).
    보고 `briefs/rel120-final-review-REPORT.md`(sha256 `017bfc18ae2206ffa03ea53032ff5f0c9c46764f694ad6cee556d032022e8918`), 조정자가 직접 읽었다.
    **판정: 승인(두 diff 모두), 수정 필요 항목 없음.** 그 보고가 적은 것:
    - 노트 일곱 문장을 `0707dee` 소스와 대조해 모두 맞음.
    - 저장소 이름: `api.github.com/repos/BrilliantTiger/token-pet/releases/latest` → 200, `v1.1.2`, 자산 6개; 옛 이름 둘은 301 로
      같은 릴리스에 닿음. 자산 선택은 이름 표와 호스트만 보고 저장소 경로를 보지 않음.
    - 테스트: `2c11c94` 의 `_find_agy_cli` 대역은 게이트를 약하게 하지 않음. `c35671b` 는 세 군데가 느슨해졌고 모두 노트 내용이
      바뀐 데 따른 것이며 새 게이트가 더해짐 — "받아들일 만하다". 핀 값은 `claude_pet.py` 의 실제 sha256 `3b009f6e…ef67bb` 와 같음.
    - `tests.yml`: 워크플로에 배포·서명·게시 단계가 없어 main push 에서 도는 것은 테스트뿐.
    - 실행: 바뀐 테스트 파일 다섯 → 199 OK, `windows/tests/test_win_repo_move.py` → 8 OK(`0707dee` 를 `git archive` 로 푼 사본).
    - 그 검토자가 확인 못 했다고 적은 것: 전체 스위트, Windows 실기기, 로그아웃 상태의 실제 `agy`, README·`docs/` 의 옛 링크.
  - 검토자가 바뀐 까닭: 메인 세션이 전하기를, 사용자 지시로 Gemini(agy)는 사용량 읽기 검증만 맡고 마지막 변경의 검토는 Claude 의
    독립 검토자에게 맡겼다. 조정자는 그 지시의 원문을 받지 못했다.
  - 조정자가 따로 본 것: `c3224e1` 의 제품 변경은 위 세 줄뿐이다. `gh repo view BrilliantTiger/token-pet` 은 그 이름의 저장소를
    돌려주고 `gh release list -R BrilliantTiger/token-pet` 의 Latest 는 v1.1.2 다. `2ce8dd5` 는 `branches` 한 줄과 주석 넷이다.
- **전체 스위트 초록(§8-5):** 항목 2.
- **추적되지 않은 파일(§8-6):** 조정자는 이 기록 외에 아무것도 더하거나 지우지 않았다. 워크트리는
  `git worktree add /Users/yeongyu/claude-pet-wt/rel120-gate -b tok-43-release-v1.2.0-gate origin/main` 으로 새로 만들었고, 메인 체크아웃과
  다른 워크트리는 읽기만 했다. Windows PC 에서는 조정자 전용 터미널을 따로 열어 읽기 명령과 배포물 검증기만 돌리고 닫았다(아래).
- **§5(§8-7):** PR #13 본문의 "Gemini 67개 중 26개 실패", "68개 중 3개 실패" 는 `red-run-gemini-v5.txt`(`failures=44`)·`-v6.txt`
  (`failures=3`)와 세는 단위가 다르다(테스트 수와 subTest 실패 수). PR #17 본문의 "받기 2.3s", "61%" 는 실기기 한 번의 관측으로
  전해졌고 표본 크기와 시각이 본문에 없다. 릴리스 노트에는 버전 말고 숫자가 없다.

## 항목 2 — 깨끗한 트리에서 전체 스위트
- 조정자 worktree `/Users/yeongyu/claude-pet-wt/rel120-gate`, HEAD `0707dee`, `git status --porcelain` 출력 없음
  (실행 전 2026-11-19T05:53:18Z 에 확인; 실행 뒤 05:59:19Z 에는 그 사이 조정자가 쓴 이 문서 `?? docs-design/release-v120-gate-20261119.md` 한 줄뿐 — 추적 파일 변경 없음). Python 3.13.7(python.org, PyObjC 12.2.1). 저장소 루트에서:
  - `python3 -m unittest discover -s tests` → `Ran 1240 tests in 358.139s` / `OK (skipped=8)`, exit 0
  - `python3 -m unittest discover -s windows/tests -t .` → `Ran 289 tests in 1.626s` / `OK (skipped=23)`, exit 0
- 검증자 gemini-tests-v2 의 결과(`briefs/repo-now-done-REPORT.md`, `20196e6` 의 내용을 커밋하기 직전 워킹 트리): `Ran 1240 tests in 358.878s` /
  `OK (skipped=8)`, `Ran 289 tests in 1.635s` / `OK (skipped=23)`. `20196e6` 의 트리는 `0707dee` 와 같다. **검증자가 `0707dee` 의
  깨끗한 트리에서 다시 돌린 기록은 없다** — §6 항목 2 는 그 재실행을 검증자에게 맡긴다. 위의 깨끗한 트리 실행은 조정자가 한 것이다
  (v1.1.2 기록과 같은 방식).
- CI (`gh run view <id> -R BrilliantTiger/token-pet` 로 확인):

  | run | 대상 | 이벤트 | 결과 |
  | --- | --- | --- | --- |
  | 44273714554 | `d1e52c8` (PR #13 브랜치) | workflow_dispatch | macOS·Windows success |
  | 44281683887 | `cddc332` (PR #14 브랜치) | workflow_dispatch | macOS·Windows success |
  | 44428348923 | `2ce8dd5` (PR #16 브랜치) | workflow_dispatch | macOS·Windows success |
  | 44430517881 | dev `a494274` | push | success |
  | 44460979904 | `2eaa903` | workflow_dispatch | macOS failure(로컬 `agy` 에 기댄 테스트 하나 → `2c11c94`), Windows success |
  | 44465345864 | `20196e6` (PR #17 브랜치) | workflow_dispatch | macOS·Windows success |
  | 44466229786 | PR #17 (`20196e6`) | pull_request | success |
  | 44467043189 | dev `ed84aed` | push | success |
  | 44467048006 | PR #15 (`ed84aed`) | pull_request | success |
  | 44468100335 | **main `0707dee`** | push | macOS — full suite success, Windows — gating contract success (2026-11-19T05:59:51Z 확인) |
  | 44468099028 | main `0707dee` | dynamic | `pages-build-deployment` success — 테스트 실행이 아니다 |

  44468100335 는 TOK-57 덕분에 main 의 머지 커밋에서 처음으로 도는 `tests` 실행이다. CI 의 Windows 작업은 `windows-latest` 의
  게이팅 계약이고, 포트 자체 스위트 단계는 `continue-on-error` 다(v1.1.2 기록에서 확인한 구성; 이번에 다시 읽지 않았다).
- 이 기록 커밋은 `docs-design/` 의 문서 하나만 더하므로 스위트 결과에 영향이 없다.

## 항목 3 — 릴리스 노트
- v1.2.0 절(`0707dee`):
  ```
  **v1.2.0**

  - 설정 창 "AI 연결"에서 Claude Code·Codex·Gemini CLI를 [설치] 한 번으로 받고 로그인 창까지 이어집니다. 공식 서버에서 받아 서명을 확인한 뒤 앱 전용 폴더에 두고 PATH는 바꾸지 않습니다.
  - Gemini (Antigravity) 사용량을 macOS와 Windows 필에 표시합니다. 로그인하지 않았으면 표시하지 않고, 앱이 브라우저를 멋대로 열지 않습니다.
  - Gemini 로그인은 열린 창에 브라우저에서 받은 코드를 붙여 넣으면 끝납니다. Gemini를 API 키로 보는 방식은 아직 없습니다.
  ```
- 형식: 최상위 불릿 3개, 중첩 0, 불릿마다 2 문장. 공백 정규화 길이는 조정자가 재어 297자(머리 `**v1.2.0**` 를 넣으면 308자 —
  Developer 보고의 308 과 같다), 한도 450. 해시·소스 경로·테스트 언급 없음. 크기·빈도의 모호한 표현 없음. 숫자는 버전뿐.
  `tests/test_v1_2_0_release_contract.py` 의 노트 형식·내용 테스트가 이를 묶고, 항목 2 의 스위트에 들어 있다.
- **노트가 말하는 것 가운데 실기기로 본 것과 보지 않은 것**(항목 4 의 "확인하지 못한 것" 과 같다): "[설치] 한 번으로 받고" 는
  Codex 에 대해서만 실기기(이 Mac, Windows 11)에서 실제로 받았다고 전해졌다. Claude Code 와 Gemini CLI 를 앱에서 받는 것,
  설치에서 로그인 완료까지 이어지는 것은 코드와 테스트로만 확인됐다(`briefs/v8-notes-dev-REPORT.md` 가 같은 점을 적는다).
- 이 문구(`2eaa903`)는 `release-reviewer-v120` 이 `0707dee` 의 소스와 문장마다 대조해 "과장·틀린 문장은 찾지 못했다" 고 적었다
  (항목 1 의 검토자 표 마지막 줄). 그 검토자가 잰 길이는 298자다(조정자 297 — 세는 방법의 차이, 둘 다 한도 안).
- v1.1.2 는 published(태그 `v1.1.2` → `ea8922d`, GitHub 릴리스 "ClaudePet v1.1.2" Latest, 2026-11-18T04:33:06Z). 태그의
  `RELEASE_NOTES.md` 에서 `**v1.1.2**` 부터 끝까지가 `0707dee` 의 같은 부분과 바이트 단위로 같다(24628 바이트, sha256
  `88a9cdf2…5e9c`). `**v1.2.0**` 위의 머리말도 같다. 게시된 절은 한 글자도 바뀌지 않았다.
- `git ls-remote --tags origin 'v1.2.0*'` 출력 없음, `gh release view v1.2.0 -R BrilliantTiger/token-pet` → `release not found`
  (2026-11-19 조정자 확인). v1.2.0 절은 아직 게시되지 않은 staged 상태다.

## 항목 4 — 조정자 판정
- **인증:** v1.2.0(`0707dee`)을 실행 단계에 들어가도 된다고 인증한다. **게이트: GREEN.**
  - §8-1 트레일러, §8-2 분리, §8-3 먼저 빨강(위 표의 단서와 함께), §8-4 검토자(위 표 — 마지막 줄은 조정자의 첫 판정 뒤에 채워졌다),
    §8-5·항목 2 스위트(깨끗한 트리 1240 OK / 289 OK), §8-6, §8-7, 항목 3 노트, 항목 5 운영자 지정.
  - **경과.** 조정자의 첫 판정(2026-11-19, 스위트 실행 뒤)은 "아직 GREEN 이 아니다" 였다 — `4892d9f` 뒤의 변경과 `2ce8dd5` 에
    검토자 서명이 없었다. 조정자가 이를 메인 세션에 알렸고, `release-reviewer-v120` 이 두 diff 를 검토해 승인했다
    (`briefs/rel120-final-review-REPORT.md`). 그 보고를 조정자가 직접 읽고 판정을 GREEN 으로 고쳤다. 릴리스할 커밋은 그 사이
    바뀌지 않았다(`0707dee`).
- GREEN 은 항목 1–5 에 대한 판정이다. 운영자 단계가 성공한다는 예측이 아니고, 승인을 주는 것도 아니다 — 승인은 "사용자 승인" 절의
  사용자 말이고, 조정자는 그것을 전달받아 적었을 뿐이다.
- **실기기**(PR #17 본문과 메인 세션이 전한 것. 조정자가 직접 본 것은 "게이트 밖의 사실"의 Windows 산출물뿐이다):
  - 이 Mac: Gemini 읽기(백그라운드 env), Codex 를 앱 경로로 실제 받기(0.170.0, OpenAI 서명, PATH·셸 무변경), 설정 창 스크린샷
    (`/Users/yeongyu/claude-pet-wt/shots/v7-ai-connect-{ko,en}.png`, `v8-ai-connect-{ko,en}.png` — 파일이 있음을 확인).
  - Windows 11: `agy` 로그인 뒤 Gemini 읽기, 소스 앱 설정 창, Codex [설치] 실제 실행(Authenticode Valid, PATH 무변경, 로그인 창, [취소]).
- **확인하지 못한 것:**
  - Developer ID 서명·공증된 v1.2.0 번들의 실제 Mac 실행(운영자가 빌드한 뒤에야 존재한다). 번들의 짧은 `PATH` 에서의 `agy` 실행은
    검토자가 최소 `PATH` 로 흉내 낸 한 번(`agy-v6-review`)이 전부다.
  - 위 실기기 항목 전부 — 전달받았다. 어느 커밋에서 돌렸는지도 조정자는 모른다(v8 수정 `3115ff5` 전인지 뒤인지 포함).
  - 실기기에서 Claude Code·Gemini CLI 를 앱으로 받는 것, 세 CLI 의 로그인 완료, 로그아웃 상태의 실제 `agy` 가 가짜 `open` 에서 멈추는 것.
  - 진짜 네트워크로 `BrilliantTiger/token-pet` 에 업데이트 확인을 보내는 것(테스트는 요청 URL 만 본다). v1.2.0 이 게시된 뒤
    설치된 v1.1.2 사본(상수가 옛 이름 `BrilliantTiger/claude-pet`)이 301 을 따라 v1.2.0 을 받는 것.
  - `0707dee` 트리에서 Windows 포트 스위트를 실제 Windows 에서 돌린 결과. PC 의 `wintest.log` 는 v1.1.2 때의 것이다(아래).
  - 검토자 보고의 원문은 파일로 읽었다. 사용자 승인 아홉 줄, 6·7 의 맥락, 검토자를 바꾸라는 지시는 전달받았다.

## 항목 5 — 릴리스 운영자
- **자격 없음:** 조정자 release-coordinator-v120(이 기록의 작성자); gemini-dev-v2, gemini-dev(개발자); gemini-tests-v2,
  gemini-agy-tests(검증자); gemini-agy-review(검토자 — `agy-*-consult` 로 설계 상담도 했다); release-reviewer-v120(마지막 변경의 검토자); 메인 세션(브리프를 쓰고 머지를 정한
  일상 조정자이며 Windows 산출물 해시를 확인했다); Windows PC 에서 v1.2.0 을 빌드한 세션; TOK-58(사이트) 세션. 이전 릴리스의
  운영자(release-operator-v111, -v112)도 다시 쓰지 않는다.
- **지정 운영자:** `release-operator-v120`. 이 일 하나만을 위해 새로 만든다. 이 릴리스에서 개발자·검증자·검토자·조정자
  어느 역할도 맡지 않았다.
  - **시작 조건:** 이 문서가 GREEN 판정으로 `tok-43-release-v1.2.0-gate` 에 커밋된 뒤에만 시작한다. 운영자는 그 커밋의 이 파일을 직접 읽는다.
  - 작업 트리: `0707deeaedba921aa0f0c6e8a0f33ffdb9e404a6` 에서 만든 워크트리(이 기록 브랜치가 아니다). 시작 전에 `git rev-parse HEAD`
    = `0707deea…` 와 `git status --porcelain` 에 추적 파일 변경이 없음을 기록한다. 운영자 기록 문서는 빌드·서명이 끝난 뒤에 더한다.
  - 시작 전 확인(읽기 전용): 가장 새 태그가 `v1.1.2`, `v1.2.0` 태그·릴리스 없음, `xcrun notarytool history --keychain-profile
    claudepet-notary` 가 exit 0. 하나라도 다르면 `./release.sh build` 도 시작하지 않고 멈춰 넘긴다.
  - 하나씩, 단계마다 결과를 기록하고 첫 실패에서 멈춘다: `./release.sh build`, `sign`, `notarize`, `universal`, `dmg`,
    그다음 태그 `v1.2.0` 을 `0707dee` 에 만들어 그 태그만 push, 그다음 `./release.sh publish`, 그다음 Windows 자산 둘 업로드(아래).
  - **태그는 main 의 `0707dee` 에 단다. 이 기록 커밋에 달지 않는다.**
  - `publish` 는 만드는 경로다(`--clobber` 아님) — 위에 적은 대로 v1.2.0 릴리스가 없다. 릴리스 대상 저장소는
    `BrilliantTiger/token-pet` 이다(`GITHUB_REPO`).
  - `all` / `ship` / 맨 `./release.sh` 는 절대 실행하지 않는다. 브랜치 push, main·dev 변경, 다른 버전은 범위 밖이다.

## 게이트 밖의 사실 (관측 그대로)

### Apple 공증
- 2026-11-19T05:57:08Z, 조정자 실행(읽기 전용, 제출 없음): `xcrun notarytool history --keychain-profile claudepet-notary` → exit 0,
  `Successfully received submission history.`, 맨 위 항목은 2026-11-18T04:31:09Z `ClaudePet-universal.dmg` `Accepted`(v1.1.2).
- 운영자는 시작 전에 다시 확인하고 결과를 기록한다(항목 5).

### Windows 산출물
- GitHub Actions 의 PC 러너는 꺼져 있다: 2026-11-19T05:57Z `gh api orgs/BrilliantTiger/actions/runners` → `token-pet-win-1`
  (Windows) `offline`. 빌드는 Orca 환경 "windows" 로 같은 사용자 PC 에 닿아 만들었다고 전해졌다(`briefs/rel120-win-build-REPORT.md`:
  Windows 11 Pro 10.0.26200 AMD64, `build_win.py` 종료 0, `CLAUDE_PET_WIN_SIGN=off`).
- **조정자가 직접 확인한 것**(같은 Orca 환경, 워크트리 `C:/Users/yeongyu/orca/workspaces/claude-pet/rel112-win` 에 조정자 전용
  pwsh 터미널을 열어 아래만 돌리고 닫았다, 2026-11-19):
  - `git log -1 --format=%H` = `20196e6ce4a295429c5a502db6c07dd4dbb33473`, `git rev-parse HEAD^{tree}` =
    `95d7443211fae7b372649fdc3947af1a6e5611c7`(= `0707dee` 의 트리). `git status --porcelain` 은 `?? winbuild.log`, `?? wintest.log` 뿐.
  - 산출물(`release\` 아래, `Get-FileHash -Algorithm SHA256`), 전달받은 값과 같다:
    - `claude-pet-win.zip` 72,702,311 바이트, `60622a314a0931629e2b94cb5647ae620803a43b65c3255fa99a938d8d61051d` (수정 2026-11-19T05:28:37Z)
    - `claude-pet-win-setup.exe` 56,221,244 바이트, `f6f6c1adee3319187690d18ee82b9733c5ba47975dcee3339070e6fc9844ceef` (수정 2026-11-19T05:28:54Z)
  - `.\.venv\Scripts\python.exe windows\verify_win_artifact.py --version 1.2.0 --zip release\claude-pet-win.zip --installer
    release\claude-pet-win-setup.exe` → `✅ artifact gate passed`, exit 0. 같은 명령에 `--version 1.1.2` → `❌ zip layout refused:
    release marker version does not match the release tag`, exit 1 — 검증기가 버전 표식을 실제로 가른다. 실행 뒤 `git status` 는 그대로.
  - `Get-AuthenticodeSignature release\claude-pet-win-setup.exe` → `NotSigned`(무서명, 원래대로).
  - **그 폴더의 `winbuild.log`·`wintest.log` 는 v1.1.2 때의 것이다**(`ClaudePet v1.1.2 — Windows onedir 빌드`, `Ran 271 tests in 2.559s`).
    v1.2.0 빌드와 Windows 스위트 실행의 로그는 그 폴더에 없다. 그래서 v1.2.0 빌드의 "종료 0" 과 내장 게이트 통과는 전달받은 것이고,
    조정자가 직접 본 것은 산출물 자체(해시, 1.2.0 표식, 검증기 통과)다.
- **올리기:** 운영자가 `publish` 로 v1.2.0 릴리스를 만든 뒤, 올릴 파일을 다시 해시해 위 값과 같은지 기록하고 같은 릴리스에 올린다:
  `gh release upload v1.2.0 claude-pet-win.zip claude-pet-win-setup.exe -R BrilliantTiger/token-pet` (`--clobber` 없음).
  해시 확인은 올리는 쪽의 파일로 한다. 해시가 다르면 올리지 않고 멈춘다. 게시 뒤 자산이 여섯인지 확인한다.
- **올라가기 전까지:** v1.1.2 기록이 그때의 코드에서 확인한 대로라면 publish 와 Windows 업로드 사이에는 설치된 Windows 판이
  `missing-asset` 으로 업데이트를 찾지 못하고 한 시간 뒤 다시 묻는다. 이번 트리에서 그 코드를 다시 읽지는 않았다. 운영자는
  publish 바로 다음에 Windows 자산을 올린다.
