"""TOK-62 — 제공자 × 상태 × 동작 시나리오 표. macOS·Windows 호스트 러너에서 둘 다 돈다.

1.2.0 은 CI 를 통과하고도 실기기에서 바로 터졌다(TOK-61): Gemini 에 이미 로그인돼 있는데 사용량 읽기가
인증서(x509) 오류로 실패하자 설정이 [로그인]을 내밀었고, 그 창은 agy 가 오류로 곧장 끝났는데도 "시간이
지났어요"를 찍었다. 기능별 테스트는 있었지만 **상태를 조합한** 테스트가 없었다. 이 파일이 그 표다.

기준(대표님, 2026-11-19): "이미 로그인되어있으면 … 로그인이 왜 필요해! 그냥 바로 로딩되서 가져와야지!"
  · 로그인 정보가 있으면 [로그인]을 보여 주지도 묻지도 않고 바로 사용량을 읽는다.
  · 읽기가 네트워크·인증서·서버 오류로 실패하면 로그인을 유도하지 않고, 다음 차례에 스스로 다시 읽는다.
  · [로그인]은 로그인 정보가 없거나 CLI·서버가 로그인을 요구했을 때만.
  · 로그인 창은 오류로 끝난 것을 "시간 초과"라고 하지 않는다.

── 표 ────────────────────────────────────────────────────────────────────────────────

  제공자  claude · codex · gemini
  상태    not_installed      CLI 없음
          installed_no_login CLI 만 있음(로그인 정보 없음)
          logged_in_ok       로그인됨, 읽기 성공
          logged_in_x509     로그인됨, 읽기가 인증서 오류
          logged_in_network  로그인됨, 읽기가 네트워크 오류
          logged_in_server   로그인됨, 읽기가 서버 오류(5xx)
          login_required     로그인 정보는 남아 있는데 서버·CLI 가 로그인을 요구(만료·로그아웃)
  동작    row      첫 새로고침 뒤 설정 "AI 연결" 줄(상태·버튼), 읽기를 시도했는가, 값이 바로 보이는가
          press    그 줄에서 흐름을 시작했을 때: 설치 횟수, 로그인 실행 횟수(창·프로세스), 그 뒤 값
          recover  (오류 상태) 로그인 없이 스스로 다시 읽어 값이 뜨고, 다시 실패해도 직전 값이 남는가
  로그인 창 스크립트(Gemini 만 창을 쓴다) × 4개 언어 × agy 의 끝(성공·인증서·네트워크·서버·진짜 시간 초과)

── 대역 ──────────────────────────────────────────────────────────────────────────────

실제 네트워크·실제 자격 정보·실제 CLI 는 쓰지 않는다. 테스트마다 임시 폴더에:
  · 가짜 CLI — 정해진 stdout·stderr·종료 코드를 내는 작은 파이썬 스크립트(_FAKE_CLI)와 그것을 부르는
    래퍼(`claude`/`codex`/`agy`, Windows 는 `.cmd`). 앱이 **진짜 프로세스로** 띄운다.
  · 가짜 자격 정보 — 임시 홈의 `.claude/.credentials.json`, `.codex/auth.json`(합성 토큰), 그리고 agy 의
    키체인 항목을 대신하는 `creds.json`. macOS 에서는 PATH 맨 앞의 가짜 `security` 가 그것을 읽어 답하고
    (`-w`·`-g` 를 받으면 기록을 남겨 테스트가 실패한다), Windows 에서는 자격 증명 프로브를 같은 파일로 바꾼다.
  · 서버 — `urllib.request.urlopen` 대역. 모르는 주소가 오면 기록하고 테스트가 실패한다.
  · 로그인 창 — macOS 의 `_run_in_terminal`, Windows 의 새 콘솔 Popen 을 가로채 **그 스크립트를 그대로**
    bash / PowerShell 로 돌리고 출력을 받는다. Terminal 도 콘솔 창도 브라우저도 열리지 않는다.
  · Claude 로그인 job — `_run_refresh_job` 만 대역이다(launchd·WMI 를 타지 않고 같은 argv 를 바로 돌린다).
"""

import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import claude_pet  # noqa: E402
except ImportError:
    from windows.win_core import import_core  # noqa: E402
    claude_pet = import_core()

WIN = sys.platform == "win32"
_REAL_POPEN = subprocess.Popen
_REAL_RUN = subprocess.run
_REAL_EXISTS = os.path.exists
_REAL_URLOPEN = urllib.request.urlopen

PROVIDERS = ("claude", "codex", "gemini")
EXE = {"claude": "claude", "codex": "codex", "gemini": "agy"}
LANGS = ("en", "ko", "ja", "es")
ERROR_STATES = ("logged_in_x509", "logged_in_network", "logged_in_server")
STATES = ("not_installed", "installed_no_login", "logged_in_ok") + ERROR_STATES + ("login_required",)

X509_TEXT = ('error: Eligibility check failed: Post "https://daily-cloudcode-pa.googleapis.com/'
             'v1internal:loadCodeAssist": tls: failed to verify certificate: x509: certificate signed '
             'by unknown authority')
NETWORK_TEXT = "error: authentication failed: token refresh failed due to network error"
SERVER_TEXT = "error: Eligibility check failed: 503 Service Unavailable"
LOGIN_TEXT = "Authentication required. Please visit the URL to log in: https://login.invalid/synthetic"
TIMEOUT_TEXT = "error: authentication failed or timed out"

# 가짜 CLI 본체. argv[1] 이 어느 CLI 인지, 나머지가 그 CLI 가 받은 인자다. 무엇을 할지는 behaviour.json
# 이 정하고, 불린 것은 calls.log 에 한 줄씩 남긴다(인자와 창 여부뿐 — 환경은 적지 않는다).
_FAKE_CLI = r'''
import json, os, sys, time
BOX = os.path.dirname(os.path.abspath(__file__))
name, args = sys.argv[1], sys.argv[2:]
window = os.environ.get("FAKE_CLI_WINDOW") == "1"

def load(leaf):
    with open(os.path.join(BOX, leaf), encoding="utf-8") as f:
        return json.load(f)

def save(leaf, obj):
    tmp = os.path.join(BOX, leaf + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, os.path.join(BOX, leaf))

def err(text):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()

with open(os.path.join(BOX, "calls.log"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"cli": name, "args": args, "window": window}) + "\n")
beh = load("behaviour.json").get(name, {})
home = os.path.expanduser("~")

if name == "security":
    if "-w" in args or "-g" in args:
        with open(os.path.join(BOX, "tripwire.log"), "a", encoding="utf-8") as f:
            f.write("security asked for a secret\n")
        sys.exit(1)
    service = args[args.index("-s") + 1] if "-s" in args else ""
    mdat = load("creds.json").get("gemini") if service == "gemini" else None
    if not mdat:
        err("security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.")
        sys.exit(44)
    print('keychain: "synthetic.keychain-db"\nattributes:\n    "mdat"<timedate>=0x3230  "%s\\000"' % mdat)
    sys.exit(0)

if name == "agy":
    mode = beh.get("window" if window else "bg", "x509")
    payload = {"status": "SUCCESS", "command": {"name": "usage", "data": {"groups": [
        {"name": "Gemini Models", "buckets": [
            {"id": "gemini-5h", "window": "5h", "remaining_fraction": 0.58,
             "reset_time": "2099-01-01T00:00:00Z"}]}]}}}
    if mode == "ok":
        print(json.dumps(payload))
        sys.exit(0)
    if mode == "signin":
        err("Authentication required. Please visit the URL to log in: https://login.invalid/synthetic")
        creds = load("creds.json")
        creds["gemini"] = "2099%010dZ" % (time.time_ns() % 10 ** 10)
        save("creds.json", creds)
        all_beh = load("behaviour.json")
        all_beh["agy"]["bg"] = "ok"
        save("behaviour.json", all_beh)
        print(json.dumps(payload))
        sys.exit(0)
    if mode == "login_required":
        err("Authentication required. Please visit the URL to log in: https://login.invalid/synthetic")
        time.sleep(30)           # 진짜 agy 는 60초를 기다린다 — 앱이 그 전에 끝내야 한다
        sys.exit(1)
    if mode == "timeout":
        err("Authentication required. Please visit the URL to log in: https://login.invalid/synthetic")
        err("error: authentication failed or timed out")
        sys.exit(1)
    err({"x509": __X509__, "network": __NETWORK__, "server": __SERVER__}[mode])
    sys.exit(1)

if name == "codex" and args[:1] == ["login"]:
    if beh.get("login", "ok") != "ok":
        sys.exit(1)
    root = (os.environ.get("CODEX_HOME") or "").strip() or os.path.join(home, ".codex")
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "auth.json"), "w", encoding="utf-8") as f:
        json.dump({"tokens": {"access_token": "synthetic-fresh-codex", "account_id": "synthetic"}}, f)
    sys.exit(0)

if name == "claude" and args[:2] == ["auth", "login"]:
    if beh.get("login", "ok") != "ok":
        sys.exit(1)
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
    with open(os.path.join(home, ".claude", ".credentials.json"), "w", encoding="utf-8") as f:
        json.dump({"claudeAiOauth": {"accessToken": "synthetic-fresh-claude"}}, f)
    sys.exit(0)

sys.exit(0)
'''.replace("__X509__", repr(X509_TEXT)).replace("__NETWORK__", repr(NETWORK_TEXT)).replace(
    "__SERVER__", repr(SERVER_TEXT))

CLAUDE_BODY = json.dumps({"limits": [
    {"kind": "five_hour", "percent": 42, "resets_at": None},
    {"kind": "seven_day", "percent": 17, "resets_at": None},
]}).encode()
CODEX_BODY = json.dumps({"plan_type": "plus", "rate_limit": {
    "primary_window": {"used_percent": 31, "limit_window_seconds": 18000, "reset_at": 4102444800},
    "secondary_window": {"used_percent": 12, "limit_window_seconds": 604800, "reset_at": 4102444800},
}}).encode()
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"

_STATE_DEFAULTS = {
    "_oauth_cache": {"t": 0.0, "gauges": None, "ok_t": None},
    "_oauth_token_cache": {"tok": None, "next_retry": 0.0, "declined": False,
                           "src": None, "file_sig": None, "suspect": False},
    "OAUTH_STATUS": {"auth_error": False, "last_error": None},
    "_oauth_last_call": {"transient": False},
    "_codex_cache": {"t": 0.0, "rows": None, "ok_t": None},
    "CODEX_STATUS": {"auth_error": False, "last_error": None},
    "_gemini_cache": {"t": 0.0, "rows": None, "ok_t": None, "click": False, "click_check": False,
                      "cwd": None, "check_t": 0.0, "login": None, "marker": None,
                      "auth_failed_marker": None, "open_dir": None},
    "GEMINI_STATUS": {"auth_error": False, "last_error": None},
    "GEMINI_BUCKETS": {},
    "_keychain_facts": {"blob": None, "t": 0.0, "t_try": 0.0},
}


class _Response:
    def __init__(self, body):
        self._body = body

    def read(self, *_a):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _Window:
    """Windows 에서 새 콘솔 Popen 대신 돌려주는 것 — 창은 없고, 스크립트는 이미 끝까지 돌았다."""
    pid = 0
    returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


class Box:
    """한 테스트의 격리된 세계: 임시 홈·가짜 CLI·가짜 자격 정보·서버 대역·창 대역."""

    def __init__(self, case):
        self.case = case
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="cp-matrix-"))
        case.addCleanup(shutil.rmtree, self.root, True)
        self.home = os.path.join(self.root, "home")
        self.bin = os.path.join(self.root, "bin")
        self.local = os.path.join(self.root, "localappdata")
        for d in (self.home, self.bin, self.local, os.path.join(self.root, "appdata")):
            os.makedirs(d)
        with open(os.path.join(self.root, "fakecli.py"), "w", encoding="utf-8") as f:
            f.write(_FAKE_CLI)
        self.write("behaviour.json", {"agy": {"bg": "x509", "window": "signin"},
                                      "codex": {"login": "ok"}, "claude": {"login": "ok"}})
        self.write("creds.json", {"gemini": None})
        self.http = {"claude": "ok", "codex": "ok"}
        self.http_calls = {"claude": 0, "codex": 0}
        self.leaks = []            # 대역이 모르는 주소 — 하나라도 있으면 실패
        self.windows = []          # 로그인 창마다 그 창에 찍힌 글자
        self.claude_jobs = []      # Claude 로그인 job 의 argv
        self.installs = []         # install_cli 대역이 불린 제공자
        self.install_result = "ok"
        if not WIN:
            self.install_wrapper("security")

        if WIN:
            sysroot = os.environ.get("SystemRoot") or r"C:\Windows"
            syspath = os.pathsep.join([os.path.join(sysroot, "System32"), sysroot])
        else:
            syspath = "/usr/bin:/bin:/usr/sbin:/sbin"
        env = {"HOME": self.home, "USERPROFILE": self.home, "LOCALAPPDATA": self.local,
               "APPDATA": os.path.join(self.root, "appdata"),
               "PATH": self.bin + os.pathsep + syspath}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        case.addCleanup(patcher.stop)
        for key in [k for k in os.environ
                    if k.upper() in ("CODEX_HOME", "CLAUDE_PET_USE_CLI", "CLAUDE_PET_FORCE_ONBOARD",
                                     "CLAUDE_PET_DEBUG", "SSH_TTY", "SSH_CLIENT", "SSH_CONNECTION")]:
            os.environ.pop(key, None)      # patch.dict 가 끝날 때 되돌린다
        if WIN:
            path_keys = [k for k in os.environ if k.upper() == "PATH" and k != "PATH"]
            for k in path_keys:
                os.environ[k] = env["PATH"]

        for name, default in _STATE_DEFAULTS.items():
            live = getattr(claude_pet, name)
            saved = dict(live)
            case.addCleanup(self._restore, live, saved)
            live.clear()
            live.update(default)
        prompt_until = list(claude_pet._keychain_prompt_until)
        case.addCleanup(claude_pet._keychain_prompt_until.__setitem__, 0, prompt_until[0])
        claude_pet._keychain_prompt_until[0] = 0.0
        lang = claude_pet.L["lang"]
        case.addCleanup(claude_pet.set_lang, lang)
        mode = claude_pet.RUNTIME.get("mode")
        case.addCleanup(claude_pet.RUNTIME.__setitem__, "mode", mode)
        claude_pet.RUNTIME["mode"] = "sub"

        patches = [
            mock.patch.object(urllib.request, "urlopen", self._urlopen),
            mock.patch.object(os.path, "exists", self._exists),
            mock.patch.object(claude_pet, "keychain_locked", lambda: False),
            mock.patch.object(claude_pet, "_security_read_blob", lambda timeout: None),
            mock.patch.object(claude_pet, "_keychain_token_native", self._native_tripwire),
            mock.patch.object(claude_pet, "_gemini_cred_probe", self._cred_probe),
            mock.patch.object(claude_pet, "_run_refresh_job", self._refresh_job),
            mock.patch.object(claude_pet, "install_cli", self._install_cli),
            mock.patch.object(claude_pet, "_run_in_terminal", self._terminal),
            mock.patch.object(claude_pet, "GEMINI_LOGIN_HINT_SEC", 3.0),
            mock.patch.object(claude_pet, "GEMINI_LOGIN_POLL_SEC", 0.05),
        ]
        if WIN:
            patches.append(mock.patch.object(subprocess, "Popen", self._popen))
        for p in patches:
            p.start()
            case.addCleanup(p.stop)

    # ── 파일 ──

    @staticmethod
    def _restore(live, saved):
        live.clear()
        live.update(saved)

    def write(self, leaf, obj):
        with open(os.path.join(self.root, leaf), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def read(self, leaf):
        with open(os.path.join(self.root, leaf), encoding="utf-8") as f:
            return json.load(f)

    def behave(self, cli, **kw):
        beh = self.read("behaviour.json")
        beh.setdefault(cli, {}).update(kw)
        self.write("behaviour.json", beh)

    def install_wrapper(self, exe):
        """가짜 CLI 의 래퍼를 PATH 의 폴더에 둔다 → 그 경로."""
        fake = os.path.join(self.root, "fakecli.py")
        if WIN:
            path = os.path.join(self.bin, exe + ".cmd")
            with open(path, "w", encoding="ascii", newline="\r\n") as f:
                f.write('@echo off\n"%s" "%s" %s %%*\n' % (sys.executable, fake, exe))
            return path
        path = os.path.join(self.bin, exe)
        with open(path, "w", encoding="utf-8") as f:
            f.write('#!/bin/sh\nexec "%s" "%s" %s "$@"\n' % (sys.executable, fake, exe))
        os.chmod(path, 0o755)
        return path

    def calls(self, cli, window=None):
        try:
            with open(os.path.join(self.root, "calls.log"), encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return []
        return [r for r in rows if r["cli"] == cli and (window is None or r["window"] == window)]

    # ── 대역 ──

    def _exists(self, path):
        """임시 폴더 밖의 claude·codex·agy 는 없는 것으로 — 러너에 깔린 진짜 CLI 가 표에 섞이지 않게."""
        try:
            text = os.fspath(path)
        except TypeError:
            return _REAL_EXISTS(path)
        if isinstance(text, str):
            stem = os.path.basename(text).lower().split(".")[0]
            inside = os.path.normcase(os.path.abspath(text)).startswith(os.path.normcase(self.root))
            if stem in ("claude", "codex", "agy") and not inside:
                return False
        return _REAL_EXISTS(path)

    def _urlopen(self, req, *_a, **_kw):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url == claude_pet.CODEX_LOGIN_CANCEL_URL:
            raise urllib.error.URLError(ConnectionRefusedError(61, "synthetic"))
        provider = {claude_pet.OAUTH_USAGE_URL: "claude", CODEX_USAGE_URL: "codex"}.get(url)
        if provider is None:
            self.leaks.append(url.split("?")[0])
            raise urllib.error.URLError(OSError("synthetic: unknown address"))
        self.http_calls[provider] += 1
        token = req.get_header("Authorization") or ""
        mode = "expired" if "expired" in token else self.http[provider]
        if mode == "ok":
            return _Response(CLAUDE_BODY if provider == "claude" else CODEX_BODY)
        if mode == "x509":
            raise urllib.error.URLError(ssl.SSLCertVerificationError(
                1, "certificate verify failed: unable to get local issuer certificate"))
        if mode == "network":
            raise urllib.error.URLError(OSError(51, "Network is unreachable"))
        code = 401 if mode == "expired" else 503
        raise urllib.error.HTTPError(url, code, "synthetic", {}, None)

    def _native_tripwire(self):
        self.leaks.append("native keychain read")
        return -25300, None

    def _cred_probe(self):
        mdat = self.read("creds.json").get("gemini")
        return (True, int("".join(c for c in mdat if c.isdigit()))) if mdat else (False, None)

    def _refresh_job(self, argv, label, stem, timeout, cancel=None, outcome=None):
        self.claude_jobs.append(list(argv))
        _REAL_RUN(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL, timeout=60, cwd=self.root, env=dict(os.environ))
        return ""

    def _install_cli(self, provider, *_a, **_kw):
        self.installs.append(provider)
        if self.install_result != "ok":
            return False, self.install_result
        return True, self.install_wrapper(EXE[provider])

    def _run_window(self, argv, env=None):
        env = dict(os.environ if env is None else env)
        env["FAKE_CLI_WINDOW"] = "1"
        r = _REAL_RUN(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      timeout=120, cwd=self.root, env=env)
        self.windows.append(r.stdout.decode("utf-8", errors="replace"))

    def _terminal(self, cmd):
        self._run_window(["/bin/bash", "-c", cmd])

    def _popen(self, argv, *a, **kw):
        if not (kw.get("creationflags", 0) & 0x10):          # CREATE_NEW_CONSOLE 만 창이다
            return _REAL_POPEN(argv, *a, **kw)
        argv = [x for x in argv if x != "-NoExit"]
        if "-Command" in argv:
            # 창이 없으니 출력이 파이프로 온다 — 글자가 깨지지 않게 인코딩만 정한다. 스크립트는 그대로다.
            i = argv.index("-Command") + 1
            argv[i] = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + argv[i]
        self._run_window(argv, kw.get("env"))
        return _Window()

    # ── 상태 만들기 ──

    def put_credentials(self, provider, token):
        if provider == "claude":
            folder, leaf = os.path.join(self.home, ".claude"), ".credentials.json"
            body = {"claudeAiOauth": {"accessToken": token}}
        else:
            folder, leaf = os.path.join(self.home, ".codex"), "auth.json"
            body = {"tokens": {"access_token": token, "account_id": "synthetic"}}
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, leaf), "w", encoding="utf-8") as f:
            json.dump(body, f)

    def arrange(self, provider, state):
        if state == "not_installed":
            return
        self.install_wrapper(EXE[provider])
        if state == "installed_no_login":
            return
        kind = state.replace("logged_in_", "")               # ok | x509 | network | server | login_required
        if provider == "gemini":
            self.write("creds.json", {"gemini": "20261119000000Z"})
            self.behave("agy", bg=kind)
        else:
            expired = kind == "login_required"
            self.put_credentials(provider, "synthetic-expired" if expired else "synthetic-good")
            if not expired:
                self.http[provider] = kind


# ── 앱이 하는 일을 그대로 부르는 도우미 ──

def refresh(provider):
    """그 제공자의 사용량을 한 번 읽는다(새로고침이 부르는 함수) → 행."""
    return {"claude": claude_pet.fetch_exact_usage, "codex": claude_pet.fetch_codex_usage,
            "gemini": claude_pet.fetch_gemini_usage}[provider]()


def let_time_pass(provider):
    """캐시가 만료될 만큼 시간이 지난 것으로 한다 — 다음 새로고침이 다시 읽을 차례다."""
    if provider == "claude":
        claude_pet._oauth_cache["t"] = 0.0
    elif provider == "codex":
        claude_pet._codex_cache["t"] = 0.0
    else:
        claude_pet._gemini_cache["t"] -= claude_pet.GEMINI_AUTO_SEC + 1
        claude_pet._gemini_cache["check_t"] -= claude_pet.GEMINI_CHECK_SEC + 1


def settings_row(provider, job=None):
    """설정 "AI 연결" 의 그 줄 — 두 UI 가 1초마다 부르는 그 식."""
    return claude_pet.ai_connect_row(provider, bool(claude_pet.find_cli(provider)),
                                     claude_pet.cli_logged_in(provider), job or claude_pet.new_ai_job())


def reads(box, provider):
    """사용량 읽기를 몇 번 시도했는가 — 서버 요청 수, Gemini 는 백그라운드 agy 실행 수."""
    return len(box.calls("agy", window=False)) if provider == "gemini" else box.http_calls[provider]


def login_runs(box, provider):
    """로그인을 몇 번 띄웠는가 — Claude 는 job, Codex 는 `codex login`, Gemini 는 창."""
    if provider == "claude":
        return len(box.claude_jobs)
    if provider == "codex":
        return len([c for c in box.calls("codex") if c["args"][:1] == ["login"]])
    return len(box.windows)


# 첫 새로고침 뒤의 줄: 상태 → (status, button, 읽기를 시도했는가, 값이 바로 보이는가).
# 오류 상태의 status 는 "로그인하라는 줄이 아니다" 로만 고정한다(ROW_NOT_LOGIN).
ROW_NOT_LOGIN = object()
ROW = {
    "not_installed":      ("ai_not_installed", "ai_btn_install", False, False),
    "installed_no_login": ("ai_need_login", "ai_btn_login", False, False),
    "logged_in_ok":       ("ai_connected", None, True, True),
    "logged_in_x509":     (ROW_NOT_LOGIN, ROW_NOT_LOGIN, True, False),
    "logged_in_network":  (ROW_NOT_LOGIN, ROW_NOT_LOGIN, True, False),
    "logged_in_server":   (ROW_NOT_LOGIN, ROW_NOT_LOGIN, True, False),
    "login_required":     ("ai_need_login", "ai_btn_login", True, False),
}
# 그 줄에서 흐름을 시작했을 때: 상태 → (설치 횟수, 로그인 실행 횟수, 결과 또는 None(따지지 않음),
# 끝난 뒤 다음 새로고침에 값이 보이는가).
PRESS = {
    "not_installed":      (1, 1, "ok", True),
    "installed_no_login": (0, 1, "ok", True),
    "logged_in_ok":       (0, 0, None, True),
    "logged_in_x509":     (0, 0, None, False),
    "logged_in_network":  (0, 0, None, False),
    "logged_in_server":   (0, 0, None, False),
    "login_required":     (0, 1, "ok", True),
}
# 로그인 창에서 agy 가 끝난 모양 → (완료 문구가 찍히는가, 시간 초과 문구가 찍히는가, 창에 보여야 하는 agy 의 말).
WINDOW = {
    "signin":  (True, False, LOGIN_TEXT),
    "x509":    (False, False, X509_TEXT),
    "network": (False, False, NETWORK_TEXT),
    "server":  (False, False, SERVER_TEXT),
    "timeout": (False, True, TIMEOUT_TEXT),
}


class MatrixCase(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.box = Box(self)

    def tearDown(self):
        self.assertEqual(self.box.leaks, [], "대역 밖의 주소·키체인을 건드렸다")
        self.assertFalse(os.path.exists(os.path.join(self.box.root, "tripwire.log")),
                         "security 에 비밀값(-w/-g)을 물었다")

    def assert_no_login_offer(self, row, where):
        self.assertNotIn(row["status"], ("ai_need_login", "ai_not_installed"),
                         "%s: 로그인돼 있는데 줄이 로그인·설치를 말한다" % where)
        self.assertNotIn(row["button"], ("ai_btn_login", "ai_btn_install"),
                         "%s: 로그인돼 있는데 [로그인]·[설치] 버튼이 있다" % where)


class StateMatrixTest(MatrixCase):
    """제공자 × 상태 × (row | press | recover). 메서드는 아래에서 표로 만든다."""

    def check_row(self, provider, state):
        status, button, read, values = ROW[state]
        self.box.arrange(provider, state)
        rows = refresh(provider)
        row = settings_row(provider)
        where = "%s/%s" % (provider, state)
        if status is ROW_NOT_LOGIN:
            self.assert_no_login_offer(row, where)
        else:
            self.assertEqual((row["status"], row["button"]), (status, button), where)
        self.assertEqual(bool(reads(self.box, provider)), read, "%s: 읽기 시도" % where)
        if provider == "gemini":
            self.assertLessEqual(reads(self.box, provider), 1, "%s: agy 를 한 번 넘게 띄웠다" % where)
        self.assertEqual(bool(rows), values, "%s: 값이 바로 보이는가" % where)
        self.assertEqual(self.box.installs, [], "%s: 새로고침이 설치를 시작했다" % where)
        for p in PROVIDERS:
            self.assertEqual(login_runs(self.box, p), 0, "%s: 새로고침이 %s 로그인을 띄웠다" % (where, p))

    def check_press(self, provider, state):
        installs, logins, result, values = PRESS[state]
        self.box.arrange(provider, state)
        refresh(provider)
        job = claude_pet.new_ai_job()
        got = claude_pet.run_ai_connect(provider, job)
        where = "%s/%s" % (provider, state)
        self.assertEqual(self.box.installs, [provider] * installs, "%s: 설치 횟수" % where)
        self.assertEqual(login_runs(self.box, provider), logins, "%s: 로그인 실행 횟수" % where)
        for p in PROVIDERS:
            if p != provider:
                self.assertEqual(login_runs(self.box, p), 0, "%s: 다른 제공자(%s) 로그인을 띄웠다" % (where, p))
        if provider != "gemini":
            self.assertEqual(self.box.windows, [], "%s: 터미널 창을 열었다" % where)
        if result is not None:
            self.assertEqual(got, result, where)
            self.assertEqual((job["phase"], job["reason"]), (None, None), where)
            row = settings_row(provider, job)
            self.assertEqual((row["status"], row["button"]), ("ai_connected", None), "%s: 끝난 뒤의 줄" % where)
        else:
            self.assert_no_login_offer(settings_row(provider, job), where + " 끝난 뒤")
        if provider == "gemini" and logins:
            done, late = claude_pet.t("term_gemini_done"), claude_pet.t("term_gemini_timeout")
            self.assertIn(done, self.box.windows[-1], where)
            self.assertNotIn(late, self.box.windows[-1], where)
        if result is not None:
            # 로그인을 마친 흐름은 스스로 다시 읽게 해 둔다 — 시간을 돌리지 않고 다음 새로고침에서 값이 떠야 한다.
            rows = refresh(provider)
        else:
            rows = refresh(provider)
        self.assertEqual(bool(rows), values, "%s: 끝난 뒤 값이 보이는가" % where)

    def check_recover(self, provider, state):
        """오류 상태: 로그인 없이 스스로 다시 읽어 값이 뜨고, 다시 실패해도 직전 값이 남는다."""
        kind = state.replace("logged_in_", "")
        where = "%s/%s" % (provider, state)
        self.box.arrange(provider, state)
        self.assertFalse(refresh(provider), where)
        before = reads(self.box, provider)

        def set_server(mode):
            if provider == "gemini":
                self.box.behave("agy", bg=mode)
            else:
                self.box.http[provider] = mode

        set_server("ok")
        let_time_pass(provider)
        rows = refresh(provider)
        self.assertGreater(reads(self.box, provider), before, "%s: 스스로 다시 읽지 않았다" % where)
        self.assertTrue(rows, "%s: 서버가 돌아왔는데 값이 없다" % where)
        row = settings_row(provider)
        self.assertEqual((row["status"], row["button"]), ("ai_connected", None), where)

        set_server(kind)
        let_time_pass(provider)
        kept = refresh(provider)
        self.assertEqual(kept, rows, "%s: 다시 실패하자 직전 값이 사라졌다" % where)
        self.assert_no_login_offer(settings_row(provider), where + " 다시 실패")
        for p in PROVIDERS:
            self.assertEqual(login_runs(self.box, p), 0, "%s: %s 로그인을 띄웠다" % (where, p))
        self.assertEqual(self.box.installs, [], where)


def _add(cls, name, fn, *args):
    def test(self):
        fn(self, *args)
    test.__name__ = name
    test.__qualname__ = "%s.%s" % (cls.__name__, name)
    setattr(cls, name, test)


for _p in PROVIDERS:
    for _s in STATES:
        _add(StateMatrixTest, "test_%s__%s__row" % (_p, _s), StateMatrixTest.check_row, _p, _s)
        _add(StateMatrixTest, "test_%s__%s__press" % (_p, _s), StateMatrixTest.check_press, _p, _s)
    for _s in ERROR_STATES:
        _add(StateMatrixTest, "test_%s__%s__recover" % (_p, _s), StateMatrixTest.check_recover, _p, _s)


class InstallFailureTest(MatrixCase):
    """[설치]가 실패하면 거기서 멈춘다 — 이유와 [다시 시도], 로그인은 띄우지 않는다."""

    def check(self, provider, kind):
        self.box.install_result = kind
        job = claude_pet.new_ai_job()
        got = claude_pet.run_ai_connect(provider, job)
        self.assertEqual(got, kind)
        self.assertEqual(self.box.installs, [provider])
        row = settings_row(provider, job)
        self.assertEqual((row["status"], row["button"]), ("ai_fail_" + kind, "ai_btn_retry"))
        for p in PROVIDERS:
            self.assertEqual(login_runs(self.box, p), 0)


for _p in PROVIDERS:
    for _k in ("network", "hash", "signature"):
        _add(InstallFailureTest, "test_%s__install_%s" % (_p, _k), InstallFailureTest.check, _p, _k)


class LoginWindowScriptTest(MatrixCase):
    """Gemini 로그인 창의 스크립트를 가짜 agy 로 **실제로 돌려** 찍힌 글자를 본다 — 언어 × agy 의 끝."""

    def check(self, lang, ending):
        done_shown, late_shown, agy_text = WINDOW[ending]
        claude_pet.set_lang(lang)
        self.box.install_wrapper("agy")
        self.box.behave("agy", window=ending)
        claude_pet.start_gemini_login()
        self.assertEqual(len(self.box.windows), 1, "창은 하나")
        text = self.box.windows[0]
        where = "%s/%s" % (lang, ending)
        for key in ("term_gemini_step1", "term_gemini_step2", "term_gemini_step3"):
            self.assertIn(claude_pet.t(key), text, "%s: 안내 %s" % (where, key))
        self.assertIn(agy_text, text, "%s: agy 의 stderr 가 창에 보여야 한다" % where)
        self.assertNotIn('"status"', text, "%s: stdout(JSON 본문)은 창에 찍지 않는다" % where)
        done, late = claude_pet.t("term_gemini_done"), claude_pet.t("term_gemini_timeout")
        self.assertEqual(done in text, done_shown, "%s: 완료 문구" % where)
        self.assertEqual(late in text, late_shown, "%s: 시간 초과 문구" % where)
        ran = self.box.calls("agy", window=True)
        self.assertEqual([c["args"] for c in ran], [list(claude_pet.GEMINI_AGY_ARGS)], where)


for _l in LANGS:
    for _e in WINDOW:
        _add(LoginWindowScriptTest, "test_%s__agy_%s" % (_l, _e), LoginWindowScriptTest.check, _l, _e)


class SignedOutNeverRunsTest(MatrixCase):
    """로그인 정보가 없는 CLI 는 몇 번을 새로고침해도 띄우지 않는다(로그인 절차가 스스로 시작되지 않게)."""

    def test_gemini_signed_out_is_never_run(self):
        self.box.arrange("gemini", "installed_no_login")
        for _ in range(3):
            refresh("gemini")
            let_time_pass("gemini")
        self.assertEqual(self.box.calls("agy"), [])
        self.assertEqual(self.box.windows, [])

    def test_gemini_login_demand_stops_automatic_runs(self):
        self.box.arrange("gemini", "login_required")
        for _ in range(3):
            refresh("gemini")
            let_time_pass("gemini")
        self.assertEqual(len(self.box.calls("agy", window=False)), 1, "로그인을 요구한 agy 를 다시 띄웠다")
        self.assertEqual(self.box.windows, [])

    def test_codex_login_is_never_run_by_refresh(self):
        for state in ("logged_in_ok", "logged_in_x509", "login_required"):
            with self.subTest(state=state):
                self.box.arrange("codex", state)
                for _ in range(3):
                    refresh("codex")
                    let_time_pass("codex")
                self.assertEqual(login_runs(self.box, "codex"), 0)


class CliEnvProbeTest(MatrixCase):
    """`--cli-env-probe` — CI 가 빌드한 번들에게 "CLI 에 넘기는 환경"을 묻는 숨은 인자
    (ci/bundle_cli_env_check.py 가 쓴다). 여기서는 소스 실행으로 모양만 고정한다: 번들에서만 생기는
    값(py2app 의 SSL_CERT_*)은 번들 잡이 본다."""

    def run_probe(self, *extra):
        main = getattr(claude_pet, "cli_env_probe_main", None)
        self.assertIsNotNone(main, "claude_pet.cli_env_probe_main 이 없다")
        out = os.path.join(self.box.root, "probe.json")
        rc = main(["app", claude_pet.CLI_ENV_PROBE_FLAG, out] + list(extra))
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as f:
            return json.load(f)

    def test_reports_every_environment_and_opens_nothing(self):
        agy = self.box.install_wrapper("agy")
        popen_before, terminal_before = subprocess.Popen, claude_pet._run_in_terminal
        report = self.run_probe("--agy", agy)
        self.assertEqual(sorted(report["cli_env"]), sorted(PROVIDERS))
        for provider in PROVIDERS:
            self.assertIsInstance(report["cli_env"][provider], dict)
        self.assertIsInstance(report["agy_env"], dict)
        self.assertEqual(report["environ"].get("HOME"), self.box.home)
        self.assertIsNone(report["login_window_error"])
        window = report["login_window"]
        self.assertEqual(window["kind"], "powershell" if WIN else "bash")
        script = " ".join(window["argv"]) if WIN else window["script"]
        self.assertIn(claude_pet.t("term_gemini_step1"), script)
        self.assertIn(agy, script)
        # 아무것도 띄우지 않았고, 바꿔 끼운 것은 되돌려 놓았다.
        self.assertEqual(self.box.windows, [])
        self.assertEqual(self.box.calls("agy"), [])
        self.assertIs(subprocess.Popen, popen_before)
        self.assertIs(claude_pet._run_in_terminal, terminal_before)

    def test_without_agy_there_is_no_login_window(self):
        report = self.run_probe()
        self.assertIsNone(report["login_window"])
        self.assertEqual(self.box.windows, [])

    def test_missing_path_is_a_usage_error(self):
        main = getattr(claude_pet, "cli_env_probe_main", None)
        self.assertIsNotNone(main, "claude_pet.cli_env_probe_main 이 없다")
        self.assertEqual(main(["app", "--cli-env-probe"]), 2)

    def test_both_entry_points_answer_the_flag_before_becoming_the_app(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "claude_pet.py"), encoding="utf-8") as f:
            core = f.read()
        tail = core[core.rindex('if __name__ == "__main__":'):]
        self.assertIn("cli_env_probe_main(sys.argv)", tail)
        self.assertLess(tail.index("cli_env_probe_main"), tail.index("run_gui()"))
        with open(os.path.join(root, "windows", "claude_pet_win.py"), encoding="utf-8") as f:
            port = f.read()
        body = port[port.rindex("def main():"):]
        self.assertIn("cp.cli_env_probe_main(sys.argv)", body)
        self.assertLess(body.index("cli_env_probe_main"), body.index("acquire_single_instance_mutex()"))


if __name__ == "__main__":
    unittest.main()
