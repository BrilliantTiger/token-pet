"""v8 수정 목록(briefs/v8-fixes.md)의 게이트 — B1 B2 B4 B5 F1 F3 G1(+보완) M1 M2 M3.

B3 과 M2 의 포트 쪽은 windows/tests/test_win_v8_fixes.py. F2·F4 는 화면이라 여기 없다.

진짜 네트워크·진짜 CLI·키체인·자격 증명 관리자·codesign·launchctl 은 건드리지 않는다. subprocess 는 대역이고
홈·LOCALAPPDATA·임시 폴더는 테스트의 것이다. G1 은 앱이 Terminal 에 넘길 bash 명령을 **가짜 agy**(임시 폴더의
셸 스크립트)로 실제로 돌려 본다 — 진짜 agy 는 실행하지 않는다.

여기서 정한 이름(코어 claude_pet.py)
  run_cli_login("claude", cancel=…)   cancel 을 Claude 에도 넘긴다 — "cancelled" / 기한이 지나면 "timeout".
                                      (_run_refresh_job 에 cancel 을 어떻게 넘길지는 정하지 않는다. 기존
                                      호출 `_run_refresh_job(argv, label, stem, timeout)` 은 그대로 돈다.)
  cli_login_argv("gemini", path)      [path, "-p", "/usage", "--output-format", "json"]  (G1)
  TR: term_gemini_done / term_gemini_failed / term_gemini_cert_hint  (4개 로케일; TOK-61 — 오류로 끝난
      창에 시간 초과 문구를 찍지 않는다. term_gemini_timeout 은 없다)
  _win_wmi_create(cmdline, cwd=None, …)   M1 — 앱이 깐 claude 면 명령줄 또는 env= 로 두 변수를 넘긴다.
  M3 의 정션 판정은 app_cli_ok 와 같은 기준: os.lstat(...).st_file_attributes & 0x400.
"""

import ast
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time as _real_time
import types
import unittest
from unittest import mock

import claude_pet

CORE = pathlib.Path(claude_pet.__file__)
_REAL_RUN = subprocess.run
_REAL_LSTAT = os.lstat
LANGS = ("en", "ko", "ja", "es")
SSH = ("SSH_CLIENT", "SSH_TTY", "SSH_CONNECTION")


def _require(name):
    fn = getattr(claude_pet, name, None)
    if fn is None:
        raise AssertionError("claude_pet.%s 가 없다" % name)
    return fn


class V8Case(unittest.TestCase):
    platform = "darwin"

    def setUp(self):
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="claudepet-v8-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.home = os.path.join(self.base, "home")
        self.local = os.path.join(self.base, "localappdata")
        self.sysroot = os.path.join(self.base, "sysroot")
        self.tmp = os.path.join(self.base, "tmp")
        for d in (self.home, self.local, self.tmp, os.path.join(self.sysroot, "System32")):
            os.makedirs(d)
        # 코어의 _windows_system32() 는 역슬래시로 잇는다 — macOS 에서는 그것이 파일 이름이다. 두 모양 모두에 둔다.
        for p in {os.path.join(self.sysroot, "System32", "systray.exe"),
                  "\\".join([self.sysroot, "System32", "systray.exe"])}:
            with open(p, "wb") as f:
                f.write(b"MZ synthetic systray " + b"\x00" * 64)
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, LOCALAPPDATA=self.local,
                   SystemRoot=self.sysroot, SYSTEMROOT=self.sysroot)
        for name in list(env):
            if name.upper() in SSH + ("CLAUDE_PET_DEBUG", "CODEX_HOME", "DISABLE_AUTOUPDATER",
                                      "DISABLE_INSTALLATION_CHECKS", "AGY_CLI_DISABLE_AUTO_UPDATE",
                                      "PSMODULEPATH", "HOMEDRIVE", "HOMEPATH"):
                env.pop(name)
        self._patch(mock.patch.dict(os.environ, env, clear=True))
        self._patch(mock.patch.object(tempfile, "tempdir", self.tmp))
        self._patch(mock.patch.object(sys, "platform", self.platform))
        self.dbg = []
        self._patch(mock.patch.object(claude_pet, "_dbg", lambda *a, **k: self.dbg.append(a)))

    def _patch(self, p):
        got = p.start()
        self.addCleanup(p.stop)
        return got

    def keep(self, *dicts):
        """모듈의 상태 dict 를 테스트 뒤에 되돌린다."""
        for d in dicts:
            snap = dict(d)
            self.addCleanup(lambda d=d, snap=snap: (d.clear(), d.update(snap)))


# ═════════════════════════════ B1 — macOS 서명 요구 ═════════════════════════════

class SignatureRequirementTests(V8Case):
    """가짜 codesign: 서명자를 (팀, ad-hoc 인가)로 흉내 낸다.
      · `--verify` 에 요구(-R)가 없으면 ad-hoc 도 0 으로 통과한다(진짜 codesign 과 같다).
      · 요구가 있으면: ad-hoc 이 아니고, `anchor apple generic` 이고, leaf 의 subject.OU 가 그 서명자의 팀일 때만 0.
      · `-dv` 는 TeamIdentifier 한 줄을 찍는다 — **ad-hoc 위조본도 같은 팀을 찍을 수 있다.**"""

    def setUp(self):
        super().setUp()
        self.signer = ("", False)
        self.calls = []
        self._patch(mock.patch.object(claude_pet.subprocess, "run", self._codesign))
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen",
                                      side_effect=AssertionError("Popen 으로 무언가를 띄웠다")))

    @staticmethod
    def _requirement(argv):
        for i, a in enumerate(argv):
            if a in ("-R", "--test-requirement") and i + 1 < len(argv):
                return argv[i + 1]
            for pre in ("-R=", "--test-requirement="):
                if a.startswith(pre):
                    return a[len(pre):]
        return None

    def _codesign(self, argv, *a, **k):
        argv = [str(x) for x in argv]
        self.calls.append(argv)
        if argv[0] != "/usr/bin/codesign":
            raise AssertionError("codesign 말고 다른 것을 띄웠다: %r" % argv[0])
        team, adhoc = self.signer
        if "--verify" in argv or "-v" in argv:
            req = self._requirement(argv)
            if req is None:
                return subprocess.CompletedProcess(argv, 0, "", "")
            ou = re.findall(r'subject\.OU\]\s*=\s*"?([A-Z0-9]+)"?', req)
            ok = (not adhoc) and "anchor apple generic" in req and ou == [team]
            return subprocess.CompletedProcess(argv, 0 if ok else 3, "", "" if ok else "test-requirement: failed\n")
        return subprocess.CompletedProcess(argv, 0, "", "Identifier=x\nTeamIdentifier=%s\n" % team)

    def test_an_ad_hoc_copy_claiming_the_vendors_team_is_refused(self):
        """B1(보안): `codesign --verify --strict` 는 ad-hoc 서명도 통과시키고 TeamIdentifier 는 위조할 수 있다.
        검증에 **Developer ID 요구**(`-R` — anchor apple generic + leaf 의 subject.OU = 그 제공사의 팀)를 건다.
        Rivals: `--verify --strict` + TeamIdentifier 줄만 봄(ad-hoc 위조본을 설치한다); 요구에 다른 팀을 넣음;
        요구에 anchor 가 없음(자체 서명 인증서)."""
        ok = _require("cli_signature_ok")
        path = os.path.join(self.base, "staged")
        with open(path, "wb") as f:
            f.write(b"\xcf\xfa\xed\xfe synthetic")
        teams = claude_pet.CLI_TEAM_IDS
        self.assertEqual(teams, {"claude": "Q6L2SF6YDW", "codex": "2DC432GLL2", "gemini": "EQHXZ8M8AV"})
        for p, team in teams.items():
            with self.subTest(provider=p):
                self.signer = (team, False)
                self.calls.clear()
                self.assertIs(ok(p, path), True, "진짜 Developer ID 서명을 거절했다")
                reqs = [self._requirement(c) for c in self.calls if self._requirement(c) is not None]
                self.assertTrue(reqs, "검증에 요구(-R)를 걸지 않았다")
                self.signer = (team, True)
                self.assertIs(ok(p, path), False, "ad-hoc 서명 + 같은 TeamIdentifier 위조본을 받아들였다")
                other = next(t for t in teams.values() if t != team)
                self.signer = (other, False)
                self.assertIs(ok(p, path), False, "다른 제공사의 Developer ID 를 받아들였다")


# ═════════════════════════════ B2 — Windows 서명 확인의 PSModulePath ═════════════════════════════

class WindowsSignatureEnvTests(V8Case):
    platform = "win32"

    def test_the_powershell_child_gets_no_psmodulepath_in_any_spelling(self):
        """B2(Windows 실기기 — 설치 실패): 앱이 PowerShell 7 에서 떴으면 PSModulePath 가 7 의 모듈 폴더를
        가리켜, powershell.exe(5.1)의 Get-AuthenticodeSignature 가 모듈을 못 읽는다. 서명 확인이 띄우는
        자식의 env 에서 그 변수를 **대소문자 무관하게** 지운다. 앱 자신의 환경은 그대로다.
        Rivals: os.environ 을 그대로 넘김; `PSModulePath` 한 철자만 지움."""
        ok = _require("cli_signature_ok")
        spellings = {"PSModulePath": "C:/pwsh7/Modules", "PSMODULEPATH": "C:/x", "psmodulepath": "C:/y"}
        self._patch(mock.patch.dict(os.environ, spellings))
        before = dict(os.environ)
        seen = []

        def run(argv, *a, **k):
            seen.append(([str(x) for x in argv], dict(k)))
            return subprocess.CompletedProcess(argv, 0, "Valid\nCN=OpenAI OpCo, LLC, O=\"OpenAI OpCo, LLC\", C=US\n", "")
        self._patch(mock.patch.object(claude_pet.subprocess, "run", run))
        self.assertIs(ok("codex", os.path.join(self.local, "staged.exe")), True)
        self.assertEqual(len(seen), 1)
        argv, kw = seen[0]
        self.assertTrue(argv[0].replace("\\", "/").lower().endswith("windowspowershell/v1.0/powershell.exe"))
        env = kw.get("env")
        self.assertIsInstance(env, dict, "자식에게 env 를 따로 주지 않았다(앱의 PSModulePath 를 물려받는다)")
        self.assertEqual([k for k in env if k.upper() == "PSMODULEPATH"], [])
        self.assertTrue(dict(os.environ) == before, "앱 자신의 환경을 바꿨다")


# ═════════════════════════════ B4 — Claude 로그인의 취소와 기한 ═════════════════════════════

class ClaudeLoginCancelTests(V8Case):

    def setUp(self):
        super().setUp()
        self.bootouts = []
        self.keep(claude_pet.OAUTH_STATUS)
        claude_pet.OAUTH_STATUS["auth_error"] = False
        self._patch(mock.patch.object(claude_pet, "find_cli", lambda p: "/synthetic/bin/claude"))
        self._patch(mock.patch.object(claude_pet, "claude_token_present", lambda: False))
        self.alive = True
        self._patch(mock.patch.object(claude_pet, "_launchctl_job_alive", lambda label: self.alive))
        self._patch(mock.patch.object(claude_pet, "_launchctl_bootout",
                                      lambda label: self.bootouts.append((_real_time.time(), label))))
        self._patch(mock.patch.object(claude_pet.subprocess, "run", self._run))
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen",
                                      side_effect=AssertionError("claude 를 자식으로 띄웠다")))

    def _run(self, argv, *a, **k):
        argv = [str(x) for x in argv]
        if os.path.basename(argv[0]) == "security":
            return subprocess.CompletedProcess(argv, 44, "", "not found\n")
        if argv[0] == claude_pet.LAUNCHCTL:
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError("뜻밖의 프로세스: %r" % os.path.basename(argv[0]))

    def login(self, limit=8.0, **kw):
        """run_cli_login("claude") 을 스레드에서 — limit 초 안에 안 끝나면 job 을 "끝난 것"으로 바꿔 풀어 주고
        실패로 적는다(취소를 보지 않는 구현이 이 테스트를 300초 붙들지 않게)."""
        box = []

        def work():
            t0 = _real_time.time()
            try:
                box.append((claude_pet.run_cli_login("claude", **kw), _real_time.time() - t0))
            except Exception as e:  # noqa: BLE001
                box.append(("raised " + type(e).__name__, _real_time.time() - t0))
        th = threading.Thread(target=work, daemon=True)
        th.start()
        th.join(limit)
        if th.is_alive():
            self.alive = False
            th.join(10)
            self.fail("%.0f초가 지나도 run_cli_login(\"claude\") 이 끝나지 않았다" % limit)
        return box[0]

    def test_cancel_takes_effect_at_once_and_takes_the_job_down(self):
        """B4: Claude 로그인 중 [취소] — 대기 루프가 cancel 을 보고 job 을 내리고 "cancelled". 전에는 cancel 을
        보지 않아 300초를 다 기다렸다.
        Rivals: cancel 을 Claude 에 넘기지 않음; 2초 잠에서 깨어난 뒤에야 봄(느리다); job 을 남겨 둠
        (브라우저 로그인 서버가 계속 돈다); 취소를 "failed" 로."""
        flag = threading.Event()
        timer = threading.Timer(0.3, flag.set)
        timer.daemon = True
        timer.start()
        self.addCleanup(timer.cancel)
        t0 = _real_time.time()
        got, took = self.login(cancel=flag.is_set)
        self.assertEqual(got, "cancelled")
        self.assertGreaterEqual(took, 0.25, "취소하기 전에 끝났다")
        self.assertLess(took, 0.3 + 1.5, "취소를 누르고 1.5초가 넘도록 기다렸다")
        after = [t for t, label in self.bootouts if t >= t0 + 0.3 and label == claude_pet.LOGIN_JOB_LABEL]
        self.assertTrue(after, "취소한 뒤 job 을 내리지 않았다")

    def test_the_deadline_is_a_timeout_not_a_failure(self):
        """B4: 기한(CLI_LOGIN_TIMEOUT_SEC["claude"])을 넘기면 "timeout" — job 을 내린다. job 이 스스로 끝났는데
        토큰이 없으면 시간 초과가 아니다.
        Rivals: 기한을 넘겨도 "failed"(왜 안 됐는지 모른다); 기한 뒤 job 을 남김."""
        self._patch(mock.patch.object(claude_pet, "CLI_LOGIN_TIMEOUT_SEC", {"claude": 1.0, "codex": 300}))
        got, took = self.login()
        self.assertEqual(got, "timeout")
        self.assertLess(took, 6.0)
        self.assertTrue([1 for _t, label in self.bootouts if label == claude_pet.LOGIN_JOB_LABEL])
        self.alive = False
        got, _took = self.login()
        self.assertNotIn(got, ("timeout", "cancelled", "ok", "already"), "job 이 스스로 끝났는데 %r" % got)


# ═════════════════════════════ B5 — "ok" 직후 바로 연결됨 + 읽기 ═════════════════════════════

class ConnectedRightAfterLoginTests(V8Case):

    def setUp(self):
        super().setUp()
        self.keep(claude_pet._gemini_cache, claude_pet.GEMINI_STATUS, claude_pet._oauth_token_cache,
                  claude_pet.OAUTH_STATUS, claude_pet._oauth_cache, claude_pet._codex_cache,
                  claude_pet.CODEX_STATUS)
        self.login_result = "ok"
        self.reads = []
        self._patch(mock.patch.object(claude_pet, "find_cli", lambda p: "/synthetic/bin/x"))
        self._patch(mock.patch.object(claude_pet, "run_cli_login", lambda p, *a, **k: self.login_result))
        self._patch(mock.patch.object(claude_pet, "install_cli",
                                      side_effect=AssertionError("설치돼 있는데 받으려 했다")))
        self._patch(mock.patch.object(claude_pet, "fetch_exact_usage",
                                      lambda *a, **k: self.reads.append("claude")))
        self._patch(mock.patch.object(claude_pet, "claude_token_present", lambda: True))

    def stale(self):
        claude_pet._gemini_cache.update(t=1_700_000_000.0, ok_t=None, rows=None)
        claude_pet.GEMINI_STATUS["auth_error"] = True
        claude_pet._oauth_token_cache.update(next_retry=_real_time.time() + 900, declined=True)
        claude_pet.OAUTH_STATUS["auth_error"] = True
        self.reads.clear()

    def connect(self, provider):
        job = {"phase": None, "pct": None, "reason": None}
        return claude_pet.run_ai_connect(provider, job), job

    def test_gemini_is_connected_the_moment_the_login_says_ok(self):
        """B5: Gemini 로그인이 "ok" 면 바로 "연결됨" + 읽기 — `_gemini_cache["t"] = 0`(다음 주기에 바로 읽는다),
        `ok_t = now`, `GEMINI_STATUS["auth_error"] = False`. 전에는 다음 조회(최대 5분)가 성공할 때까지
        "로그인 필요 [로그인]" 이 그대로였다.
        Rivals: 깃발만 올리고 ok_t 는 그대로(줄이 안 바뀐다); 실패했는데도 연결됨으로 바꿈."""
        self.stale()
        self.assertIs(claude_pet.cli_logged_in("gemini"), False)
        t0 = _real_time.time()
        got, job = self.connect("gemini")
        self.assertEqual(got, "ok")
        self.assertEqual(claude_pet._gemini_cache["t"], 0)
        ok_t = claude_pet._gemini_cache["ok_t"]
        self.assertIsInstance(ok_t, float)
        self.assertTrue(t0 - 1 <= ok_t <= _real_time.time() + 1, "ok_t 가 지금이 아니다")
        self.assertIs(claude_pet.GEMINI_STATUS["auth_error"], False)
        self.assertIs(claude_pet.cli_logged_in("gemini"), True)
        row = claude_pet.ai_connect_row("gemini", True, claude_pet.cli_logged_in("gemini"), job)
        self.assertEqual((row["status"], row["button"]), ("ai_connected", None))
        for result in ("denied", "timeout", "failed", "cancelled"):
            with self.subTest(result=result):
                self.stale()
                self.login_result = result
                self.connect("gemini")
                self.assertIsNone(claude_pet._gemini_cache["ok_t"], "로그인이 %s 인데 연결됨으로 바꿨다" % result)
                self.assertIs(claude_pet.GEMINI_STATUS["auth_error"], True)

    def test_claude_is_read_once_right_after_the_login_says_ok(self):
        """B5: Claude 로그인이 "ok" 면 `_oauth_token_cache` 의 `next_retry = 0`·`declined = False`,
        `OAUTH_STATUS["auth_error"] = False` 로 두고 사용량을 **한 번** 읽는다(fetch_exact_usage).
        전에는 직전 401 의 쿨다운·거절 표시가 남아 새 토큰을 읽지 않았다.
        Rivals: 캐시 시각만 0 으로(쿨다운 때문에 토큰을 안 읽는다); 실패해도 읽음; 여러 번 읽음."""
        self.stale()
        got, _job = self.connect("claude")
        self.assertEqual(got, "ok")
        end = _real_time.time() + 3
        while not self.reads and _real_time.time() < end:
            _real_time.sleep(0.02)
        _real_time.sleep(0.2)
        self.assertEqual(self.reads, ["claude"], "로그인 직후 사용량을 정확히 한 번 읽지 않았다")
        self.assertEqual(claude_pet._oauth_token_cache["next_retry"], 0)
        self.assertIs(claude_pet._oauth_token_cache["declined"], False)
        self.assertIs(claude_pet.OAUTH_STATUS["auth_error"], False)
        self.stale()
        self.login_result = "denied"
        self.connect("claude")
        _real_time.sleep(0.2)
        self.assertEqual(self.reads, [], "로그인이 실패했는데 읽었다")
        self.assertIs(claude_pet._oauth_token_cache["declined"], True)
        self.assertIs(claude_pet.OAUTH_STATUS["auth_error"], True)


# ═════════════════════════════ F1 — "연결됨"은 읽을 수 있을 때만 ═════════════════════════════

CODEX_AUTH = json.dumps({"tokens": {"access_token": "synthetic-access", "account_id": "synthetic-acct"}})


class ConnectedMeansReadableTests(V8Case):

    def setUp(self):
        super().setUp()
        self.keep(claude_pet.CODEX_STATUS, claude_pet.OAUTH_STATUS)
        auth = os.path.join(self.home, ".codex", "auth.json")
        os.makedirs(os.path.dirname(auth))
        with open(auth, "w", encoding="utf-8") as f:
            f.write(CODEX_AUTH)
        self.auth = auth
        self.assertTrue(claude_pet.read_codex_token(claude_pet.codex_auth_path()), "픽스처가 유효하지 않다")
        self.spawned = []

        def popen(argv, *a, **k):
            self.spawned.append([str(x) for x in argv])
            raise OSError("synthetic: not started")
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen", popen))
        self._patch(mock.patch.object(claude_pet.urllib.request, "urlopen",
                                      side_effect=OSError("synthetic: no network")))

    def test_a_codex_token_the_server_rejected_is_not_connected(self):
        """F1(Windows 실기기): auth.json 에 토큰이 있어도 서버가 거절했으면(CODEX_STATUS["auth_error"]) "연결됨"
        이 아니다 — 줄은 CLI 가 없으면 `설치 안 됨 [설치]`, 있으면 `로그인 필요 [로그인]`.
        Rival: 토큰 파일이 있다는 것만으로 연결됨(사용량은 안 나오는데 버튼이 없다)."""
        logged = _require("cli_logged_in")
        claude_pet.CODEX_STATUS["auth_error"] = False
        self.assertIs(logged("codex"), True)
        claude_pet.CODEX_STATUS["auth_error"] = True
        self.assertIs(logged("codex"), False, "만료된 Codex 토큰을 연결됨으로 봤다")
        row = claude_pet.ai_connect_row("codex", False, logged("codex"))
        self.assertEqual((row["status"], row["button"]), ("ai_not_installed", "ai_btn_install"))
        row = claude_pet.ai_connect_row("codex", True, logged("codex"))
        self.assertEqual((row["status"], row["button"]), ("ai_need_login", "ai_btn_login"))

    def test_the_codex_guard_lets_a_rejected_token_sign_in_again(self):
        """F1: `codex login` 가드는 **유효한** 로그인만 지킨다. 서버가 거절한 토큰이면 [로그인] 이 실제로
        `codex login` 을 띄운다. 유효하면 전과 같이 "already"(띄우지 않는다 — 그 명령은 기존 토큰을 지운다).
        Rival: 토큰 파일이 있으면 언제나 "already"([로그인] 을 눌러도 아무 일도 없다)."""
        codex = os.path.join(self.home, ".local", "bin", "codex")
        self._patch(mock.patch.object(claude_pet, "find_cli", lambda p: codex))
        claude_pet.CODEX_STATUS["auth_error"] = False
        self.assertEqual(claude_pet.run_cli_login("codex"), "already")
        self.assertEqual(self.spawned, [])
        claude_pet.CODEX_STATUS["auth_error"] = True
        got = claude_pet.run_cli_login("codex")
        self.assertNotEqual(got, "already")
        self.assertEqual(self.spawned, [[codex, "login"]], "거절된 토큰인데 codex login 을 띄우지 않았다")

    def test_install_carries_on_into_login_when_the_token_is_no_good(self):
        """F1: CLI 가 없고 토큰이 거절된 상태에서 [설치] — 설치 뒤 로그인으로 이어진다.
        Rival: 설치만 하고 "이미 로그인됨" 으로 끝냄."""
        claude_pet.CODEX_STATUS["auth_error"] = True
        state = {"installed": False}
        log = []

        def install(provider, *a, **k):
            log.append("install")
            state["installed"] = True
            return True, "/synthetic/bin/codex"
        self._patch(mock.patch.object(claude_pet, "find_cli",
                                      lambda p: "/synthetic/bin/codex" if state["installed"] else None))
        self._patch(mock.patch.object(claude_pet, "install_cli", install))
        self._patch(mock.patch.object(claude_pet, "run_cli_login",
                                      lambda p, *a, **k: log.append("login") or "denied"))
        claude_pet.run_ai_connect("codex", {"phase": None, "pct": None, "reason": None})
        self.assertEqual(log, ["install", "login"])


# ═════════════════════════════ F3 — 이름 통일 ═════════════════════════════

class GeminiNameTests(unittest.TestCase):

    def test_the_gemini_section_and_the_ai_row_use_one_name(self):
        """F3: 설정 왼쪽 구역 제목(`s_sec_gemini`)과 "AI 연결" 줄의 이름이 4개 로케일 모두 "Gemini (Antigravity)".
        Rival: 왼쪽은 "Gemini (agy)", 오른쪽은 "Gemini (Antigravity)"(같은 것을 두 이름으로 부른다)."""
        self.assertEqual({lang: claude_pet.TR[lang].get("s_sec_gemini") for lang in LANGS},
                         {lang: "Gemini (Antigravity)" for lang in LANGS})
        self.assertEqual(getattr(claude_pet, "AI_PROVIDER_NAMES", {}).get("gemini"), "Gemini (Antigravity)")


# ═════════════════════════════ G1 — Gemini 로그인 창 ═════════════════════════════

_FAKE_AGY = r"""#!/bin/bash
here="$(cd "$(dirname "$0")" && pwd)"
printf '%s\n' "$@" > "$here/args"
env > "$here/env"
command -v open > "$here/open"
echo 'PASTE-THE-CODE-HERE-PROMPT' >&2
echo '{"schemaVersion": 1, "status": "SYNTHETIC-JSON-BODY"}'
exit "$(cat "$here/rc")"
"""
WANT_ARGS = ["-p", "/usage", "--output-format", "json"]
# TOK-61: 오류로 끝난 로그인 창에 찍으면 안 되는 말(4개 로케일의 옛 term_gemini_timeout).
TIMEOUT_WORDS = ("시간이 지났", "Time ran out", "時間切れ", "agotó el tiempo")


@unittest.skipIf(sys.platform == "win32", "macOS 의 Terminal 명령(bash)을 돌려 본다")
class GeminiWindowScriptTests(V8Case):

    def setUp(self):
        super().setUp()
        self.keep(claude_pet._gemini_cache)
        self.bin = os.path.join(self.base, "agy bin")        # 공백이 있는 경로
        os.makedirs(self.bin)
        self.agy = os.path.join(self.bin, "agy")
        with open(self.agy, "w", encoding="utf-8") as f:
            f.write(_FAKE_AGY)
        os.chmod(self.agy, 0o755)
        self._patch(mock.patch.object(claude_pet, "_find_agy_cli", lambda: self.agy))

    def script(self, lang):
        seen = []
        with mock.patch.dict(claude_pet.L, {"lang": lang}), \
                mock.patch.object(claude_pet, "_run_in_terminal", side_effect=seen.append), \
                mock.patch.object(claude_pet.subprocess, "run", side_effect=AssertionError("프로세스를 띄웠다")), \
                mock.patch.object(claude_pet.subprocess, "Popen", side_effect=AssertionError("프로세스를 띄웠다")):
            _require("start_gemini_login")()
        self.assertEqual(len(seen), 1, "Terminal 창을 한 번 열지 않았다")
        return str(seen[0])

    def run_script(self, script, rc):
        with open(os.path.join(self.bin, "rc"), "w", encoding="utf-8") as f:
            f.write(str(rc))
        for name in ("args", "env", "open"):
            if os.path.exists(os.path.join(self.bin, name)):
                os.unlink(os.path.join(self.bin, name))
        env = {"HOME": self.home, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "TERM": "dumb", "LANG": "en_US.UTF-8",
               "SSH_TTY": "/dev/ttys000", "SSH_CLIENT": "x", "SSH_CONNECTION": "y"}
        # stdout 과 stderr 를 한 줄기로 — 창에 보이는 순서 그대로.
        r = _REAL_RUN(["/bin/bash", "-c", script], env=env, cwd=self.tmp, stdin=subprocess.DEVNULL,
                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)

        def read(name):
            p = os.path.join(self.bin, name)
            if not os.path.exists(p):
                return None
            with open(p, encoding="utf-8") as f:
                return f.read()
        return r, read

    def test_the_window_runs_the_usage_query_under_the_three_steps_and_says_how_it_ended(self):
        """G1(+보완): 인자 없는 `agy`(TUI)는 대체 화면으로 바뀌어 안내 세 줄을 가린다. 창에서는
        `agy -p "/usage" --output-format json` 을 실행한다. 안내 세 줄이 먼저, agy 의 **stdout(JSON 본문)은
        숨기고** stderr(로그인 안내·붙여 넣기 프롬프트)는 보인다. 끝나면 종료 코드로 끝맺는다 — 0 이면
        `term_gemini_done`, 아니면 `term_gemini_failed`("로그인하지 못했어요 — 위 오류를 확인하세요")와
        `term_gemini_cert_hint`(TOK-61: 1.2.0 은 인증서 오류로 곧바로 끝난 agy 뒤에 "시간이 지났어요" 를
        찍었다 — 0 이 아닌 종료에 시간 초과 문구는 없다). SSH_* 를 지우고 AGY_CLI_DISABLE_AUTO_UPDATE=1(M2).
        가짜 open 은 없다(브라우저가 떠야 한다). 4개 로케일.
        Rivals: 인자 없는 agy; JSON 이 창에 쏟아짐; stderr 까지 숨김(코드를 어디에 넣는지 안 보인다);
        끝났는지 말이 없음; 실패에도 "완료"; 오류에 "시간이 지났어요"; SSH_* 가 남아 토큰이 파일로 감."""
        for lang in LANGS:
            with self.subTest(lang=lang):
                table = claude_pet.TR[lang]
                steps = [table["term_gemini_step%d" % i] for i in (1, 2, 3)]
                done, late = table.get("term_gemini_done"), table.get("term_gemini_failed")
                cert = table.get("term_gemini_cert_hint")
                self.assertTrue(all(isinstance(x, str) and x.strip() for x in (done, late, cert)),
                                "끝맺는 문구(term_gemini_done / term_gemini_failed / term_gemini_cert_hint)가 없다")
                self.assertNotEqual(done, late)
                self.assertNotIn("term_gemini_timeout", table, "오류로 끝난 창에 찍던 시간 초과 문구가 남아 있다")
                script = self.script(lang)
                self.assertNotIn("fake-open", script)
                for rc, shown, hidden in ((0, done, late), (1, late, done)):
                    r, read = self.run_script(script, rc)
                    out = r.stdout
                    self.assertEqual((read("args") or "").splitlines(), WANT_ARGS, "agy 를 `-p /usage` 로 띄우지 않았다")
                    env = dict(ln.split("=", 1) for ln in (read("env") or "").splitlines() if "=" in ln)
                    self.assertEqual([k for k in SSH if k in env], [], "agy 에 SSH_* 가 넘어갔다")
                    self.assertEqual(env.get("AGY_CLI_DISABLE_AUTO_UPDATE"), "1")
                    self.assertEqual((read("open") or "").strip(), "/usr/bin/open", "창의 PATH 에서 open 이 가려졌다")
                    at = [out.find(x) for x in steps]
                    self.assertNotIn(-1, at, "안내 세 줄이 창에 다 찍히지 않았다")
                    self.assertEqual(at, sorted(at))
                    self.assertNotIn("SYNTHETIC-JSON-BODY", out, "agy 의 stdout(JSON)이 창에 찍혔다")
                    self.assertIn("PASTE-THE-CODE-HERE-PROMPT", out, "agy 의 stderr(붙여 넣기 안내)를 숨겼다")
                    self.assertLess(max(at), out.find("PASTE-THE-CODE-HERE-PROMPT"), "안내가 agy 보다 늦다")
                    self.assertIn(shown, out, "끝난 뒤 알맞은 한 줄이 없다(rc=%d)" % rc)
                    self.assertNotIn(hidden, out, "rc=%d 인데 반대쪽 문구를 찍었다" % rc)
                    self.assertGreater(out.find(shown), out.find("PASTE-THE-CODE-HERE-PROMPT"))
                    self.assertEqual(cert in out, rc != 0, "인증서 안내는 오류로 끝났을 때만 찍는다(rc=%d)" % rc)
                    for word in TIMEOUT_WORDS:
                        self.assertNotIn(word, out, "창에 시간 초과 문구를 찍었다(rc=%d)" % rc)

    def test_the_closing_lines_exist_in_four_languages(self):
        """G1·TOK-61: "완료 — 창을 닫아도 됩니다" / "로그인하지 못했어요 — 위 오류를 확인하세요" / 인증서 안내
        (4개 로케일). 어느 것에도 시간 초과라는 말이 없다."""
        ko = claude_pet.TR["ko"]
        self.assertEqual([w for w in ("완료", "창을 닫아도") if w not in str(ko.get("term_gemini_done"))], [])
        self.assertEqual([w for w in ("로그인하지 못했어요", "위 오류") if w not in str(ko.get("term_gemini_failed"))], [])
        self.assertEqual([w for w in ("인증서", "x509", "certificate", "프록시")
                          if w not in str(ko.get("term_gemini_cert_hint"))], [])
        for lang in LANGS:
            for key in ("term_gemini_done", "term_gemini_failed", "term_gemini_cert_hint"):
                for word in TIMEOUT_WORDS:
                    self.assertNotIn(word, str(claude_pet.TR[lang].get(key)))
        for lang in ("en", "ja", "es"):
            for key in ("term_gemini_done", "term_gemini_failed", "term_gemini_cert_hint"):
                val = claude_pet.TR[lang].get(key)
                self.assertTrue(isinstance(val, str) and val.strip(), "%s.%s 가 없다" % (lang, key))
                self.assertNotEqual(val, ko.get(key), "%s 로케일에 한국어 문구가 그대로다" % lang)

    def test_the_login_argv_table_matches_the_window(self):
        self.assertEqual(_require("cli_login_argv")("gemini", "/x/agy"), ["/x/agy"] + WANT_ARGS)


class GeminiWindowOnWindowsTests(V8Case):
    platform = "win32"

    def test_the_new_console_runs_the_usage_query_hides_stdout_and_says_how_it_ended(self):
        """G1(+보완), Windows: 새 콘솔(CREATE_NEW_CONSOLE)에서 안내 세 줄 → `agy.exe -p /usage --output-format
        json`(stdout 만 버린다 — stderr 는 그대로) → 종료 코드에 따라 완료 / 로그인하지 못했어요 + 인증서 안내
        (TOK-61: 시간 초과 문구는 없다). env 에는 SSH_* 가
        없고 AGY_CLI_DISABLE_AUTO_UPDATE=1, PATH 에 가짜 rundll32 폴더가 없다.
        Rivals: 인자 없는 agy.exe; stdout 을 안 버림; 모든 스트림을 버림(`*>` / `2>`); 끝맺는 줄이 없음."""
        self.keep(claude_pet._gemini_cache)
        agy = os.path.join(self.home, ".local", "bin", "agy.exe")
        opened = []

        def popen(argv, *a, **k):
            opened.append(([str(x) for x in argv], dict(k)))
            return mock.Mock(pid=4242, returncode=None)
        self._patch(mock.patch.dict(os.environ, {"SSH_TTY": "x", "SSH_CLIENT": "y", "SSH_CONNECTION": "z"}))
        with mock.patch.object(claude_pet, "_find_agy_cli", lambda: agy), \
                mock.patch.dict(claude_pet.L, {"lang": "ko"}), \
                mock.patch.object(claude_pet, "_run_in_terminal",
                                  side_effect=AssertionError("Windows 에서 Terminal.app 을 열었다")), \
                mock.patch.object(claude_pet.subprocess, "Popen", popen):
            _require("start_gemini_login")()
        self.assertEqual(len(opened), 1)
        argv, kw = opened[0]
        flags = int(kw.get("creationflags") or 0)
        self.assertTrue(flags & 0x10 and not flags & 0x08000000, "보이는 새 콘솔이 아니다")
        text = " ".join(argv)
        ko = claude_pet.TR["ko"]
        steps = [ko["term_gemini_step%d" % i] for i in (1, 2, 3)]
        at = [text.find(x) for x in steps] + [text.find(agy)]
        self.assertNotIn(-1, at)
        self.assertEqual(at, sorted(at))
        tail = text[text.find(agy):]
        for word in WANT_ARGS:
            self.assertIn(word, tail, "agy.exe 에 %r 인자가 없다" % word)
        self.assertRegex(tail, r"(Out-Null|(?<![2*])>\s*\$null|1>\s*\$null)", "agy 의 stdout 을 버리지 않는다")
        self.assertNotRegex(tail, r"(\*>|2>\s*\$null|2>&1\s*\|\s*Out-Null)", "agy 의 stderr 까지 버린다")
        for key in ("term_gemini_done", "term_gemini_failed", "term_gemini_cert_hint"):
            self.assertTrue(isinstance(ko.get(key), str) and ko[key] in tail, "%s 문구가 명령에 없다" % key)
        for word in TIMEOUT_WORDS:
            self.assertNotIn(word, text, "새 콘솔의 명령에 시간 초과 문구가 있다")
        self.assertIn("LASTEXITCODE", tail, "agy 의 종료 코드를 보지 않는다")
        env = kw.get("env")
        self.assertIsInstance(env, dict)
        self.assertEqual([k for k in env if k.upper() in SSH], [])
        self.assertEqual(env.get("AGY_CLI_DISABLE_AUTO_UPDATE"), "1")
        self.assertNotIn("fake-open", str(env.get("PATH", "")))


# ═════════════════════════════ M1 — Windows 의 앱이 깐 claude ═════════════════════════════

class WindowsAppClaudeEnvTests(V8Case):
    platform = "win32"

    def test_an_app_installed_claude_is_started_with_its_updater_off_on_windows_too(self):
        """M1: Windows 에서도 앱이 깐 claude 를 띄울 때 DISABLE_AUTOUPDATER=1·DISABLE_INSTALLATION_CHECKS=1
        (명령줄 안에서든 `_win_wmi_create(..., env=…)` 로든). 사용자가 깐 claude 에는 넣지 않는다.
        Rival: macOS 만 넣음(WMI 는 환경을 안 넘긴다 — 앱이 깐 것을 CLI 가 스스로 바꾼다)."""
        seen = []

        def create(cmdline, *a, **k):
            seen.append((str(cmdline), dict(k)))
            return None
        self._patch(mock.patch.object(claude_pet, "_win_wmi_create", create))
        names = ("DISABLE_AUTOUPDATER", "DISABLE_INSTALLATION_CHECKS")

        def carried(path):
            seen.clear()
            claude_pet._run_refresh_job([path, "auth", "login", "--claudeai"],
                                        claude_pet.LOGIN_JOB_LABEL, "login", 5)
            self.assertEqual(len(seen), 1, "WMI 로 한 번 띄우지 않았다")
            cmdline, kw = seen[0]
            env = kw.get("env") or {}
            return [n for n in names if env.get(n) == "1" or (n + "=1") in cmdline]
        self.assertEqual(carried(claude_pet.app_cli_path("claude")), list(names))
        self.assertEqual(carried(os.path.join(self.home, ".local", "bin", "claude.exe")), [],
                         "사용자가 깐 claude 의 자동 업데이트를 껐다")


# ═════════════════════════════ M3 — Windows 폴더의 재해석 지점 ═════════════════════════════

def _as_reparse(st):
    return types.SimpleNamespace(st_mode=st.st_mode, st_uid=st.st_uid, st_gid=st.st_gid, st_size=st.st_size,
                                 st_mtime=st.st_mtime, st_mtime_ns=st.st_mtime_ns, st_ino=st.st_ino,
                                 st_dev=st.st_dev, st_nlink=st.st_nlink, st_file_attributes=0x400 | 0x10)


class WindowsJunctionTests(V8Case):
    platform = "win32"

    def junction(self, target):
        """target 폴더를 정션으로 보이게 한다 — app_cli_ok 와 같은 판정(os.lstat 의 st_file_attributes & 0x400)."""
        want = os.path.normcase(os.path.abspath(target))

        def lstat(path, *a, **k):
            st = _REAL_LSTAT(path, *a, **k)
            if not isinstance(path, int) and os.path.normcase(os.path.abspath(os.fspath(path))) == want:
                return _as_reparse(st)
            return st
        return mock.patch.object(claude_pet.os, "lstat", lstat)

    def test_a_junction_for_the_bin_or_staging_folder_is_refused(self):
        """M3: Windows 에서 앱 bin·staging 폴더가 재해석 지점(정션)이면 받지 않는다 — 다른 곳으로 이어진 폴더에
        실행 파일을 쓰지 않는다. `app_cli_ok` 와 같은 기준.
        Rival: os.path.islink 만 봄(정션은 심볼릭 링크가 아니다)."""
        stage = _require("cli_stage_download")
        bin_dir = claude_pet.app_cli_bin_dir()
        staging = os.path.join(bin_dir, "staging")
        body = b"MZ synthetic " * 100
        import hashlib
        import io
        digest = hashlib.sha256(body).hexdigest()
        opened = []

        def opener(url):
            opened.append(url)
            return io.BytesIO(body)
        got = stage("https://example.invalid/x", "sha256", digest, opener)
        self.assertTrue(os.path.isfile(got), "평소의 받기가 안 된다 — 이 테스트의 전제가 틀렸다")
        os.unlink(got)
        for name, folder in (("bin", bin_dir), ("staging", staging)):
            with self.subTest(folder=name):
                opened.clear()
                with self.junction(folder):
                    with self.assertRaises((claude_pet.CliInstallError, OSError)):
                        stage("https://example.invalid/x", "sha256", digest, opener)
                self.assertEqual(os.listdir(staging), [], "정션인 폴더에 파일을 썼다")

    def test_a_junction_for_the_fake_open_folder_is_refused(self):
        """M3: 가짜 rundll32 폴더가 정션이면 쓰지 않는다 — None(그 주기에는 agy 를 띄우지 않는다)."""
        make = _require("_gemini_fake_rundll_dir")
        self.keep(claude_pet._gemini_cache)
        folder = make()
        self.assertTrue(folder and os.path.isdir(folder), "평소에 폴더를 못 만든다 — 이 테스트의 전제가 틀렸다")
        claude_pet._gemini_cache["open_dir"] = None
        with self.junction(folder):
            self.assertIsNone(make(), "정션인 fake-open 폴더를 그대로 썼다")


# ═════════════════════════════ M2 — 진행 중에는 취소 깃발을 지우지 않는다 ═════════════════════════════

def _run_gui():
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_gui")


_JOBISH = re.compile(r"phase|ai_jobs|busy|idle|running")


def unguarded_clears(fn, table):
    """fn 과 fn 이 부르는 table 안의 함수에서, **일이 도는지 보지 않고** 도는 `<…>.clear()` 호출의 수.
    본다 = 그 호출이 job 을 묻는 If(조건식에 phase·ai_jobs·busy·idle·running 이 나온다) 안에 있거나, 같은
    함수에서 그보다 앞줄에 그런 If 가 return 으로 빠진다."""
    seen, frontier, bad = set(), [fn], 0
    while frontier:
        cur = frontier.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        asks = [n for n in ast.walk(cur) if isinstance(n, ast.If) and _JOBISH.search(ast.unparse(n.test))]
        for node in ast.walk(cur):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", None))
            if name in table:
                frontier.append(table[name])
            if name != "clear" or not isinstance(node.func, ast.Attribute):
                continue
            inside = any(node in ast.walk(i) and node not in ast.walk(i.test) for i in asks)
            left_early = any(i.lineno < node.lineno and any(isinstance(r, ast.Return) for r in ast.walk(i))
                             for i in asks)
            if not (inside or left_early):
                bad += 1
    return bad


class CancelFlagTests(unittest.TestCase):

    def test_the_menu_and_the_pill_do_not_clear_a_running_jobs_cancel_flag(self):
        """M2: 일이 돌고 있을 때 우클릭·필 클릭이 `ai_cancel[...].clear()` 를 하지 않는다 — 방금 누른 [취소]가
        지워져 받기·로그인이 계속된다. idle 일 때만 지운다.
        Rival: 핸들러가 언제나 clear() 부터 함."""
        gui = _run_gui()
        table = {n.name: n for n in ast.walk(gui) if isinstance(n, ast.FunctionDef)}
        for name in ("installClaude_", "loginClaude_", "installCodex_", "loginCodex_", "loginGemini_",
                     "_summary_click_work"):
            with self.subTest(handler=name):
                self.assertIn(name, table)
                self.assertEqual(unguarded_clears(table[name], table), 0,
                                 "%s 가 진행 중인지 보지 않고 취소 깃발을 지운다" % name)


if __name__ == "__main__":
    unittest.main()
