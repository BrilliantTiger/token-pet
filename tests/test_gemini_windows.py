"""계약 v7-W — Windows 에서 Gemini(agy) 사용량 읽기. Verifier(gemini-tests-v2) 작성, 구현 전.

계약: briefs/v7-contract.md 의 W1~W6 과 끝의 "agy 동의" 보완. 이 파일은 **Windows 의 동작**을 가른다 —
macOS 에서는 `sys.platform` 을 "win32" 로 바꿔 돌고, 진짜 Windows(CI)에서는 그대로 돈다. 어느 쪽에서도
진짜 agy·자격 증명 관리자·taskkill·네트워크를 건드리지 않는다: `subprocess.run`/`Popen` 은 전부
대역(WinFake)이고, 그것이 실제로 띄우는 것은 이 파일의 파이썬 에뮬레이터 자식뿐이다.

Developer 는 이 파일의 단언·기대값·픽스처를 고치지 않는다(AGENTS.md §2).

── 이 파일이 정한 이름(코어 `claude_pet.py`) ─────────────────────────────────────────────

  GEMINI_CRED_TARGET = "gemini:antigravity"     자격 증명 관리자 대상 이름(CRED_TYPE_GENERIC)
  GEMINI_CRED_PROBE_FLAG = "--gemini-cred-probe" 앱 자신을 다시 띄울 때 주는 숨은 인자
  parse_gemini_cred_probe(text)                 자식의 stdout → (True, LastWritten 정수) | (False, None)
                                                | (None, None)(모름). 순수, 예외 없음.
  gemini_cred_probe_main()                      자식 쪽 본체 — CredReadW 한 건, RtlZeroMemory + CredFree,
                                                `os.write(1, …)` 로 `1 <LastWritten>` 또는 `0` 만 쓴다.
  _find_agy_cli() / fetch_gemini_usage() / compute_gemini_onboard_state()   macOS 와 같은 이름, win32 갈래.

부모 쪽 관측(대역이 본다): 프로브는 `argv[0] == sys.executable` 이고 argv 에 GEMINI_CRED_PROBE_FLAG 가
있는 자식이다. agy 는 argv[0] 의 파일 이름이 `agy.exe`(또는 `agy`)인 자식, 끝내기는 파일 이름이
`taskkill.exe` 인 자식이다. 그 밖의 어떤 프로세스도 띄우지 않는다(security·cmdkey·powershell 포함).

── 경로 비교 ──────────────────────────────────────────────────────────────────────────

코어의 `_windows_system32()` 는 역슬래시로 잇는다. macOS 에서 그 문자열은 역슬래시가 든 **파일 이름**
이므로, 대역 System32 의 파일은 두 모양(`os.path.join` / 역슬래시) 모두로 만들어 두고 비교는 `norm()` 으로 한다.
"""

import ast
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time as _real_time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import claude_pet  # noqa: E402
except ImportError:
    from windows.win_core import import_core  # noqa: E402
    claude_pet = import_core()

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "claude_pet.py"
PORT_DIR = ROOT / "windows"
REAL_WINDOWS = sys.platform == "win32"
REAL_ENV = dict(os.environ)
_REAL_POPEN = subprocess.Popen
_REAL_RUN = subprocess.run

AGY_ARGS = ["-p", "/usage", "--output-format", "json"]
CREATE_NO_WINDOW = 0x08000000
SHORT = 1.5
_FOREVER = 20
FLAG = "--gemini-cred-probe"
APP_DIR = "me.yeongyu.claudepet"

LOGIN_WAIT_STDERR = (
    "Authentication required. Please visit the URL to log in:\n"
    "  https://accounts.example.invalid/o/oauth2/auth?synthetic=1&state=synthetic\n"
    "\n"
    "Waiting for authentication...\n")
# Windows 에서는 실행 파일 이름이 agy.exe 로 찍힌다(조사 보고 A-4).
LOGIN_EXIT_STDERR = "Error: authentication required. Run 'agy.exe' to log in\n"


def _require(name):
    fn = getattr(claude_pet, name, None)
    if fn is None:
        raise AssertionError("claude_pet.%s 가 없다 — 계약 v7-W 미구현" % name)
    return fn


def norm(path):
    """경로 비교용: 역슬래시·슬래시, 대소문자(Windows)를 가리지 않는다."""
    return os.path.normcase(os.path.normpath(str(path).replace("\\", "/")))


def eget(env, key):
    """env(dict)에서 키를 대소문자 무시로 찾는다 — Windows 의 os.environ 사본은 키가 대문자다."""
    for k, v in env.items():
        if k.upper() == key.upper():
            return v
    return None


def agy_payload():
    return {"schemaVersion": 1, "status": "SUCCESS", "command": {"name": "usage", "data": {"groups": [
        {"name": "Gemini Models", "buckets": [
            {"id": "gemini-weekly", "window": "weekly", "remaining_fraction": 0.75,
             "reset_time": "2099-01-05T00:00:00Z"},
            {"id": "gemini-5h", "window": "5h", "remaining_fraction": 0.4,
             "reset_time": "2099-01-01T05:00:00Z"}]},
        {"name": "Claude and GPT models", "buckets": [
            {"id": "3p-5h", "window": "5h", "remaining_fraction": 0.9,
             "reset_time": "2099-01-01T05:00:00Z"}]}]}}}


# mode → (stdout — None 이면 payload, stderr, 종료 코드, 끝나는 방식)
AGY_MODES = {
    "ok": (None, "", 0, "exit"),
    "fail": ("", "synthetic agy failure\n", 1, "exit"),
    "timeout": ("", "", 0, "forever"),
    "login_wait": ("", LOGIN_WAIT_STDERR, 0, "forever"),
    "login_exit": ("", LOGIN_EXIT_STDERR, 1, "exit"),
}

_EMULATOR = r"""
import json, os, sys, time
spec = json.load(open(sys.argv[1], encoding="utf-8"))
if spec.get("gdir"):
    # agy 가 띄우는 자식의 대역. 살아 있는 동안 심장 박동 파일을 고쳐 쓴다(pid 를 찔러 보지 않으려고).
    import subprocess
    beat = os.path.join(spec["gdir"], "beat-%d" % os.getpid())
    code = ("import os,sys,time\nend=time.time()+%d\n"
            "while time.time()<end:\n"
            "    open(sys.argv[1],'w').write(str(time.time()))\n    time.sleep(0.05)\n" % spec["forever"])
    g = subprocess.Popen([sys.executable, "-I", "-S", "-c", code, beat],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(os.path.join(spec["gdir"], "pids"), "a", encoding="utf-8") as f:
        f.write("%d %d %s\n" % (os.getpid(), g.pid, beat))
sys.stderr.write(spec["stderr"]); sys.stderr.flush()
end = time.time() + spec["forever"]
if spec["how"] == "forever":
    while time.time() < end:
        time.sleep(0.05)
    sys.exit(3)
sys.stdout.write(spec["stdout"]); sys.stdout.flush()
sys.exit(spec["rc"])
"""


class _Child(_REAL_POPEN):
    """에뮬레이터 자식. 끝나지 않는 mode 에서는 기다리는 상한을 자르고, kill/terminate 를 기록한다."""

    _never = None
    _fake = None
    _role = None

    def _clamp(self, timeout):
        if self._never is not None and isinstance(timeout, (int, float)):
            return min(timeout, self._never)
        return timeout

    def communicate(self, input=None, timeout=None):
        return super().communicate(input, self._clamp(timeout))

    def wait(self, timeout=None):
        return super().wait(self._clamp(timeout))

    def kill(self):
        if self._fake is not None and self._role == "agy" and not self._fake.closing:
            self._fake.events.append(("kill", self.pid))
        return super().kill()

    def terminate(self):
        if self._fake is not None and self._role == "agy" and not self._fake.closing:
            self._fake.events.append(("terminate", self.pid))
        return super().terminate()


class WinFake:
    """subprocess.run / Popen 의 대역 — 무엇이든 진짜로는 실행하지 않고 에뮬레이터 자식을 띄운다.

    agy: mode(AGY_MODES) 대로. 프로브(argv 에 FLAG): cred 대로 —
      ("present", n) → "1 n\\n" / "absent" → "0\\n" / "garbage"(종료 0, 뜻 모를 줄) / "crash"(종료 1, 빈 출력)
      / "hang"(끝나지 않음).
    taskkill: 그 pid 의 agy 대역과 그것이 띄운 자식을 진짜로 끝낸다(트리 종료의 대역).
    구현이 준 kwargs 는 기록만 하고, 자식은 진짜 환경으로 띄운다(가짜 SystemRoot 로는 파이썬이 못 뜬다)."""

    def __init__(self, clock):
        self.clock = clock
        self.mode = "ok"
        self.cred = ("present", 133_800_000_000_000_000)
        self.wait = SHORT
        self.calls = []        # agy: (시각, argv, kwargs)
        self.probes = []       # 프로브: (시각, argv, kwargs)
        self.kills = []        # taskkill: (argv, kwargs, 그때 그 pid 의 agy 가 살아 있었나)
        self.events = []       # ("taskkill"|"kill"|"terminate"|"killpg", pid) 순서
        self.other = []        # 그 밖에 띄우려 한 것
        self.children = []
        self._all = []
        self.closing = False
        self._dir = tempfile.mkdtemp(prefix="claudepet-winfake-")
        self._gdir = os.path.join(self._dir, "g")
        os.mkdir(self._gdir)
        self._n = 0
        self._local = threading.local()

    @staticmethod
    def _base(argv):
        return os.path.basename(argv[0].replace("\\", "/")).lower() if argv else ""

    def run(self, argv, *a, **k):
        if isinstance(argv, (str, bytes)) or k.get("shell"):
            self.other.append("shell-string")
            raise AssertionError("문자열 명령 — 셸 없이 argv 목록으로 띄워야 한다")
        argv = [str(x) for x in argv]
        kk = dict(k)
        self._local.run_kwargs = dict(k)
        forever = ((self._base(argv) in ("agy", "agy.exe") and AGY_MODES[self.mode][3] == "forever")
                   or (FLAG in argv and self.cred == "hang"))
        if forever:
            given = kk.get("timeout")
            kk["timeout"] = min(given, self.wait) if isinstance(given, (int, float)) else self.wait
        try:
            return _REAL_RUN(argv, *a, **kk)
        finally:
            self._local.run_kwargs = None

    def popen(self, args, *a, **k):
        if isinstance(args, (str, bytes)) or k.get("shell"):
            self.other.append("shell-string")
            raise AssertionError("문자열 명령 — 셸 없이 argv 목록으로 띄워야 한다")
        argv = [str(x) for x in args]
        given = getattr(self._local, "run_kwargs", None) or dict(k)
        base = self._base(argv)
        never, role, gdir = None, None, None
        if base in ("agy", "agy.exe"):
            role = "agy"
            self.calls.append((self.clock.time(), argv, given))
            stdout, stderr, rc, how = AGY_MODES[self.mode]
            if stdout is None:
                stdout = json.dumps(agy_payload()) + "\n"
            never = self.wait if how == "forever" else None
            gdir = self._gdir if self.mode == "login_wait" else None
        elif FLAG in argv:
            role = "probe"
            self.probes.append((self.clock.time(), argv, given))
            if isinstance(self.cred, tuple):
                stdout, stderr, rc, how = "1 %d\n" % self.cred[1], "", 0, "exit"
            elif self.cred == "absent":
                stdout, stderr, rc, how = "0\n", "", 0, "exit"
            elif self.cred == "garbage":
                stdout, stderr, rc, how = "CredReadW failed: 5\n", "", 0, "exit"
            elif self.cred == "crash":
                stdout, stderr, rc, how = "", "synthetic crash\n", 1, "exit"
            else:
                stdout, stderr, rc, how = "", "", 0, "forever"
                never = self.wait
        elif base == "taskkill.exe":
            role = "taskkill"
            pid = int(argv[argv.index("/PID") + 1]) if "/PID" in argv[:-1] else -1
            target = [c for c in self.children if c.pid == pid]
            self.kills.append((argv, given, bool(target) and target[0].poll() is None))
            self.events.append(("taskkill", pid))
            if "/T" in argv and "/F" in argv:
                self._kill_tree(pid)
            stdout, stderr, rc, how = "SUCCESS: synthetic\n", "", 0, "exit"
        else:
            self.other.append(base)
            stdout, stderr, rc, how = "", "", 1, "exit"
        self._n += 1
        spec = os.path.join(self._dir, "spec-%d.json" % self._n)
        with open(spec, "w", encoding="utf-8") as f:
            json.dump({"stdout": stdout, "stderr": stderr, "rc": rc, "how": how,
                       "forever": _FOREVER, "gdir": gdir}, f)
        k = dict(k)
        for drop in ("executable", "cwd", "env"):
            k.pop(drop, None)
        if not REAL_WINDOWS:
            k.pop("creationflags", None)
            k.pop("startupinfo", None)
        child = _Child([sys.executable, "-I", "-S", "-c", _EMULATOR, spec], *a, env=REAL_ENV, **k)
        child._never, child._fake, child._role = never, self, role
        self._all.append(child)
        if role == "agy":
            self.children.append(child)
        return child

    def _grand(self):
        try:
            with open(os.path.join(self._gdir, "pids"), encoding="utf-8") as f:
                rows = [ln.split(None, 2) for ln in f.read().splitlines() if ln.strip()]
        except OSError:
            return []
        return [(int(p), int(g), beat) for p, g, beat in rows]

    def _kill_tree(self, pid):
        for parent, gpid, _beat in self._grand():
            if parent == pid:
                try:
                    os.kill(gpid, signal.SIGTERM if REAL_WINDOWS else signal.SIGKILL)
                except OSError:
                    pass
        for c in self.children:
            if c.pid == pid and c.poll() is None:
                _REAL_POPEN.kill(c)

    def grandchildren_alive(self):
        """agy 대역이 띄운 자식 중 아직 뛰고 있는 것의 수(심장 박동이 0.6초 안에 바뀌었다)."""
        n = 0
        for _parent, _gpid, beat in self._grand():
            try:
                a = open(beat, encoding="utf-8").read()
            except OSError:
                continue
            _real_time.sleep(0.3)
            try:
                if open(beat, encoding="utf-8").read() != a:
                    n += 1
            except OSError:
                pass
        return n

    def alive(self, grace=2.0):
        end = _real_time.time() + grace
        while _real_time.time() < end and any(c.poll() is None for c in self.children):
            _real_time.sleep(0.02)
        return sum(1 for c in self.children if c.poll() is None) + self.grandchildren_alive()

    def close(self):
        self.closing = True
        for _parent, gpid, _beat in self._grand():
            try:
                os.kill(gpid, signal.SIGTERM if REAL_WINDOWS else signal.SIGKILL)
            except OSError:
                pass
        for c in self._all:
            try:
                if c.poll() is None:
                    _REAL_POPEN.kill(c)
                _REAL_POPEN.wait(c, 5)
                for stream in (c.stdin, c.stdout, c.stderr):
                    if stream is not None:
                        stream.close()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(self._dir, ignore_errors=True)


class _FakeTime:
    """`time` 모듈의 대역 — time() 만 box["now"] 를 읽고 나머지는 진짜다."""

    def __init__(self, box):
        self.box = box

    def time(self):
        return self.box["now"]

    def __getattr__(self, name):
        return getattr(_real_time, name)


def _gemini_dicts():
    return {n: v for n, v in vars(claude_pet).items()
            if isinstance(v, dict) and "gemini" in n.lower()}


PRISTINE = {n: json.loads(json.dumps(v)) if n != "GEMINI_BUCKETS" else dict(v)
            for n, v in _gemini_dicts().items()
            if all(isinstance(x, (str, int, float, bool, type(None))) for x in v.values())}


class WinAgyCase(unittest.TestCase):
    """win32, 홈·LOCALAPPDATA·SystemRoot 는 임시 폴더, agy 는 which 대역, subprocess 는 WinFake."""

    SYSTRAY_A = b"MZ synthetic systray A " + b"\x00" * 41
    SYSTRAY_B = b"MZ synthetic systray B " + b"\x01" * 41          # 크기는 같고 내용이 다르다
    SYSTRAY_C = b"MZ synthetic systray C, longer " + b"\x02" * 200  # 크기도 다르다

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="claudepet-winagy-")
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.home = os.path.join(self.base, "home")
        self.local = os.path.join(self.base, "local")
        self.sysroot = os.path.join(self.base, "sysroot")
        self.tmp = os.path.join(self.base, "tmp")
        for d in (self.home, self.local, self.tmp, os.path.join(self.sysroot, "System32")):
            os.makedirs(d)
        # 진짜 임시 폴더에는 설치된 앱이 쓰는 같은 이름의 폴더가 있을 수 있다 — 이 테스트만의 것으로 바꾼다.
        self._patch(mock.patch.object(tempfile, "tempdir", self.tmp))
        self.write_systray(self.SYSTRAY_A)
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, LOCALAPPDATA=self.local,
                   SystemRoot=self.sysroot, SYSTEMROOT=self.sysroot,
                   PATH=os.pathsep.join([os.path.join(self.base, "p1"), os.path.join(self.base, "p2")]))
        for name in list(env):
            if name.upper() in ("CLAUDE_PET_DEBUG", "ANTIGRAVITY_APP_DATA_DIR", "SSH_TTY", "SSH_CLIENT",
                                "SSH_CONNECTION", "NO_COLOR", "AGY_CLI_DISABLE_AUTO_UPDATE",
                                "NODEFAULTCURRENTDIRECTORYINEXEPATH", "HOMEDRIVE", "HOMEPATH"):
                env.pop(name)
        self._patch(mock.patch.dict(os.environ, env, clear=True))
        self.fallback = os.path.join(self.home, ".gemini", "antigravity-cli", "antigravity-oauth-token")
        self.box = {"now": 1_800_000_000.0}
        self._patch(mock.patch.object(claude_pet, "time", _FakeTime(self.box)))
        self.fake = WinFake(_FakeTime(self.box))
        self.addCleanup(self.fake.close)
        self.agy_path = os.path.join(self.base, "onpath", "agy.exe")
        self.which = {"agy": self.agy_path}
        real_which = shutil.which
        self._patch(mock.patch.object(claude_pet.shutil, "which",
                                      lambda name, *a, **k: self.which.get(name)
                                      if name in self.which else real_which(name, *a, **k)))
        self._patch(mock.patch.object(sys, "platform", "win32"))
        if not REAL_WINDOWS:
            # Windows 에는 없는 것들 — 부르면 진짜 Windows 에서 AttributeError 다.
            def gone(name):
                def boom(*a, **k):
                    if name == "killpg":
                        self.fake.events.append(("killpg", a[0] if a else None))
                    raise AttributeError("module 'os' has no attribute %r (Windows)" % name)
                return boom
            for name in ("getuid", "killpg"):
                self._patch(mock.patch.object(claude_pet.os, name, gone(name)))
        self._patch(mock.patch.object(claude_pet.subprocess, "run", self.fake.run))
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen", self.fake.popen))
        self._patch(mock.patch.object(claude_pet.os, "system",
                                      lambda *a, **k: self.fake.other.append("os.system") or 1))
        self._patch(mock.patch.object(claude_pet, "_dbg", lambda *a, **k: None))
        self._patch(mock.patch("socket.create_connection",
                               side_effect=AssertionError("테스트가 네트워크에 나가려 했다")))
        self.reset_state(first=True)

    def _patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def reset_state(self, first=False):
        """Gemini 모듈 상태를 임포트 시점으로(앱을 다시 켠 것과 같다)."""
        for name, d in _gemini_dicts().items():
            if first:
                snap = dict(d)
                self.addCleanup(lambda d=d, snap=snap: (d.clear(), d.update(snap)))
            if name in PRISTINE:
                d.clear()
                d.update(dict(PRISTINE[name]))
        status = getattr(claude_pet, "GEMINI_STATUS", None)
        if isinstance(status, dict):
            status.update({"auth_error": False, "last_error": None})

    def write_systray(self, body):
        """대역 System32\\systray.exe — 두 모양의 경로 모두에(위 머리 주석)."""
        paths = [os.path.join(self.sysroot, "System32", "systray.exe")]
        if not REAL_WINDOWS:
            paths.append("\\".join([self.sysroot, "System32", "systray.exe"]))
        for p in paths:
            with open(p, "wb") as f:
                f.write(body)

    def never_exits(self, mode):
        self.fake.mode = mode
        if isinstance(getattr(claude_pet, "GEMINI_AGY_TIMEOUT", None), (int, float)):
            self._patch(mock.patch.object(claude_pet, "GEMINI_AGY_TIMEOUT", SHORT))

    def fetch(self):
        return _require("fetch_gemini_usage")()

    def status(self):
        return dict(getattr(claude_pet, "GEMINI_STATUS", {}) or {})

    def later(self, seconds=301):
        self.box["now"] += seconds

    def assert_nothing_else_ran(self):
        self.assertEqual(self.fake.other, [],
                         "agy·프로브·taskkill 말고 다른 것을 띄우려 했다(security·cmdkey·powershell 금지)")

    def assert_probe_call(self, call):
        """W2: 프로브는 앱 자신(sys.executable)을 숨은 인자로 다시 띄운 짧은 자식이다."""
        _t, argv, kw = call
        self.assertEqual(norm(argv[0]), norm(sys.executable), "프로브가 앱 자신이 아니다: %r" % argv[0])
        self.assertIn(FLAG, argv[1:])
        self.assertFalse(kw.get("shell"))
        self.assertTrue(int(kw.get("creationflags") or 0) & CREATE_NO_WINDOW,
                        "프로브를 CREATE_NO_WINDOW 없이 띄웠다 — 콘솔 창이 뜬다")
        joined = " ".join(argv).lower()
        for word in ("cmdkey", "powershell", "credenumerate"):
            self.assertNotIn(word, joined)

    def assert_background_env(self, env, app_env_before):
        """W3·W4: 백그라운드 agy 의 env. 돌려주는 것은 PATH 맨 앞 폴더."""
        self.assertIsInstance(env, dict, "agy 에 env 를 주지 않았다")
        for key in ("SSH_CLIENT", "SSH_TTY", "SSH_CONNECTION"):
            self.assertTrue(eget(env, key) is None, "%s 가 agy 의 env 에 있다" % key)
        self.assertEqual(eget(env, "NO_COLOR"), "1")
        self.assertEqual(eget(env, "AGY_CLI_DISABLE_AUTO_UPDATE"), "1",
                         "조회용 agy 가 자동 업데이터를 띄울 수 있다 — 끊을 때 교체 도중 죽는다")
        self.assertEqual(eget(env, "NoDefaultCurrentDirectoryInExePath"), "1")
        self.assertEqual(norm(eget(env, "USERPROFILE")), norm(self.home), "env 가 os.environ 의 사본이 아니다")
        self.assertTrue(dict(os.environ) == app_env_before, "앱 자신의 환경을 바꿨다")
        parts = (eget(env, "PATH") or "").split(os.pathsep)
        rest = eget(app_env_before, "PATH").split(os.pathsep)
        self.assertTrue(parts[1:] == rest, "원래 PATH 가 순서 그대로 뒤에 붙지 않았다")
        folder = parts[0]
        self.assertEqual(norm(folder), norm(os.path.join(self.local, APP_DIR, "fake-open")),
                         "PATH 맨 앞이 앱 전용 fake-open 폴더가 아니다")
        self.assertTrue(os.path.isdir(folder) and not os.path.islink(folder))
        names = sorted(os.listdir(folder))
        self.assertEqual([n.lower() for n in names], ["rundll32.exe"],
                         "fake-open 폴더에는 rundll32.exe 하나만 있어야 한다 — .cmd/.bat 는 cmd.exe 가 URL 의 "
                         "& 를 명령으로 읽고, .com 은 PATHEXT 에서 .exe 보다 먼저 잡힌다: %r" % names)
        fake = os.path.join(folder, names[0])
        self.assertTrue(stat.S_ISREG(os.lstat(fake).st_mode), "rundll32.exe 가 보통 파일이 아니다(링크?)")
        return folder

    def fake_rundll(self, folder):
        with open(os.path.join(folder, "rundll32.exe"), "rb") as f:
            return f.read()


# ═════════════════════════════ W1 — agy 찾기 ═════════════════════════════


class FindAgyOnWindowsTests(WinAgyCase):

    def places(self):
        return [("which", self.agy_path),
                ("official", os.path.join(self.local, "agy", "bin", "agy.exe")),
                ("dot-local", os.path.join(self.home, ".local", "bin", "agy.exe")),
                ("app-bin", os.path.join(self.local, APP_DIR, "bin", "agy.exe"))]

    def test_the_search_order_puts_the_users_own_installs_before_the_app_bin(self):
        """W1(agy 동의 보완): which("agy") → %LOCALAPPDATA%\\agy\\bin\\agy.exe → %USERPROFILE%\\.local\\bin\\agy.exe
        → 앱 전용 %LOCALAPPDATA%\\me.yeongyu.claudepet\\bin\\agy.exe(마지막). 하나도 없으면 None.
        Rivals: macOS 의 ~/.local/bin/agy(확장자 없음)만 봄 — 공식 설치본을 놓친다; 앱 전용 bin 을 먼저 봄
        (사용자가 깐 것보다 앱이 받은 것을 쓴다, I2 위반); 공식 위치와 .local 의 순서가 바뀜."""
        find = _require("_find_agy_cli")
        places = self.places()
        for _name, path in places[1:]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(b"MZ synthetic agy")
            os.chmod(path, 0o755)
        for n, (name, path) in enumerate(places):
            with self.subTest(first=name):
                got = find()
                self.assertIsNotNone(got, "%s 에 있는 agy.exe 를 찾지 못했다" % name)
                self.assertEqual(norm(got), norm(path))
                if n == 0:
                    self.which["agy"] = None
                else:
                    os.unlink(path)
        self.assertIsNone(find())

    def test_no_agy_is_not_installed_and_nothing_is_spawned(self):
        """agy 가 어디에도 없으면 프로브도 agy 도 띄우지 않는다 — None, "not_installed", auth_error False.
        Rival: 없는데 자격 증명을 먼저 확인함; 없음을 로그인 필요로 보임."""
        self.which["agy"] = None
        self.assertIsNone(self.fetch())
        self.assertEqual((self.fake.calls, self.fake.probes), ([], []))
        self.assertEqual(self.status().get("last_error"), "not_installed")
        self.assertIs(self.status().get("auth_error"), False)
        self.assert_nothing_else_ran()


# ═════════════════════════════ W2 — 프로브 ═════════════════════════════


class CredProbeParseTests(unittest.TestCase):

    def test_only_the_two_exact_shapes_mean_something(self):
        """`1 <LastWritten 정수>` = 있음, `0` = 없음(앞뒤 공백·줄바꿈 허용). 그 밖은 전부 모름 — 예외 없이.
        Rivals: 빈 출력을 없음으로(프로브가 죽으면 로그인된 사용자의 행이 사라진다); "1" 만 보고 있음으로
        (지문이 없어 재로그인을 못 알아챈다); 첫 글자만 봄("10" 을 있음으로); 뜻 모를 줄에 예외."""
        parse = _require("parse_gemini_cred_probe")
        n = 133_800_000_000_000_000
        good = [("1 %d" % n, (True, n)), ("1 %d\n" % n, (True, n)), ("  1 %d\r\n" % n, (True, n)),
                ("1 0", (True, 0)), ("0", (False, None)), ("0\n", (False, None)), (" 0 \r\n", (False, None)),
                (b"1 7\n", (True, 7)), (b"0\n", (False, None))]
        for text, want in good:
            with self.subTest(text=text):
                self.assertEqual(tuple(parse(text)), want)
        for text in ("", "\n", "1", "1 ", "1 abc", "1 -5", "1 1.5", "1 5 6", "0 3", "00", "10", "2",
                     "2 5", "true", "1\n5", "0\n0", "CredReadW failed: 5", "1 5\nextra", None, 5, b"\xff\xfe",
                     ["1", "5"], "1 " + "9" * 400):
            with self.subTest(text=text):
                try:
                    got = parse(text)
                except Exception as e:  # noqa: BLE001
                    self.fail("예외: %s" % type(e).__name__)
                self.assertEqual(tuple(got), (None, None))


def _core_tree():
    return ast.parse(CORE.read_text(encoding="utf-8"))


def _func(tree, name):
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[0] if found else None


def _reach(tree, name, depth=3):
    """name 과, 거기서 이름으로 부르는 같은 모듈의 함수들(depth 겹)."""
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    seen, frontier = {}, [name]
    for _ in range(depth + 1):
        nxt = []
        for fn in frontier:
            if fn in funcs and fn not in seen:
                seen[fn] = funcs[fn]
                nxt += [c.func.id for c in ast.walk(funcs[fn])
                        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
        frontier = nxt
    return list(seen.values())


def _code_words(node):
    """코드로 쓰인 이름·속성·문자열 상수(문서 문자열 제외)."""
    doc = set()
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Module, ast.AsyncFunctionDef)):
            b = n.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                    and isinstance(b[0].value.value, str):
                doc.add(id(b[0].value))
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.Attribute):
            out.append(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc:
            out.append(n.value)
    return out


class CredProbeChildTests(unittest.TestCase):
    """자식 쪽(gemini_cred_probe_main)은 진짜 자격 증명 관리자를 부르므로 실행하지 않고 코드로 본다."""

    def test_the_names_this_contract_fixed_exist(self):
        self.assertEqual(getattr(claude_pet, "GEMINI_CRED_TARGET", None), "gemini:antigravity")
        self.assertEqual(getattr(claude_pet, "GEMINI_CRED_PROBE_FLAG", None), FLAG)
        self.assertTrue(callable(getattr(claude_pet, "gemini_cred_probe_main", None)),
                        "claude_pet.gemini_cred_probe_main 이 없다")

    def test_the_child_reads_one_credential_wipes_it_and_writes_with_os_write(self):
        """W2: CredReadW 한 건 → LastWritten 만 꺼냄 → RtlZeroMemory + CredFree → `os.write(1, …)`.
        ERROR_NOT_FOUND(1168)만 "0" 이다. agy 동의 보완: 창 없는 앱의 자식은 sys.stdout 이 None 일 수 있다.
        Rivals: print()/sys.stdout.write(창 없는 빌드에서 AttributeError — 언제나 "모름"); blob 을 지우지
        않고 CredFree 만; 모든 실패를 "0" 으로(접근 거부를 로그인 안 됨으로 본다)."""
        tree = _core_tree()
        self.assertIsNotNone(_func(tree, "gemini_cred_probe_main"), "gemini_cred_probe_main 이 없다")
        funcs = _reach(tree, "gemini_cred_probe_main")
        words = [w for fn in funcs for w in _code_words(fn)]
        for need in ("CredReadW", "CredFree", "RtlZeroMemory"):
            self.assertTrue(any(need in w for w in words), "자식이 %s 를 쓰지 않는다" % need)
        self.assertTrue("GEMINI_CRED_TARGET" in words or "gemini:antigravity" in words,
                        "자식이 gemini:antigravity 를 읽지 않는다")
        consts = [n.value for fn in funcs for n in ast.walk(fn) if isinstance(n, ast.Constant)]
        self.assertIn(1168, consts, "ERROR_NOT_FOUND(1168)를 가려 보지 않는다 — 그것만 '없음'이다")
        writes = [c for fn in funcs for c in ast.walk(fn)
                  if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "write"
                  and isinstance(c.func.value, ast.Name) and c.func.value.id == "os"
                  and c.args and isinstance(c.args[0], ast.Constant) and c.args[0].value == 1]
        self.assertTrue(writes, "자식이 os.write(1, …) 로 쓰지 않는다")
        self.assertFalse(any(w in ("print", "stdout") for w in words),
                         "자식이 print/sys.stdout 을 쓴다 — 창 없는 빌드에서는 None 이다")

    def test_nothing_enumerates_credentials_or_shells_out_to_cmdkey(self):
        """W2: CredEnumerateW(다른 모든 자격 증명의 비밀값까지 메모리에 올린다)·cmdkey(종료 코드가 언제나 0,
        수정 시각이 없다) 금지 — 코어와 포트의 코드 어디에도(주석·문서 문자열은 괜찮다)."""
        files = [CORE] + sorted(PORT_DIR.glob("*.py"))
        for path in files:
            words = _code_words(ast.parse(path.read_text(encoding="utf-8")))
            for banned in ("credenumerate", "cmdkey"):
                hits = [w for w in words if banned in w.lower()]
                self.assertEqual(hits, [], "%s 에 %s" % (path.name, banned))

    def test_the_port_answers_the_probe_flag_before_it_becomes_an_app(self):
        """배포판에서 sys.executable 은 포트의 exe 다 — 그 main() 이 QApplication 을 만들기 **전에** 숨은
        인자를 보고 gemini_cred_probe_main 으로 가야 한다.
        Rival: 코어에만 갈래를 둠(자식이 펫 창을 하나 더 띄우거나 단일 인스턴스 뮤텍스에 걸려 조용히 끝난다
        — 프로브는 언제나 "모름")."""
        tree = ast.parse((PORT_DIR / "claude_pet_win.py").read_text(encoding="utf-8"))
        main = _func(tree, "main")
        self.assertIsNotNone(main)

        def lines(pred):
            return [c.lineno for c in ast.walk(main) if isinstance(c, ast.Call) and pred(c.func)]

        probe = lines(lambda f: (isinstance(f, ast.Attribute) and f.attr == "gemini_cred_probe_main")
                      or (isinstance(f, ast.Name) and f.id == "gemini_cred_probe_main"))
        self.assertTrue(probe, "포트의 main() 이 gemini_cred_probe_main 을 부르지 않는다")
        for later in ("QApplication", "acquire_single_instance_mutex", "claim_windows_app_identity"):
            at = lines(lambda f, later=later: isinstance(f, ast.Name) and f.id == later)
            self.assertTrue(at and min(probe) < min(at), "프로브 갈래가 %s 보다 뒤에 있다" % later)
        self.assertTrue(any("GEMINI_CRED_PROBE_FLAG" == w for w in _code_words(main)),
                        "main() 이 GEMINI_CRED_PROBE_FLAG 를 보지 않는다")


# ═════════════════════════════ W2~W5 — 읽기 한 번 ═════════════════════════════


class FetchOnWindowsTests(WinAgyCase):

    def test_one_read_is_a_probe_then_agy_with_no_window_in_an_empty_dir(self):
        """W2·W3·W4·W5: 프로브 한 번(앱 자신 + 숨은 인자, CREATE_NO_WINDOW) → agy 한 번
        (`[agy.exe, -p, /usage, --output-format, json]`, 셸 없음, CREATE_NO_WINDOW, 빈 전용 cwd, env 는
        os.environ 의 사본에서 SSH_* 를 빼고 NO_COLOR·AGY_CLI_DISABLE_AUTO_UPDATE·
        NoDefaultCurrentDirectoryInExePath 를 넣고 PATH 맨 앞에 fake-open). fake-open 의 rundll32.exe 는 이
        기기 System32\\systray.exe 의 사본이다. 끝낼 일이 없으면 taskkill 을 띄우지 않는다.
        Rivals: macOS 갈래 그대로(security — Windows 에 없다); CREATE_NO_WINDOW 없음(콘솔 창이 번쩍인다);
        가짜 open 이 `open` 셸 스크립트(Windows 의 agy 는 rundll32 를 부른다); rundll32.cmd/.bat; fake-open 을
        임시 폴더에(계약은 앱 전용 폴더); PATH 끝에 둠; SSH_* 를 그대로 둠; 앱 환경을 고침."""
        self._patch(mock.patch.dict(os.environ, {"SSH_TTY": "synthetic", "SSH_CLIENT": "192.0.2.1 1 22",
                                                 "SSH_CONNECTION": "192.0.2.1 1 192.0.2.2 22"}))
        before = dict(os.environ)
        rows = self.fetch()
        self.assertEqual(len(self.fake.probes), 1, "자격 증명 확인(프로브)을 정확히 한 번 해야 한다")
        self.assert_probe_call(self.fake.probes[0])
        self.assertEqual(len(self.fake.calls), 1, "agy 를 정확히 한 번 띄워야 한다")
        _t, argv, kw = self.fake.calls[0]
        self.assertEqual([norm(argv[0])] + argv[1:], [norm(self.agy_path)] + AGY_ARGS)
        self.assertFalse(kw.get("shell"))
        self.assertTrue(int(kw.get("creationflags") or 0) & CREATE_NO_WINDOW,
                        "agy 를 CREATE_NO_WINDOW 없이 띄웠다")
        cwd = kw.get("cwd")
        self.assertIsNotNone(cwd, "cwd 를 정하지 않았다")
        real = os.path.realpath(str(cwd))
        self.assertTrue(real.startswith(os.path.realpath(self.tmp) + os.sep)
                        or real.startswith(os.path.realpath(self.local) + os.sep),
                        "cwd 가 임시 폴더·앱 폴더 아래가 아니다: %r" % cwd)
        self.assertEqual(os.listdir(str(cwd)), [], "agy 의 작업 폴더가 비어 있지 않다")
        folder = self.assert_background_env(kw.get("env"), before)
        self.assertEqual(self.fake_rundll(folder), self.SYSTRAY_A, "rundll32.exe 가 systray.exe 의 사본이 아니다")
        self.assertEqual(self.fake.kills, [], "끝낼 것이 없는데 taskkill 을 띄웠다")
        self.assertEqual(self.fake.events, [])
        self.assert_nothing_else_ran()
        self.assertTrue(rows)
        self.assertEqual(rows[0][0], "gemini")
        self.assertAlmostEqual(rows[0][1], 60.0, places=6)
        self.assertEqual([r[0] for r in rows[1:]],
                         ["gemini_group:gemini-weekly", "gemini_group:gemini-5h", "gemini_group:3p-5h"])
        self.assertEqual((self.status().get("last_error"), self.status().get("auth_error")), (None, False))

    def test_the_fake_rundll32_is_checked_against_this_machines_systray_before_every_run(self):
        """W3(agy 동의 보완): 매 실행 전 **이 기기의 지금 System32\\systray.exe** 와 크기·해시를 대조해 다르면
        다시 복사한다(고정 해시 상수 금지 — Windows 업데이트가 systray.exe 를 바꾼다). 지워졌으면 다시 만든다.
        Rivals: 한 번만 복사; 파일이 있는지만 봄; 크기만 봄(크기가 같은 바꿔치기를 못 본다); 고정 해시 상수
        (업데이트 뒤 영원히 불일치 → 영원히 못 읽는다)."""
        before = dict(os.environ)
        self.assertTrue(self.fetch())
        folder = self.assert_background_env(self.fake.calls[0][2].get("env"), before)
        target = os.path.join(folder, "rundll32.exe")

        def tamper_same_size():
            with open(target, "wb") as f:
                f.write(b"X" * len(self.SYSTRAY_A))

        def add_a_batch_file():
            with open(os.path.join(folder, "rundll32.cmd"), "w") as f:
                f.write("@exit /b 0\r\n")

        steps = [("사본이 지워짐", lambda: os.unlink(target), self.SYSTRAY_A),
                 ("폴더가 지워짐", lambda: shutil.rmtree(folder), self.SYSTRAY_A),
                 ("사본이 같은 크기로 바뀜", tamper_same_size, self.SYSTRAY_A),
                 ("systray.exe 가 같은 크기로 바뀜(업데이트)", lambda: self.write_systray(self.SYSTRAY_B),
                  self.SYSTRAY_B),
                 ("systray.exe 의 크기가 바뀜", lambda: self.write_systray(self.SYSTRAY_C), self.SYSTRAY_C),
                 ("누가 rundll32.cmd 를 넣음", add_a_batch_file, self.SYSTRAY_C)]
        for n, (name, change, want) in enumerate(steps, start=1):
            with self.subTest(step=name):
                change()
                self.later()
                self.assertTrue(self.fetch())
                self.assertEqual(len(self.fake.calls), n + 1, "다음 주기에 agy 를 띄우지 않았다")
                folder = self.assert_background_env(self.fake.calls[n][2].get("env"), before)
                target = os.path.join(folder, "rundll32.exe")
                self.assertEqual(self.fake_rundll(folder), want)

    def test_without_a_systray_to_copy_agy_is_not_run_at_all(self):
        """브라우저를 막지 못한 채로는 띄우지 않는다(macOS 의 "가짜 open 을 못 만들면 실행하지 않는다"와 같다).
        Rival: 그냥 띄움 — 로그인이 필요해진 agy 가 진짜 rundll32 로 브라우저를 연다."""
        for p in (os.path.join(self.sysroot, "System32", "systray.exe"),
                  "\\".join([self.sysroot, "System32", "systray.exe"])):
            if os.path.exists(p):
                os.unlink(p)
        self.assertIsNone(self.fetch())
        self.assertEqual(self.fake.calls, [], "가짜 rundll32 없이 agy 를 띄웠다")
        self.assertIs(self.status().get("auth_error"), False)

    def test_the_fallback_token_file_is_only_statted(self):
        """W2: 자격 증명이 없어도 %USERPROFILE%\\.gemini\\antigravity-cli\\antigravity-oauth-token 이 있으면
        읽는다. 그 파일은 열지 않는다(stat 만).
        Rival: 자격 증명 관리자만 봄(2560바이트를 넘는 토큰은 agy 가 파일에 둔다); 파일을 열어 읽음."""
        self.fake.cred = "absent"
        os.makedirs(os.path.dirname(self.fallback))
        with open(self.fallback, "w", encoding="utf-8") as f:
            f.write("{}")
        opened = []
        real_open, real_os_open = open, os.open

        def spy_open(file, *a, **k):
            opened.append(str(file))
            return real_open(file, *a, **k)

        def spy_os_open(path, *a, **k):
            opened.append(str(path))
            return real_os_open(path, *a, **k)

        with mock.patch("builtins.open", spy_open), mock.patch.object(claude_pet.os, "open", spy_os_open):
            rows = self.fetch()
        self.assertTrue(rows, "폴백 파일이 있는데 읽지 않았다")
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual([p for p in opened if norm(p) == norm(self.fallback)], [], "폴백 토큰 파일을 열었다")


class EndingAgyOnWindowsTests(WinAgyCase):

    def assert_tree_was_ended_by_taskkill(self):
        self.assertEqual(len(self.fake.kills), 1, "taskkill 을 정확히 한 번 띄워야 한다: %r" % self.fake.events)
        argv, kw, parent_alive = self.fake.kills[0]
        pid = self.fake.children[0].pid
        self.assertEqual(norm(argv[0]), norm("\\".join([self.sysroot, "System32", "taskkill.exe"])),
                         "taskkill 을 System32 의 절대 경로로 부르지 않았다(PATH 를 믿지 않는다)")
        self.assertEqual(sorted(argv[1:]), sorted(["/PID", str(pid), "/T", "/F"]))
        self.assertEqual(argv[argv.index("/PID") + 1], str(pid))
        self.assertFalse(kw.get("shell"))
        self.assertTrue(int(kw.get("creationflags") or 0) & CREATE_NO_WINDOW,
                        "taskkill 을 CREATE_NO_WINDOW 없이 띄웠다")
        self.assertTrue(parent_alive, "taskkill 을 부를 때 agy 가 이미 죽어 있었다")
        self.assertEqual(self.fake.events[0], ("taskkill", pid),
                         "taskkill 보다 먼저 agy 를 죽였다 — 죽은 부모 pid 로는 자식 트리를 못 찾는다: %r"
                         % self.fake.events)
        self.assertFalse([e for e in self.fake.events if e[0] == "killpg"], "os.killpg 는 Windows 에 없다")
        self.assertEqual(self.fake.alive(), 0, "agy 나 그것이 띄운 프로세스가 남았다")
        self.assertIsNotNone(self.fake.children[0].returncode, "끝낸 agy 를 거두지(wait) 않았다")

    def test_agy_asking_for_a_login_is_ended_at_once_with_taskkill_while_it_is_alive(self):
        """W5: stderr 에 로그인 요구가 보이면 **부모가 살아 있을 때** `System32\\taskkill.exe /PID <pid> /T /F`
        (CREATE_NO_WINDOW) → wait. 행 없음, "login"/auth_error True. 30초를 기다리지 않는다.
        Rivals: proc.kill() 만(agy 가 띄운 자식이 남고 파이프를 쥔다); kill 뒤 taskkill(이미 죽은 pid);
        os.killpg(Windows 에 없다); /T 없음; PATH 의 taskkill; 창이 뜨는 taskkill."""
        self.never_exits("login_wait")
        t0 = _real_time.time()
        self.assertIsNone(self.fetch())
        self.assertLess(_real_time.time() - t0, SHORT, "로그인 요구를 보고도 상한까지 기다렸다")
        self.assertEqual(len(self.fake.calls), 1)
        self.assert_tree_was_ended_by_taskkill()
        self.assertEqual((self.status().get("last_error"), self.status().get("auth_error")), ("login", True))
        self.assert_nothing_else_ran()

    def test_a_timeout_ends_the_tree_the_same_way_and_is_not_a_login(self):
        """W5: 시간 초과도 같은 방법으로 끝낸다 — "timeout", auth_error False."""
        self.never_exits("timeout")
        self.assertIsNone(self.fetch())
        self.assert_tree_was_ended_by_taskkill()
        self.assertEqual((self.status().get("last_error"), self.status().get("auth_error")), ("timeout", False))

    def test_an_immediate_login_error_names_agy_exe_and_is_still_login(self):
        """Windows 의 즉시 종료 문구는 `Run 'agy.exe' to log in` 이다 — 그래도 "login"."""
        self.fake.mode = "login_exit"
        self.assertIsNone(self.fetch())
        self.assertEqual((self.status().get("last_error"), self.status().get("auth_error")), ("login", True))
        self.assertEqual(self.fake.alive(), 0)


# ═════════════════════════════ W6 — 로그인 지문·멈춤·복구 ═════════════════════════════


class LoginMarkerOnWindowsTests(WinAgyCase):

    def test_without_a_credential_or_fallback_agy_is_never_run_and_the_menu_offers_login(self):
        """항목도 폴백 파일도 없으면 agy 실행 0회, 행 없음, "login"/auth_error True. 우클릭 메뉴 깃발은
        "login"(Windows 에서도). 다섯 주기를 돌아도 0회다.
        Rivals: 확인 없이 agy 를 띄움(로그인 절차가 시작된다); compute_gemini_onboard_state 가 darwin 이
        아니면 None(Windows 사용자는 로그인 메뉴를 못 본다)."""
        self.fake.cred = "absent"
        for _ in range(5):
            self.assertIsNone(self.fetch())
            self.later()
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(self.fake.probes)
        for call in self.fake.probes:
            self.assert_probe_call(call)
        self.assertEqual((self.status().get("last_error"), self.status().get("auth_error")), ("login", True))
        runtime = dict(claude_pet.RUNTIME, show_gemini=True, gemini_gauges=["gemini"])
        self.assertEqual(_require("compute_gemini_onboard_state")(runtime), "login")
        self.assertIsNone(_require("compute_gemini_onboard_state")(dict(runtime, show_gemini=False)))
        self.assert_nothing_else_ran()

    def test_after_a_login_demand_nothing_runs_until_last_written_changes(self):
        """agy 가 로그인을 요구하면 그때의 지문(LastWritten)을 기억하고 자동 실행을 멈춘다. 지문이 그대로인
        동안 5분마다 프로브만 한다. LastWritten 이 달라지면(사용자가 로그인을 마쳤다) **클릭 없이** 다시 읽는다.
        Rivals: 5분마다 agy 를 다시 띄움(로그인 절차를 되풀이); 한 번 멈추면 클릭 없이는 영영 안 읽음;
        있음/없음만 봄(로그아웃 뒤에도 항목은 남으므로 재로그인을 못 알아챈다)."""
        self.never_exits("login_wait")
        self.assertIsNone(self.fetch())
        self.assertEqual(len(self.fake.calls), 1)
        probes = len(self.fake.probes)
        for _ in range(3):
            self.later()
            self.assertIsNone(self.fetch())
        self.assertEqual(len(self.fake.calls), 1, "지문이 그대로인데 agy 를 다시 띄웠다")
        self.assertGreater(len(self.fake.probes), probes, "멈춘 동안 지문을 다시 보지 않았다")
        self.assertIs(self.status().get("auth_error"), True)
        self.fake.mode = "ok"
        self.fake.cred = ("present", self.fake.cred[1] + 5_000_000)
        self.later()
        rows = self.fetch()
        if not rows:                         # 지문 변화를 본 주기와 읽는 주기가 달라도 된다
            self.later(61)
            rows = self.fetch()
        self.assertTrue(rows, "LastWritten 이 바뀌었는데 다시 읽지 않았다")
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual((self.status().get("last_error"), self.status().get("auth_error")), (None, False))

    def test_a_probe_that_did_not_answer_skips_the_cycle_and_keeps_what_was_shown(self):
        """W2: 프로브가 `1 <n>`·`0` 밖의 답을 내면(뜻 모를 줄·죽음·멈춤) "모름" — 그 주기를 건너뛴다. agy 를
        띄우지 않고, 직전 행과 상태를 그대로 둔다. 다음 주기에 프로브가 답하면 다시 읽는다.
        Rivals: 모름을 없음으로(로그인된 사용자의 숫자가 사라지고 로그인 메뉴가 뜬다); 모름을 있음으로 보고
        agy 를 띄움; 예외로 워커가 죽음."""
        first = self.fetch()
        self.assertTrue(first)
        for kind in ("garbage", "crash", "hang"):
            with self.subTest(probe=kind):
                self.fake.cred = kind
                self.later()
                try:
                    rows = self.fetch()
                except Exception as e:  # noqa: BLE001
                    self.fail("예외: %s" % type(e).__name__)
                self.assertEqual(rows, first, "모름인데 직전 행을 버렸다")
                self.assertEqual(len(self.fake.calls), 1, "모름인데 agy 를 띄웠다")
                self.assertEqual((self.status().get("last_error"), self.status().get("auth_error")),
                                 (None, False))
        self.fake.cred = ("present", 133_800_000_000_000_000)
        self.later()
        self.assertTrue(self.fetch())
        self.assertEqual(len(self.fake.calls), 2)

    def test_an_unknown_first_answer_runs_nothing_and_claims_nothing(self):
        """처음부터 모름이면 agy 를 띄우지 않고 로그인 안 됨이라고도 하지 않는다."""
        self.fake.cred = "garbage"
        self.assertIsNone(self.fetch())
        self.assertEqual(self.fake.calls, [])
        self.assertIs(self.status().get("auth_error"), False)

    def test_reads_are_five_minutes_apart(self):
        """W6: 자동 실행은 300초에 한 번 — 그 사이의 새로고침(30초)은 아무것도 띄우지 않는다."""
        first = self.fetch()
        self.assertTrue(first)
        probes = len(self.fake.probes)
        for _ in range(9):
            self.later(30)
            self.assertEqual(self.fetch(), first)
        self.assertEqual((len(self.fake.calls), len(self.fake.probes)), (1, probes))
        self.later(31)
        self.assertTrue(self.fetch())
        self.assertEqual(len(self.fake.calls), 2)


if __name__ == "__main__":
    unittest.main()
