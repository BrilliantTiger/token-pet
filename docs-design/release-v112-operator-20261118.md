# ClaudePet v1.1.2: 릴리즈 운영자 기록 (`release-operator-v112`)

AGENTS.md §6 항목 5 의 운영자 쪽 기록. 누가 자격 증명이 걸린 단계를 실행했고, 무엇을 실행했고, 무엇이 나왔는지.
단계가 끝날 때마다 결과를 확인하고 다음 단계로 넘어갔다.

**결과:** 2026-11-18T04:25Z~04:37Z, 사전 확인과 ①~⑨ 모두 통과. v1.1.2 가 Latest 로 게시되었고 자산은 6개다.
실패하거나 건너뛴 단계는 없다.

## 자격

**운영자:** `release-operator-v112`. `a492eb3`(게이트 기록·조정자 서명·운영자 지정,
`docs-design/release-v112-gate-20261118.md`) 커밋 뒤에 이 일 하나만을 위해 만든 하위 에이전트.

**이 릴리즈에서 맡은 역할: 없음.** 프로덕션·테스트 파일을 쓰지 않았고, 이 기록 외에 어떤 커밋도 쓰지 않았고,
게이트 기록을 쓰지 않았고, 릴리즈를 인증하지 않았다. 조정자 release-coordinator-v112, pill-width-dev(개발자, Windows 빌드
세션), pill-width-tests(검증자), pill-width-review(검토자), gemini-agy-tests, 그 밖의 Windows 빌드 세션,
release-operator-v111 등 이전 릴리즈의 운영자 어느 것도 아니다.

하지 않은 것: 추적 파일 수정, `all`/`ship`/맨 `./release.sh`, 메인 체크아웃(`/Users/yeongyu/claude-pet`)이나 사용자
미추적 파일 접근, 디렉터리 단위 삭제, `--clobber`, 브랜치를 main·dev 에 푸시. 릴리즈 작업은 모두 `ea8922d` 의 분리
워크트리 `/Users/yeongyu/claude-pet-wt/op112`(detached HEAD)에서 했다. 그 워크트리의 `release/` 에는 처음에 추적 파일
`icon.icns` 하나뿐이었고, `build/`·`dist/`·`dist-universal/` 은 없었다. 지운 것은 `release.sh` 가 자기 산출물을 지우는 것뿐이다.
이 기록은 따로 만든 워크트리 `/Users/yeongyu/claude-pet-wt/op112-record`(브랜치 `tok-42-release-v1.1.2-operator`,
바탕 `a492eb3`)에서 썼다.

## 권한, 직접 읽음

- **게이트:** `docs-design/release-v112-gate-20261118.md`(`a492eb3`, `origin/tok-42-release-v1.1.2-gate`)를 읽었다. 항목 1–3 증거,
  항목 4 조정자 인증 "게이트: GREEN", 항목 5 가 `release-operator-v112` 를 지정하고 자격 없는 에이전트를 나열한다.
  태그는 기록 커밋이 아니라 main 의 `ea8922d` 에 달라고 적혀 있다. Windows 산출물 두 개의 크기·sha256 도 거기 있다.
- **사용자 원문**(브리프가 아니라 git 에서 읽음): 릴리즈 커밋 `1c2ab4b` 본문 `사용자 승인(원문, 이 세션에서 사용자가 직접):`
  - 질문 "'적용'은 어디까지 할까요?" 에 "릴리스까지" 선택
  - "서명·공증·게시까지 다 진행해"
  - 질문 "v1.1.2 릴리스에 Windows 파일도 넣을까요?" 에 "Windows도 함께" 선택
- **네 번째 문장** "어디까지 했는지 확인하고 릴리즈 하던지 해 빨리 내가 아까 보낸 이슈 랑 같이" 는 게이트 기록(`a492eb3`)에서
  읽었다. 게이트 기록에 따르면 이 기록 전에는 git·PR 어디에도 없었고, 메인 세션이 조정자에게 전달했다. 이 운영의 권한은
  `1c2ab4b` 의 세 문장이 준다. 네 번째 문장으로 범위를 넓히지 않았다.
- **범위(문자 그대로):** v1.1.2 릴리즈 하나 — build/sign/notarize/universal/dmg, 태그 `v1.1.2` 를 `ea8922d` 에 달아 그 태그만
  푸시, `publish`, 그리고 게이트 기록이 적은 Windows 자산 두 개 업로드. 범위 밖: `--clobber`, 다른 버전, `all`/`ship`/맨
  `./release.sh`, main·dev 브랜치 푸시, 이 기록 외 추적 파일 수정.

## 사전 확인 (2026-11-18T04:25:52Z ~ 04:26:05Z)

| 항목 | 결과 |
| --- | --- |
| 워크트리 `HEAD` | `ea8922d91dbcb177a20dcbc6b0f61cdcda08e8ae` |
| 원격 | `git@github.com:BrilliantTiger/token-pet.git`; `dev` = `a9a330b5…`, `main` = `ea8922d9…` |
| 추적 트리 (`git status --porcelain`) | 0줄 |
| `APP_VERSION` | `961: "1.1.2"` |
| 로컬·원격 `v1.1.2` 태그 | 없음 / 없음 |
| 최신 태그; `gh release list -R BrilliantTiger/token-pet` | `v1.1.1`; `ClaudePet v1.1.1` Latest, `v1.1.0`, `v1.0.1`, `v1.0.0`, `v0.26.1` |
| `gh release view v1.1.2 -R BrilliantTiger/token-pet` | `release not found`, 종료 1 |
| 서명 identity | 1개 유효: `Developer ID Application: Yeongyu Yang (RXGNVSLYF5)` |
| notary 프로필 `claudepet-notary` | 04:26:05Z `notarytool history` → "Successfully received submission history.", 종료 0 (403 아님). 맨 위 항목 2026-10-17T12:46:04Z `ClaudePet-universal.dmg` Accepted |
| `$PY` / `$UPY` 환경변수 | 둘 다 없음 → `release.sh` 기본값 (`PY` = `UPY`) |
| `$UPY` (python.org) | 3.13.7, `lipo -archs` `x86_64 arm64`, `MACOSX_DEPLOYMENT_TARGET` 10.13, `import ServiceManagement` OK, py2app 0.28.10 |
| `gh auth status` | `uygnoey` 로 로그인 (토큰 출력 안 함) |
| HEAD 의 sha256 | `claude_pet.py` `8c7c38cc5098f1d166db6a5425c06150bb37665394dc8825d901d6d186058354`, `release.sh` `034b639df6b97cf70414b2d29f00bf29eb353b62c19bf94aec4add77bca6d2dd`, `verify_release_artifact.py` `6e86f554964372586e2a3dad67d3dae3c57a5f10207938cb7eda14e59b99248c`, `RELEASE_NOTES.md` `f61540821b38377a02210287847c347e6facfd5b14600fd443143a34c58ae32c` (작업 트리 파일 = `git show HEAD:` 블롭) |
| `hdiutil info` | 붙은 이미지 없음 |

## 단계

시각은 UTC, 종료 코드는 각 호출의 것. 전체 로그: `/Users/yeongyu/claude-pet-wt/op112-logs/NN-*.log`.

### ① `./release.sh build`

- **04:26:12Z → 04:26:21Z, 종료 0.**
  ```
  ✓ 빌드 python: /Library/Frameworks/Python.framework/Versions/Current/bin/python3 (MACOSX_DEPLOYMENT_TARGET=10.13 ≤ 12.0)
  ✅ 동봉 펫 자산 16개 확인: dist/ClaudePet.app/Contents/Resources/.claude_pet
  [gate] minos: 74 Mach-O file(s), all ≤ macOS 12.0
  ✅ 빌드: dist/ClaudePet.app ( 44M)
  ```
- 확인: `CFBundleShortVersionString` 1.1.2; `MacOS/ClaudePet`, `MacOS/python` 둘 다 `arm64`; 번들 `claude_pet.py` =
  `8c7c38cc…`(체크아웃과 같음); 추적 트리 0줄.

### ② `./release.sh sign` **[ASK-OP]**

- **04:26:30Z → 04:27:01Z, 종료 0.** 76줄: `replacing existing signature` 75줄, 마지막 `✅ 서명 검증 통과: dist/ClaudePet.app`.
- `codesign -dv --verbose=4`: `Identifier=me.yeongyu.claudepet`, `Format=app bundle with Mach-O thin (arm64)`,
  `flags=0x10000(runtime)`, `Authority=Developer ID Application: Yeongyu Yang (RXGNVSLYF5)`,
  `Timestamp=Nov 18, 2026 at 1:27:01 PM`(KST), `TeamIdentifier=RXGNVSLYF5`. `--verify --deep --strict` 통과.

### ③ `./release.sh notarize` **[ASK-OP]**

- **04:27:05Z → 04:27:49Z, 종료 0.** 제출 `a8f9098e-d353-44fc-ba24-5c445385bad3` → `status: Accepted`;
  `The staple and validate action worked!`; `✅ 공증+staple 완료 → release/ClaudePet.zip`;
  `spctl`: `accepted`, `source=Notarized Developer ID`. 로그에 error/invalid/failed 없음.
- **`release/ClaudePet.zip`**: 31,362,922 바이트, `7ee263927ff6f83af055d8234152b87245fe833642d16d46980c40dc96fd5437`.

### ④ `./release.sh universal` **[ASK-OP]**

- **04:27:53Z → 04:29:50Z, 종료 0.** `✓ 빌드 python … 10.13 ≤ 12.0`, 펫 자산 16, `[gate] minos: 74 … ≤ macOS 12.0`,
  `✅ 유니버설 빌드: dist-universal/ClaudePet.app ( 61M, archs: x86_64 arm64)`, `replacing existing signature` 75줄,
  `✅ 서명 검증 통과`. 제출 `d9cdb997-a596-4b71-929e-f77510af9112` → `Accepted`; staple 성공; `spctl` accepted,
  Notarized Developer ID. 로그에 error/invalid/failed 없음.
- 확인: `CFBundleShortVersionString` 1.1.2; 번들 `claude_pet.py` = `8c7c38cc…`;
  `Format=app bundle with Mach-O universal (x86_64 arm64)`, `TeamIdentifier=RXGNVSLYF5`.
- **`release/ClaudePet-universal.zip`**: 38,085,428 바이트, `97c2167a07bb3b10552a349c44425e7c7b72d441c017945151ffe1bf4ad9913c`.

### ⑤ `./release.sh dmg` **[ASK-OP]**

- **04:29:58Z → 04:32:09Z, 종료 0.** 제출 `eaf33d14-3f79-4f61-89fa-6ea1536f01a5`, `3da6a523-5b93-4174-856b-3f32c93eba36`,
  `status: Accepted` 2회, `staple and validate action worked` 2회. `✅ dmg 완료 → release/ClaudePet.dmg ( 32M)`,
  `✅ dmg 완료 → release/ClaudePet-universal.dmg ( 41M)`. 로그에 error/invalid/failed 없음.
- **`release/ClaudePet.dmg`**: 33,898,058 바이트, `e3a223add600e3c723bf163db1477f7c53765277e43ace88d67adf21b73e023b`.
- **`release/ClaudePet-universal.dmg`**: 41,523,819 바이트, `a8e4c6b2d2d5b8553aeaa88bde5e5bc9b3dc152785af62236afb1401ae3a8589`.
- 각각 `stapler validate` → `The validate action worked!`. 단계 뒤 `hdiutil info` 는 사전 확인과 같음(남은 마운트 없음).

### ⑥ 태그 `v1.1.2` 생성·푸시 **[ASK]**

- 사전 확인 04:32:17Z: 최신 태그 `v1.1.1`; 로컬·원격 `v1.1.2` 없음; 원격 `main` = `ea8922d9…`; `gh release list` 최신은
  v1.1.1; 추적 트리 0줄; `HEAD` = `ea8922d9…`.
- `git tag v1.1.2 ea8922d91dbcb177a20dcbc6b0f61cdcda08e8ae` 종료 0 (경량 태그, 브리프의 명령 그대로). `v1.1.2^{commit}` =
  `ea8922d9…`. 게이트 기록 항목 5 대로 main 의 `ea8922d` 에 달았다. 기록 커밋 `a492eb3` 에 달지 않았다.
- `git push origin v1.1.2`: **04:32:27Z → 04:32:30Z, 종료 0**, `* [new tag] v1.1.2 -> v1.1.2`. 원격:
  `ea8922d91dbcb177a20dcbc6b0f61cdcda08e8ae refs/tags/v1.1.2`. 이 태그 하나만, 브랜치 푸시 없음.

### ⑦ `./release.sh publish` **[ASK]**

- 직전 04:32:39Z: `gh repo view` → `BrilliantTiger/token-pet`; `cur_version` 1.1.2; `gh release view v1.1.2` 는 `-R` 없이
  (`publish()` 가 부르는 형태)와 `-R BrilliantTiger/token-pet` 둘 다 `release not found` → 생성 경로(`--clobber` 아님).
- **04:32:43Z → 04:33:06Z, 종료 0.** 게이트가 네 파일 모두 통과(`✅ 동봉 펫 자산 16개` 네 번, `[gate] minos: 74 … ≤ macOS 12.0`
  네 번, `[gate] dmg: mounted read-only …` 두 번) 뒤
  `🚀 새 릴리즈 생성: v1.1.2 ← release/ClaudePet.zip release/ClaudePet-universal.zip release/ClaudePet.dmg release/ClaudePet-universal.dmg`
  → <https://github.com/BrilliantTiger/token-pet/releases/tag/v1.1.2>

### ⑧ Windows 자산 두 개 업로드 **[ASK]**

- 파일: 사용자 Windows PC 의 `C:\Users\yeongyu\orca\workspaces\claude-pet\rel112-win\release\`. 메인 세션이 `ea8922d` 에서 만든
  무서명 빌드(게이트 기록 "Windows 산출물"). Orca 환경 `windows`(`ff301039-54a9-4313-9857-f4057ffb1cf3`)에 운영자 전용
  터미널을 따로 열었다(`orca terminal create … --title release-operator-v112`, PowerShell, 워크트리 `rel112-win`).
  다른 세션의 터미널은 쓰지 않았다.
- 첫 재해시 명령은 내 따옴표 처리 잘못으로 PowerShell `ParserError` 가 나서 아무것도 실행되지 않았다. 고쳐서 다시 보냈다.
- **04:33:45Z 재해시**(`Get-FileHash -Algorithm SHA256`, 올리는 쪽의 파일) — 게이트 기록 값과 같음(문자열 비교로 확인):
  - `git log -1` = `ea8922d91dbcb177a20dcbc6b0f61cdcda08e8ae Merge pull request #12 from BrilliantTiger/dev`; `git status --porcelain` 은
    `?? winbuild.log`, `?? wintest.log` 뿐.
  - `claude-pet-win.zip`: 72,630,325 바이트, `99344d1522cbe3ba0df817b6ed5d1cf5b3c1e173abeb3f3dce9a5980c5b9e720` (수정 04:17:38Z)
  - `claude-pet-win-setup.exe`: 56,154,776 바이트, `75eef85fbda9a7c6490f1dff078ed19cec82dec7e043b48347092ec4eb87dc38` (수정 04:17:58Z)
- 그 터미널의 `gh auth status`: `uygnoey` 로 로그인(토큰 출력 안 함). `gh release view v1.1.2`: 태그 `v1.1.2`, draft 아님, 자산 4개.
- `gh release upload v1.1.2 release\claude-pet-win.zip release\claude-pet-win-setup.exe -R BrilliantTiger/token-pet`
  (`--clobber` 없음): **04:34:21Z → 04:34:29Z, 종료 0**, `Successfully uploaded 2 assets to v1.1.2`.
- 터미널을 닫았다(`orca terminal close`, `ptyKilled: true`). Windows PC 에서 파일을 쓰거나 지우지 않았다.
- publish(04:33:06Z)부터 Windows 업로드 끝(04:34:29Z)까지 83초 동안 릴리즈에 Windows 자산이 없었다.

## ⑨ 게시 결과 확인 (04:37:08Z)

`gh release view v1.1.2 -R BrilliantTiger/token-pet`: `tagName v1.1.2`, `name ClaudePet v1.1.2`, `isDraft false`,
`isPrerelease false`, 게시 2026-11-18T04:33:06Z. `gh api repos/BrilliantTiger/token-pet/releases/latest` → `v1.1.2`
(`draft=false prerelease=false`); `gh release list` 에서 `ClaudePet v1.1.2` 가 Latest, v1.1.1 은 Latest 표시가 빠졌다.
원격 태그 `refs/tags/v1.1.2` → `ea8922d9…`.

| 자산 | 바이트 | GitHub `digest` (= 로컬·Windows sha256) |
| --- | --- | --- |
| `ClaudePet.zip` | 31,362,922 | `7ee263927ff6f83af055d8234152b87245fe833642d16d46980c40dc96fd5437` |
| `ClaudePet-universal.zip` | 38,085,428 | `97c2167a07bb3b10552a349c44425e7c7b72d441c017945151ffe1bf4ad9913c` |
| `ClaudePet.dmg` | 33,898,058 | `e3a223add600e3c723bf163db1477f7c53765277e43ace88d67adf21b73e023b` |
| `ClaudePet-universal.dmg` | 41,523,819 | `a8e4c6b2d2d5b8553aeaa88bde5e5bc9b3dc152785af62236afb1401ae3a8589` |
| `claude-pet-win.zip` | 72,630,325 | `99344d1522cbe3ba0df817b6ed5d1cf5b3c1e173abeb3f3dce9a5980c5b9e720` |
| `claude-pet-win-setup.exe` | 56,154,776 | `75eef85fbda9a7c6490f1dff078ed19cec82dec7e043b48347092ec4eb87dc38` |

모두 `state: uploaded`. 크기와 `digest` 를 스크립트로 비교해 6개 모두 일치.

**서명·공증 (빌드된 번들):**
- `dist/ClaudePet.app`: `Format=app bundle with Mach-O thin (arm64)`, `TeamIdentifier=RXGNVSLYF5`; `spctl -a -vv` →
  `accepted`, `source=Notarized Developer ID`, `origin=Developer ID Application: Yeongyu Yang (RXGNVSLYF5)`;
  `stapler validate` 성공.
- `dist-universal/ClaudePet.app`: `Format=app bundle with Mach-O universal (x86_64 arm64)`, `TeamIdentifier=RXGNVSLYF5`;
  `spctl` 같은 결과; `stapler validate` 성공.

**릴리즈 본문**의 변경 내역 절은 `**v1.1.2**` 제목 하나와 그 아래 불릿 3개다.

## 마감 상태

- 원격: 태그 `v1.1.2` → `ea8922d9…`; 릴리즈 v1.1.2 가 Latest, 자산 6개.
- 워크트리 `op112`: `release/` 에는 `icon.icns` 와 macOS 산출물 네 개, 그리고 `release.sh` 가 만든 `build/`·`dist/`·`dist-universal/`.
  추적 트리 0줄. 메인 체크아웃은 건드리지 않았다.
- 확인하지 못한 것:
  - 공증된 v1.1.2 번들을 실제로 실행해 보는 것, 그리고 화면에서 필이 더 잘리지 않는지(운영자 범위 밖).
  - 게시된 자산을 다시 내려받아 푼 확인(GitHub `digest` 가 로컬·Windows sha256 과 같은 것까지만 확인).
  - Windows 빌드 자체와 Windows 테스트(게이트 기록 "Windows 산출물"). 운영자는 올린 두 파일의 해시와 그 워크트리의 HEAD 만 봤다.
  - 네 번째 사용자 문장의 "내가 아까 보낸 이슈" 가 어느 이슈인지. 게이트 기록은 메인 세션이 운영자를 띄우기 전에 사용자에게
    확인하라고 적었지만, 그 확인 결과는 git 에서 보지 못했다. 이 릴리즈는 브리프와 게이트 기록대로 `ea8922d`(TOK-42 만)다.
    TOK-44 는 들어 있지 않다.
  - publish 와 Windows 업로드 사이 83초 동안 업데이트를 확인한 설치된 Windows 판이 실제로 있었는지. 게이트 기록의 코드 읽기에
    따르면 그런 사본은 `missing-asset` 을 받고 한 시간 뒤 다시 확인한다. 관측하지 않았다.
