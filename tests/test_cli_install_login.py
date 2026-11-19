"""계약 v7-I — 설정에서 Claude Code·Codex·Gemini CLI 를 받고 로그인까지. Verifier(gemini-tests-v2) 작성, 구현 전.

계약: briefs/v7-contract.md 의 I1~I8 과 끝의 "agy 동의" 보완. 진짜 네트워크·진짜 CLI·키체인·자격 증명
관리자·codesign 을 건드리지 않는다: 받기는 주입한 `http_get`/`opener`, 프로세스는 `subprocess` 대역, 홈은
임시 폴더다. Developer 는 이 파일의 단언·기대값·픽스처를 고치지 않는다(AGENTS.md §2).

── 이 파일이 정한 이름(코어 `claude_pet.py`) ─────────────────────────────────────────────

경로·찾기
  CLI_PROVIDERS = ("claude", "codex", "gemini")
  app_cli_bin_dir()                 앱 전용 bin. macOS ~/Library/Application Support/me.yeongyu.claudepet/bin,
                                    Windows %LOCALAPPDATA%\\me.yeongyu.claudepet\\bin
  app_cli_path(provider)            그 안의 claude / codex / agy (Windows 는 .exe)
  app_cli_ok(path)                  lstat: 보통 파일·소유자 본인·링크 아님
  find_cli(provider)                사용자가 깐 것 먼저, 앱 전용 bin 은 마지막(app_cli_ok 일 때만). 없으면 None

받기
  CliInstallError(kind)             .kind ∈ unsupported | manifest | network | hash | archive | signature
                                    | cancelled | locked
  cli_release_info(provider, http_get, system=None, machine=None)
        → {"version", "url", "alg"("sha256"|"sha512"), "digest"(hex), "archive"(None|"tar.gz"|"zip"),
           "member"(아카이브 안의 이름 또는 None)}.  http_get(url) → bytes.
  cli_stage_download(url, alg, digest, opener, progress=None, cancel=None) → staging 안의 파일 경로
        opener(url) → .read(n)·.close()·.length(int 또는 None) 를 가진 응답. progress(받은 바이트, 전체 또는 None).
        cancel() → bool.
  cli_extract_one(archive_path, kind, member, dest_path)   한 엔트리만 보통 파일로
  CLI_TEAM_IDS / CLI_AUTHENTICODE_ORGS
  cli_signature_ok(provider, path) → bool      macOS: /usr/bin/codesign --verify --strict + TeamIdentifier
  authenticode_ok(provider, status, subject) → bool   Windows: 상태 "Valid" + 주체의 O
  install_cli(provider, http_get=None, opener=None, system=None, machine=None, progress=None, cancel=None)
        → (True, 경로) | (False, kind).  예외를 내지 않는다. 서명 확인은 모듈의 cli_signature_ok 를 이름으로 부른다.
  read_app_cli_meta(provider) → {"version": …, "checked": 초} 또는 None
  app_cli_update_due(provider, now) / update_app_cli(provider, http_get=None, opener=None, now=None, …)

로그인
  CLI_LOGIN_TIMEOUT_SEC = {"claude": 300, "codex": 300}   (Gemini 는 앱이 끊지 않는다)
  GEMINI_LOGIN_HINT_SEC = 300        표시용 — 지나면 run_cli_login("gemini") 이 "timeout"("다시 시도" 안내)
  start_gemini_login()               보이는 창: macOS Terminal(_run_in_terminal), Windows 새 콘솔(코어가 연다,
                                     CREATE_NEW_CONSOLE). 안내 세 줄(term_gemini_step1~3) 뒤에 `agy`.
                                     run_cli_login("gemini") 이 이 이름으로 부른다.
  cli_login_argv(provider, path) / cli_env(provider, path, base_env=None) / cli_logged_in(provider)
  run_cli_login(provider, cancel=None) → "ok" | "already" | "denied" | "timeout" | "cancelled" | "failed"
                                         | "not_installed"

설정 "AI 연결"
  ai_connect_row(provider, installed, logged_in, job=None) → {"status", "button", "pct", "hint"} (TR 키)
  start_ai_connect(...)              (선택) run_ai_connect 를 데몬 스레드에서 돌리는 도우미 — 두면 이 이름으로
  run_ai_connect(provider, job, cancel=None) → 위 결과 문자열 또는 install 의 kind.
        job 은 dict — {"phase": None|"download"|"verify"|"login"|"failed", "pct": …, "reason": …}
"""

import ast
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time as _real_time
import unittest
import zipfile
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
REAL_WINDOWS = sys.platform == "win32"
REAL_ENV = dict(os.environ)
_REAL_POPEN = subprocess.Popen
_REAL_RUN = subprocess.run
APP_DIR = "me.yeongyu.claudepet"
PROVIDERS = ("claude", "codex", "gemini")
EXE = {"claude": "claude", "codex": "codex", "gemini": "agy"}

CLAUDE_BASE = "https://downloads.claude.ai/claude-code-releases"
CODEX_CHANNEL = "https://releases.openai.com/codex/channels/latest"
CODEX_GITHUB = "https://api.github.com/repos/openai/codex/releases/latest"
AGY_MANIFESTS = "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/"
# 받는 주소에는 서명된 쿼리가 붙을 수 있다 — 로그에 남으면 안 되는 것의 대역.
SECRET_QUERY = "X-Synthetic-Signature=SECRETSECRETSECRET"


def _require(name):
    fn = getattr(claude_pet, name, None)
    if fn is None:
        raise AssertionError("claude_pet.%s 가 없다 — 계약 v7-I 미구현" % name)
    return fn


def norm(path):
    return os.path.normcase(os.path.normpath(str(path).replace("\\", "/")))


def rb(path):
    with open(path, "rb") as f:
        return f.read()


def sha(alg, data):
    return hashlib.new(alg, data).hexdigest()


def tar_gz(members):
    """members: [(이름, bytes | ("link", 대상) | ("hard", 대상) | ("dir",))] → tar.gz bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, body in members:
            info = tarfile.TarInfo(name)
            if isinstance(body, bytes):
                info.size = len(body)
                info.mode = 0o755
                tf.addfile(info, io.BytesIO(body))
            elif body[0] == "dir":
                info.type = tarfile.DIRTYPE
                tf.addfile(info)
            else:
                info.type = tarfile.SYMTYPE if body[0] == "link" else tarfile.LNKTYPE
                info.linkname = body[1]
                tf.addfile(info)
    return buf.getvalue()


def zip_bytes(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in members:
            if isinstance(body, bytes):
                zf.writestr(name, body)
            else:                                   # 심볼릭 링크 엔트리
                info = zipfile.ZipInfo(name)
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                zf.writestr(info, body[1])
    return buf.getvalue()


class Release:
    """한 제공자·한 플랫폼의 합성 배포물 — 매니페스트 응답들과 받을 파일."""

    def __init__(self, provider, system, machine, binary=None, version=None):
        self.provider = provider
        win = system == "Windows"
        arm = machine in ("arm64", "aarch64")
        self.binary = binary if binary is not None else (
            b"MZ" if win else b"\xcf\xfa\xed\xfe") + (" synthetic %s " % provider).encode() * 9000
        self.http = {}
        if provider == "claude":
            self.version = version or "9.8.7"
            plat = "win32-x64" if win else ("darwin-arm64" if arm else "darwin-x64")
            name = "claude.exe" if win else "claude"
            self.payload, self.archive, self.member, self.alg = self.binary, None, None, "sha256"
            self.url = "%s/%s/%s/%s" % (CLAUDE_BASE, self.version, plat, name)
            other = "f" * 64
            platforms = {p: {"binary": "claude.exe" if p.startswith("win32") else "claude",
                             "checksum": other, "size": 1}
                         for p in ("darwin-arm64", "darwin-x64", "win32-x64", "win32-arm64")}
            platforms[plat] = {"binary": name, "checksum": sha("sha256", self.payload),
                               "size": len(self.payload)}
            self.http[CLAUDE_BASE + "/latest"] = (self.version + "\n").encode()
            self.http["%s/%s/manifest.json" % (CLAUDE_BASE, self.version)] = json.dumps(
                {"version": self.version, "platforms": platforms}).encode()
        elif provider == "codex":
            self.version = version or "0.987.6"
            if win:
                asset, self.member, self.archive = ("codex-x86_64-pc-windows-msvc.exe.zip",
                                                    "codex-x86_64-pc-windows-msvc.exe", "zip")
                self.payload = zip_bytes([(self.member, self.binary)])
            else:
                triple = "aarch64-apple-darwin" if arm else "x86_64-apple-darwin"
                asset, self.member, self.archive = "codex-%s.tar.gz" % triple, "codex-%s" % triple, "tar.gz"
                self.payload = tar_gz([(self.member, self.binary)])
            self.alg = "sha256"
            self.url = "https://releases.openai.com/codex/releases/%s/%s?%s" % (
                self.version, asset, SECRET_QUERY)
            decoys = ["codex-aarch64-apple-darwin.tar.gz", "codex-x86_64-apple-darwin.tar.gz",
                      "codex-x86_64-pc-windows-msvc.exe.zip", "codex-x86_64-pc-windows-msvc.exe",
                      "codex-package-aarch64-apple-darwin.tar.gz", "codex-package_SHA256SUMS",
                      "codex-x86_64-pc-windows-msvc.exe.tar.gz", "install.sh", "install.ps1"]
            assets = [{"name": n, "digest": "sha256:" + "e" * 64,
                       "browser_download_url": "https://releases.openai.com/codex/releases/%s/%s"
                                               % (self.version, n)} for n in decoys if n != asset]
            assets.insert(2, {"name": asset, "digest": "sha256:" + sha("sha256", self.payload),
                              "browser_download_url": self.url})
            self.meta = json.dumps({"tag_name": "rust-v" + self.version, "assets": assets}).encode()
            self.http[CODEX_CHANNEL] = self.meta
        else:
            self.version = version or "7.6.5"
            key = ("windows_amd64" if win else ("darwin_arm64" if arm else "darwin_amd64")) + ".json"
            if win:
                self.payload, self.archive, self.member = self.binary, None, None
                self.url = "https://storage.googleapis.com/antigravity-public/x/cli_windows_x64.exe?" \
                           + SECRET_QUERY
            else:
                self.archive, self.member = "tar.gz", "antigravity"
                self.payload = tar_gz([("antigravity", self.binary)])
                self.url = "https://storage.googleapis.com/antigravity-public/x/cli_mac.tar.gz?" \
                           + SECRET_QUERY
            self.alg = "sha512"
            self.http[AGY_MANIFESTS + key] = json.dumps(
                {"version": self.version, "url": self.url, "sha512": sha("sha512", self.payload),
                 "timestamp": 1}).encode()
        self.digest = sha(self.alg, self.payload)


class Net:
    """http_get 과 opener 의 대역. 모르는 주소는 OSError — 진짜 네트워크로 나가지 않는다."""

    def __init__(self):
        self.http = {}
        self.files = {}
        self.gets = []
        self.opens = []
        self.reads = []
        self.cancel_after = None        # 이만큼의 read 뒤 cancel() 이 True
        self.break_after = None         # 이만큼의 read 뒤 OSError
        self.closed = 0

    def serve(self, release, payload=None):
        self.http.update(release.http)
        self.files[release.url] = release.payload if payload is None else payload
        return release

    def http_get(self, url, *a, **k):
        self.gets.append(url)
        if url not in self.http:
            raise OSError("synthetic: no such url")
        return self.http[url]

    def opener(self, url, *a, **k):
        self.opens.append(url)
        if url not in self.files:
            raise OSError("synthetic: no such file")
        net, body = self, io.BytesIO(self.files[url])

        class Response:
            length = len(self.files[url])

            def read(self, n=-1):
                if not isinstance(n, int) or n <= 0 or n > (1 << 22):
                    raise AssertionError("read(%r) — 통째로 읽지 말고 청크로 읽어야 한다" % (n,))
                net.reads.append(n)
                if net.break_after is not None and len(net.reads) > net.break_after:
                    raise OSError("synthetic: connection reset")
                return body.read(min(n, 65536))

            def close(self):
                net.closed += 1

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()

        return Response()

    def cancel(self):
        return self.cancel_after is not None and len(self.reads) >= self.cancel_after


class CliCase(unittest.TestCase):
    """홈·LOCALAPPDATA·임시 폴더는 이 테스트의 것, which 는 대역, subprocess 는 기록만 하는 대역."""

    platform = "darwin"

    def setUp(self):
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="claudepet-cli-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.home = os.path.join(self.base, "home")
        self.local = os.path.join(self.base, "localappdata")
        self.tmp = os.path.join(self.base, "tmp")
        for d in (self.home, self.local, self.tmp):
            os.makedirs(d)
        self.dotfiles = {}
        for name in (".zshrc", ".zprofile", ".bash_profile", ".bashrc", ".profile"):
            p = os.path.join(self.home, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# synthetic %s\nexport PATH=\"/synthetic/bin:$PATH\"\n" % name)
            self.dotfiles[p] = (rb(p), os.stat(p).st_mtime_ns)
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, LOCALAPPDATA=self.local,
                   PATH=os.pathsep.join([os.path.join(self.base, "p1"), os.path.join(self.base, "p2")]))
        for name in list(env):
            if name.upper() in ("CLAUDE_PET_DEBUG", "CODEX_HOME", "SSH_TTY", "SSH_CLIENT", "SSH_CONNECTION",
                                "DISABLE_AUTOUPDATER", "DISABLE_INSTALLATION_CHECKS",
                                "AGY_CLI_DISABLE_AUTO_UPDATE", "HOMEDRIVE", "HOMEPATH", "XDG_CONFIG_HOME"):
                env.pop(name)
        self._patch(mock.patch.dict(os.environ, env, clear=True))
        self._patch(mock.patch.object(tempfile, "tempdir", self.tmp))
        self._patch(mock.patch.object(sys, "platform", self.platform))
        self.which = {"claude": None, "codex": None, "agy": None,
                      "claude.exe": None, "codex.exe": None, "codex.cmd": None, "agy.exe": None}
        real_which = shutil.which
        self._patch(mock.patch.object(claude_pet.shutil, "which",
                                      lambda name, *a, **k: self.which.get(name)
                                      if name in self.which else real_which(name, *a, **k)))
        # 이 기기에 진짜로 깔린 CLI(/opt/homebrew/bin/claude 등)가 보이지 않게 — 테스트 폴더 밖의 CLI 이름은 없다.
        for fn in ("exists", "isfile", "lexists"):
            real = getattr(os.path, fn)

            def hide(path, _real=real):
                p = os.fspath(path) if not isinstance(path, int) else path
                if isinstance(p, str) and os.path.basename(p).lower().split(".")[0] in ("claude", "codex", "agy") \
                        and not os.path.realpath(p).startswith(self.base):
                    return False
                return _real(path)
            self._patch(mock.patch.object(claude_pet.os.path, fn, hide))
        self.spawned = []           # (argv, kwargs)
        self.dbg = []
        self._patch(mock.patch.object(claude_pet.subprocess, "run", self._run))
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen", self._popen))
        self._patch(mock.patch.object(claude_pet.os, "system",
                                      lambda *a, **k: self.spawned.append((["os.system"], {})) or 1))
        self._patch(mock.patch.object(claude_pet, "_dbg", lambda *a, **k: self.dbg.append(a)))
        self._patch(mock.patch("socket.create_connection",
                               side_effect=AssertionError("테스트가 네트워크에 나가려 했다")))
        self.urlopens = []
        self._patch(mock.patch.object(claude_pet.urllib.request, "urlopen", self._urlopen))
        self.net = Net()

    # ── 대역 ──
    def _patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def _urlopen(self, req, *a, **k):
        url = req if isinstance(req, str) else getattr(req, "full_url", str(req))
        self.urlopens.append((url, k.get("timeout", a[1] if len(a) > 1 else None)))
        raise OSError("synthetic: urlopen is not available in tests")

    def _run(self, argv, *a, **k):
        self.spawned.append(([str(x) for x in argv] if not isinstance(argv, (str, bytes)) else [str(argv)],
                             dict(k)))
        return subprocess.CompletedProcess(argv, 1, "", "")

    def _popen(self, argv, *a, **k):
        self.spawned.append(([str(x) for x in argv] if not isinstance(argv, (str, bytes)) else [str(argv)],
                             dict(k)))
        raise OSError("synthetic: this test spawns nothing")

    # ── 도구 ──
    def bin_dir(self):
        if self.platform == "win32":
            return os.path.join(self.local, APP_DIR, "bin")
        return os.path.join(self.home, "Library", "Application Support", APP_DIR, "bin")

    def final(self, provider):
        return os.path.join(self.bin_dir(), EXE[provider] + (".exe" if self.platform == "win32" else ""))

    def system_machine(self):
        return ("Windows", "AMD64") if self.platform == "win32" else ("Darwin", "arm64")

    def staging_files(self):
        d = os.path.join(self.bin_dir(), "staging")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def put(self, path, body=b"#!/bin/sh\nexit 0\n", mode=0o755):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        os.chmod(path, mode)
        return path

    def assert_user_shell_untouched(self):
        for p, (body, mtime) in self.dotfiles.items():
            self.assertEqual((rb(p), os.stat(p).st_mtime_ns), (body, mtime),
                             "사용자의 셸 설정 파일을 건드렸다: %s" % os.path.basename(p))
        left = sorted(n for n in os.listdir(self.home) if n not in
                      [os.path.basename(p) for p in self.dotfiles] + ["Library", ".claude", ".codex",
                                                                    ".gemini", ".local"])
        self.assertEqual(left, [], "홈에 모르는 것이 생겼다")

    def assert_no_secrets_logged(self, *extra):
        """I8: 로그에는 개수·상태·종료 코드만 — 주소·쿼리·해시·경로·토큰이 없다."""
        text = " ".join(str(x) for call in self.dbg for x in call)
        for bad in ("http", "?", "SECRET", self.home, self.base, "synthetic-access") + tuple(extra):
            self.assertNotIn(bad, text, "로그에 %r 가 남았다" % bad)


# ═════════════════════════════ I2·I3 — 경로와 찾기 ═════════════════════════════


class AppBinTests(CliCase):

    def test_the_app_bin_is_under_application_support_on_macos_and_localappdata_on_windows(self):
        """I3: macOS `~/Library/Application Support/me.yeongyu.claudepet/bin/`, Windows
        `%LOCALAPPDATA%\\me.yeongyu.claudepet\\bin\\`; 실행 파일 이름은 claude·codex·agy(Windows 는 .exe).
        Rival: ~/.local/bin 에 둠(사용자의 PATH 에 끼어든다 — "사용자 PATH 는 절대 건드리지 않는다")."""
        self.assertEqual(tuple(getattr(claude_pet, "CLI_PROVIDERS", ())), PROVIDERS)
        for plat in ("darwin", "win32"):
            with self.subTest(platform=plat), mock.patch.object(sys, "platform", plat):
                self.platform = plat
                self.assertEqual(norm(_require("app_cli_bin_dir")()), norm(self.bin_dir()))
                for p in PROVIDERS:
                    self.assertEqual(norm(_require("app_cli_path")(p)), norm(self.final(p)))
        self.platform = "darwin"
        self.assertFalse(os.path.exists(os.path.join(self.home, "Library")), "경로를 묻기만 했는데 폴더를 만들었다")

    def test_a_cli_in_the_app_bin_is_run_only_if_it_is_our_own_plain_file(self):
        """I3: 실행 전 lstat — 보통 파일·소유자 본인·심볼릭 링크 아님.
        Rivals: os.path.exists 만 봄(누가 bin 에 링크를 걸어 다른 것을 실행시킨다); 폴더를 실행 파일로 봄."""
        ok = _require("app_cli_ok")
        good = self.put(self.final("codex"))
        self.assertIs(ok(good), True)
        target = self.put(os.path.join(self.base, "elsewhere", "codex"))
        link = self.final("claude")
        os.symlink(target, link)
        self.assertIs(ok(link), False, "심볼릭 링크를 받아들였다")
        os.makedirs(self.final("gemini"))
        self.assertIs(ok(self.final("gemini")), False)
        self.assertIs(ok(os.path.join(self.bin_dir(), "missing")), False)
        if not REAL_WINDOWS:
            other = os.getuid() + 1
            with mock.patch.object(claude_pet.os, "getuid", lambda: other):
                self.assertIs(ok(good), False, "남의 파일을 받아들였다")

    def test_the_users_own_cli_wins_and_the_app_bin_is_the_last_resort(self):
        """I2: 찾기 순서의 **마지막**이 앱 전용 bin. 사용자가 깐 것이 있으면 그것을 쓴다. 앱 bin 의 것이 링크면
        없는 것으로 본다. 기존 찾기 함수(_find_claude_cli·_find_codex_cli·_find_agy_cli)도 같은 답을 낸다.
        Rivals: 앱 bin 을 먼저 봄(사용자가 올린 버전 대신 앱이 받은 옛 버전을 쓴다); 앱 bin 을 안 봄([설치]를
        눌러도 영원히 "설치 안 됨")."""
        find = _require("find_cli")
        legacy = {"claude": "_find_claude_cli", "codex": "_find_codex_cli", "gemini": "_find_agy_cli"}
        for p in PROVIDERS:
            with self.subTest(provider=p):
                self.assertIsNone(find(p))
                app = self.put(self.final(p))
                self.assertEqual(norm(find(p)), norm(app), "앱 전용 bin 의 %s 를 찾지 못했다" % p)
                self.assertEqual(norm(_require(legacy[p])()), norm(app))
                user = self.put(os.path.join(self.home, ".local", "bin", EXE[p]))
                self.assertEqual(norm(find(p)), norm(user), "사용자가 깐 것보다 앱 bin 을 먼저 봤다")
                onpath = self.put(os.path.join(self.base, "onpath", EXE[p]))
                self.which[EXE[p]] = onpath
                self.assertEqual(norm(find(p)), norm(onpath))
                self.which[EXE[p]] = None
                os.unlink(user)
                os.unlink(app)
                os.symlink(onpath, app)
                self.assertIsNone(find(p), "앱 bin 의 링크를 CLI 로 받아들였다")
                os.unlink(app)


# ═════════════════════════════ I4 — 무엇을 어디서 받는가 ═════════════════════════════


class ReleaseInfoTests(CliCase):

    MATRIX = (("Darwin", "arm64"), ("Darwin", "x86_64"), ("Windows", "AMD64"))

    def test_each_provider_resolves_its_official_file_hash_kind_and_member(self):
        """I4: 세 공급자 × (macOS arm64 / macOS x86_64 / Windows x64). 주소·해시 종류(SHA-256/256/512)·
        아카이브 종류·꺼낼 엔트리 이름이 계약 그대로다. 물은 주소는 공식 매니페스트뿐이다.
        Rivals: install.sh/ps1 을 받아 실행; 다른 플랫폼의 체크섬을 씀(arm64 Mac 에 x64 를 받는다);
        Codex 의 패키지 자산(codex-package-…)이나 비압축 exe 를 고름; agy 에 SHA-256 을 기대."""
        info = _require("cli_release_info")
        for system, machine in self.MATRIX:
            for p in PROVIDERS:
                with self.subTest(provider=p, system=system, machine=machine):
                    net = Net()
                    rel = net.serve(Release(p, system, machine))
                    got = info(p, net.http_get, system=system, machine=machine)
                    self.assertEqual({k: got.get(k) for k in ("version", "url", "alg", "archive", "member")},
                                     {"version": rel.version, "url": rel.url, "alg": rel.alg,
                                      "archive": rel.archive, "member": rel.member})
                    self.assertEqual(got["digest"].lower(), rel.digest)
                    self.assertEqual(sorted(net.gets), sorted(rel.http), "공식 매니페스트 말고 다른 것을 물었다")
                    self.assertEqual(net.opens, [], "정보만 물었는데 파일을 받기 시작했다")
        self.assertEqual(self.urlopens, [])

    def test_codex_falls_back_to_the_github_release_only_when_the_channel_fails(self):
        """I4: `releases.openai.com/codex/channels/latest` 가 실패하면 GitHub `openai/codex` releases/latest.
        Rival: 언제나 GitHub(비인증 시간당 60회 제한에 걸린다); 폴백 없음."""
        info = _require("cli_release_info")
        rel = Release("codex", "Darwin", "arm64")
        net = Net()
        net.files[rel.url] = rel.payload
        net.http[CODEX_GITHUB] = rel.meta
        got = info("codex", net.http_get, system="Darwin", machine="arm64")
        self.assertEqual(net.gets, [CODEX_CHANNEL, CODEX_GITHUB])
        self.assertEqual((got["url"], got["digest"].lower()), (rel.url, rel.digest))
        net2 = Net()
        net2.serve(rel)
        net2.http[CODEX_GITHUB] = b"{}"
        info("codex", net2.http_get, system="Darwin", machine="arm64")
        self.assertEqual(net2.gets, [CODEX_CHANNEL], "채널이 답했는데 GitHub 도 물었다")

    def test_a_manifest_that_cannot_be_trusted_is_refused_before_anything_is_downloaded(self):
        """I4: 믿을 수 없는 매니페스트는 받기 전에 거절한다(CliInstallError, kind "manifest"; 서버가 안 답하면
        "network"; 지원하지 않는 플랫폼은 "unsupported").
        Rivals: 버전 문자열을 그대로 주소에 끼움("../" 로 다른 경로를 받는다); http:// 주소를 받음; 해시가 없으면
        검증을 건너뜀; 다른 자산으로 대신함."""
        info = _require("cli_release_info")
        Err = _require("CliInstallError")

        def kind(provider, net, system="Darwin", machine="arm64"):
            try:
                info(provider, net.http_get, system=system, machine=machine)
            except Err as e:
                return e.kind
            except Exception as e:  # noqa: BLE001
                self.fail("CliInstallError 가 아닌 예외: %s" % type(e).__name__)
            return None

        def served(provider, change):
            net = Net()
            rel = net.serve(Release(provider, "Darwin", "arm64"))
            change(net, rel)
            return net

        def edit(url, fn):
            def change(net, rel):
                obj = json.loads(net.http[url if isinstance(url, str) else url(rel)])
                fn(obj)
                net.http[url if isinstance(url, str) else url(rel)] = json.dumps(obj).encode()
            return change

        claude_manifest = lambda rel: "%s/%s/manifest.json" % (CLAUDE_BASE, rel.version)   # noqa: E731
        agy = AGY_MANIFESTS + "darwin_arm64.json"
        codex_asset = lambda o: next(a for a in o["assets"]                                  # noqa: E731
                                     if a["name"] == "codex-aarch64-apple-darwin.tar.gz")
        cases = [
            ("claude latest 가 경로 문자", "claude",
             lambda net, rel: net.http.__setitem__(CLAUDE_BASE + "/latest", b"../../evil\n"), "manifest"),
            ("claude latest 가 HTML", "claude",
             lambda net, rel: net.http.__setitem__(CLAUDE_BASE + "/latest", b"<html>rate limited</html>"),
             "manifest"),
            ("claude 체크섬 없음", "claude",
             edit(claude_manifest, lambda o: o["platforms"]["darwin-arm64"].pop("checksum")), "manifest"),
            ("claude 체크섬이 64자 16진수가 아님", "claude",
             edit(claude_manifest, lambda o: o["platforms"]["darwin-arm64"].update(checksum="abc")), "manifest"),
            ("claude 이 플랫폼이 없음", "claude",
             edit(claude_manifest, lambda o: o["platforms"].pop("darwin-arm64")), "manifest"),
            ("claude binary 이름이 경로", "claude",
             edit(claude_manifest, lambda o: o["platforms"]["darwin-arm64"].update(binary="../x")), "manifest"),
            ("claude 매니페스트가 JSON 아님", "claude",
             lambda net, rel: net.http.__setitem__(claude_manifest(rel), b"not json"), "manifest"),
            ("codex 자산 없음", "codex",
             edit(CODEX_CHANNEL, lambda o: o["assets"].remove(codex_asset(o))), "manifest"),
            ("codex digest 가 sha256 이 아님", "codex",
             edit(CODEX_CHANNEL, lambda o: codex_asset(o).update(digest="md5:" + "a" * 32)), "manifest"),
            ("codex digest 없음", "codex",
             edit(CODEX_CHANNEL, lambda o: codex_asset(o).pop("digest")), "manifest"),
            ("codex 주소가 http", "codex",
             edit(CODEX_CHANNEL, lambda o: codex_asset(o).update(
                 browser_download_url="http://releases.openai.com/x.tar.gz")), "manifest"),
            ("agy sha512 가 128자가 아님", "gemini",
             edit(agy, lambda o: o.update(sha512="a" * 64)), "manifest"),
            ("agy 주소가 http", "gemini",
             edit(agy, lambda o: o.update(url="http://storage.googleapis.com/x.tar.gz")), "manifest"),
            ("agy 주소 없음", "gemini", edit(agy, lambda o: o.pop("url")), "manifest"),
            ("agy 가 목록", "gemini", lambda net, rel: net.http.__setitem__(agy, b"[]"), "manifest"),
        ]
        for name, provider, change, want in cases:
            with self.subTest(case=name):
                net = served(provider, change)
                self.assertEqual(kind(provider, net), want)
                self.assertEqual(net.opens, [])
        for p in PROVIDERS:
            with self.subTest(provider=p, case="서버가 답하지 않음"):
                self.assertEqual(kind(p, Net()), "network")
            for system, machine in (("Linux", "x86_64"), ("Windows", "ARM64"), ("Darwin", "ppc")):
                with self.subTest(provider=p, system=system, machine=machine):
                    net = Net()
                    self.assertEqual(kind(p, net, system, machine), "unsupported")
                    self.assertEqual(net.gets, [], "지원하지 않는 플랫폼인데 서버에 물었다")


# ═════════════════════════════ I4 — 받기·꺼내기·서명 ═════════════════════════════


class StageDownloadTests(CliCase):

    URL = "https://downloads.example.invalid/file?" + SECRET_QUERY
    BODY = bytes(range(256)) * 1200          # 307,200 바이트 — 여러 청크

    def stage(self, alg="sha256", digest=None, **kw):
        self.net.files[self.URL] = self.BODY
        return _require("cli_stage_download")(
            self.URL, alg, sha(alg, self.BODY) if digest is None else digest, self.net.opener, **kw)

    def kind(self, **kw):
        try:
            self.stage(**kw)
        except _require("CliInstallError") as e:
            return e.kind
        self.fail("CliInstallError 를 내지 않았다")

    def test_the_file_is_streamed_into_a_private_staging_folder_and_hashed(self):
        """I4: 앱 bin 의 `staging/`(0700)에 난수 이름으로 새로 만들어(O_EXCL) 청크로 받으며 해시한다. 진행률을
        알린다. SHA-256·SHA-512 둘 다, 16진수의 대소문자는 가리지 않는다.
        Rivals: read() 로 통째로 메모리에(수백 MB); 임시 폴더에 받음(다른 볼륨 — os.replace 가 원자적이 아니다);
        고정 이름(동시에 두 번 누르면 섞인다)."""
        marks = []
        path = self.stage(progress=lambda done, total: marks.append((done, total)))
        staging = os.path.join(self.bin_dir(), "staging")
        self.assertEqual(norm(os.path.dirname(path)), norm(staging))
        self.assertEqual(rb(path), self.BODY)
        self.assertGreater(len(self.net.reads), 2, "청크로 읽지 않았다")
        self.assertGreaterEqual(self.net.closed, 1, "응답을 닫지 않았다")
        self.assertEqual(marks[-1], (len(self.BODY), len(self.BODY)))
        self.assertGreater(len(marks), 2, "진행률을 알리지 않았다")
        self.assertEqual([d for d, _t in marks], sorted(d for d, _t in marks))
        if not REAL_WINDOWS:
            self.assertEqual(stat.S_IMODE(os.lstat(staging).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.lstat(self.bin_dir()).st_mode), 0o700)
            self.assertFalse(stat.S_IMODE(os.lstat(path).st_mode) & 0o022)
        second = self.stage("sha512", sha("sha512", self.BODY).upper())
        self.assertNotEqual(norm(second), norm(path), "받는 파일의 이름이 고정이다")
        self.assert_no_secrets_logged()

    def test_a_wrong_hash_a_broken_connection_and_a_cancel_leave_nothing_behind(self):
        """I4: 해시가 다르면 "hash", 연결이 끊기면 "network", 사용자가 취소하면 "cancelled" — 어느 경우든
        staging 에 파일이 남지 않는다. 길이가 맞아도 내용이 다르면 거절한다.
        Rivals: 해시를 안 봄; 크기만 봄; 실패한 반쪽 파일을 남김(다음 실행이 그것을 쓴다); 취소를 끝까지 받은
        뒤에야 봄."""
        self.assertEqual(self.kind(digest="0" * 64), "hash")
        self.assertEqual(self.staging_files(), [])
        self.assertEqual(self.kind(alg="sha512", digest=sha("sha256", self.BODY)), "hash")
        self.assertEqual(self.staging_files(), [])
        self.net.reads.clear()
        self.net.break_after = 2
        self.assertEqual(self.kind(), "network")
        self.assertEqual(self.staging_files(), [])
        self.net.break_after = None
        self.net.reads.clear()
        self.net.cancel_after = 2
        self.assertEqual(self.kind(cancel=self.net.cancel), "cancelled")
        self.assertLess(len(self.net.reads), 5, "취소한 뒤에도 계속 받았다")
        self.assertEqual(self.staging_files(), [])
        self.net.cancel_after = None
        try:
            _require("cli_stage_download")("https://downloads.example.invalid/none", "sha256", "0" * 64,
                                           self.net.opener)
        except _require("CliInstallError") as e:
            self.assertEqual(e.kind, "network")
        else:
            self.fail("없는 주소인데 예외가 없다")
        self.assert_no_secrets_logged()


class ExtractOneTests(CliCase):

    BIN = b"\xcf\xfa\xed\xfe synthetic binary " * 500

    def run_extract(self, kind, data, member):
        src = os.path.join(self.base, "work", "a." + kind)
        os.makedirs(os.path.dirname(src), exist_ok=True)
        with open(src, "wb") as f:
            f.write(data)
        dest = os.path.join(self.base, "work", "out", "bin")
        shutil.rmtree(os.path.dirname(dest), ignore_errors=True)
        os.makedirs(os.path.dirname(dest))
        try:
            _require("cli_extract_one")(src, kind, member, dest)
        except _require("CliInstallError") as e:
            return e.kind, dest
        except Exception as e:  # noqa: BLE001
            self.fail("CliInstallError 가 아닌 예외: %s" % type(e).__name__)
        return None, dest

    def assert_nothing_escaped(self, dest, extracted):
        work = os.path.join(self.base, "work")
        seen = sorted(os.path.relpath(os.path.join(r, f), work)
                      for r, _d, fs in os.walk(work) for f in fs)
        want = ["a.tar.gz", "a.zip"]
        self.assertEqual([s for s in seen if s not in want], [os.path.join("out", "bin")] if extracted else [])
        self.assertFalse(os.path.exists(os.path.join(self.base, "evil")), "아카이브의 다른 엔트리가 밖으로 나왔다")
        if extracted:
            self.assertTrue(stat.S_ISREG(os.lstat(dest).st_mode))

    def test_only_the_expected_entry_comes_out_as_a_plain_file(self):
        """I4: 아카이브에서 기대한 실행 파일 **한 엔트리만** 보통 파일로 꺼낸다(tar.gz·zip). 같이 든 다른
        엔트리(`..` 경로·절대 경로·링크)는 어디에도 풀리지 않는다.
        Rival: extractall(다른 엔트리가 bin 밖에 쓰인다 — 경로 탈출)."""
        evil = [("../../evil", b"x"), ("/abs-evil", b"x"), ("sub/readme", b"x"), ("lnk", ("link", "/etc/hosts"))]
        for kind, data in (("tar.gz", tar_gz(evil[:2] + [("antigravity", self.BIN)] + evil[2:])),
                           ("zip", zip_bytes([("../../evil", b"x"), ("tool.exe", self.BIN), ("sub/x", b"x")]))):
            with self.subTest(kind=kind):
                got, dest = self.run_extract(kind, data, "antigravity" if kind == "tar.gz" else "tool.exe")
                self.assertIsNone(got)
                self.assertEqual(rb(dest), self.BIN)
                self.assert_nothing_escaped(dest, True)

    def test_a_missing_linked_or_odd_entry_is_refused(self):
        """I4: 기대한 엔트리가 없거나, 심볼릭/하드 링크거나, 폴더거나, 아카이브가 깨졌으면 "archive" — 아무것도
        쓰지 않는다. 이름이 `..` 를 지나 같은 곳을 가리키는 엔트리(`x/../antigravity`)는 그 엔트리가 아니다.
        Rivals: 링크를 따라가 다른 파일을 설치; 이름을 정규화해 받아들임; 깨진 아카이브에 예외를 그대로 던짐."""
        tars = [("없음", tar_gz([("other", self.BIN)]), "antigravity"),
                ("심볼릭 링크", tar_gz([("antigravity", ("link", "/bin/sh"))]), "antigravity"),
                ("하드 링크", tar_gz([("real", self.BIN), ("antigravity", ("hard", "real"))]), "antigravity"),
                ("폴더", tar_gz([("antigravity", ("dir",))]), "antigravity"),
                ("이름이 돌아서 옴", tar_gz([("x/../antigravity", self.BIN)]), "antigravity"),
                ("같은 이름이 둘 — 뒤가 링크", tar_gz([("antigravity", self.BIN),
                                                 ("antigravity", ("link", "/bin/sh"))]), "antigravity"),
                ("깨진 gzip", b"\x1f\x8b" + b"broken" * 20, "antigravity"),
                ("tar 가 아님", self.BIN, "antigravity")]
        for name, data, member in tars:
            with self.subTest(tar=name):
                got, dest = self.run_extract("tar.gz", data, member)
                self.assertEqual(got, "archive")
                self.assert_nothing_escaped(dest, False)
        zips = [("없음", zip_bytes([("other.exe", self.BIN)]), "tool.exe"),
                ("심볼릭 링크", zip_bytes([("tool.exe", ("link", "C:/Windows/System32/cmd.exe"))]), "tool.exe"),
                ("zip 이 아님", self.BIN, "tool.exe")]
        for name, data, member in zips:
            with self.subTest(zip=name):
                got, dest = self.run_extract("zip", data, member)
                self.assertEqual(got, "archive")
                self.assert_nothing_escaped(dest, False)

    def test_the_core_never_calls_extractall_or_turns_off_tls_checks(self):
        """I4: `extractall` 금지, TLS 검증 우회 금지(코드 어디에도). Rival: 인증서 오류를 만나 검증을 끔."""
        tree = ast.parse(CORE.read_text(encoding="utf-8"))
        names = [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)] + \
                [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
        for banned in ("extractall", "_create_unverified_context", "CERT_NONE"):
            self.assertNotIn(banned, names)
        off = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Attribute) and t.attr == "check_hostname" for t in n.targets)
               and isinstance(n.value, ast.Constant) and n.value.value is False]
        self.assertEqual(off, [], "check_hostname = False")


class SignatureTests(CliCase):

    def codesign(self, verify_rc=0, team="Q6L2SF6YDW", raises=None):
        calls = []

        def run(argv, *a, **k):
            argv = [str(x) for x in argv]
            calls.append((argv, dict(k)))
            if raises:
                raise raises
            if "--verify" in argv:
                return subprocess.CompletedProcess(argv, verify_rc, "", "" if verify_rc == 0 else "invalid\n")
            err = "Executable=/synthetic\nIdentifier=synthetic\n"
            if team is not None:
                err += "TeamIdentifier=%s\n" % team
            return subprocess.CompletedProcess(argv, 0, "", err)
        self._patch(mock.patch.object(claude_pet.subprocess, "run", run))
        return calls

    def test_the_team_ids_and_publishers_are_the_vendors(self):
        """I4: macOS TeamIdentifier — claude `Q6L2SF6YDW`, agy `EQHXZ8M8AV`, codex 는 Developer 가 실측해 넣은
        10자 값. Windows Authenticode 주체 O — `Anthropic, PBC` / `OpenAI OpCo, LLC` / `Google LLC`."""
        teams = getattr(claude_pet, "CLI_TEAM_IDS", None)
        self.assertIsInstance(teams, dict, "CLI_TEAM_IDS 가 없다")
        self.assertEqual((teams.get("claude"), teams.get("gemini")), ("Q6L2SF6YDW", "EQHXZ8M8AV"))
        codex = teams.get("codex")
        self.assertTrue(isinstance(codex, str) and len(codex) == 10 and codex.isalnum() and codex.isupper(),
                        "codex 의 TeamIdentifier 를 실측해 고정하지 않았다: %r" % (codex,))
        self.assertEqual(len(set(teams.values())), 3)
        self.assertEqual(getattr(claude_pet, "CLI_AUTHENTICODE_ORGS", None),
                         {"claude": "Anthropic, PBC", "codex": "OpenAI OpCo, LLC", "gemini": "Google LLC"})

    def test_macos_needs_a_valid_signature_from_that_vendors_team(self):
        """I4: `/usr/bin/codesign --verify --strict <파일>` 이 0 이고 TeamIdentifier 가 그 공급자의 것일 때만 True.
        Rivals: 해시만 믿음; 서명이 유효하기만 하면 됨(다른 회사가 서명한 것을 claude 로 설치); PATH 의 codesign;
        codesign 이 없으면 통과; TeamIdentifier 가 "not set"(ad-hoc)인데 통과."""
        ok = _require("cli_signature_ok")
        teams = _require("CLI_TEAM_IDS")
        target = self.put(os.path.join(self.bin_dir(), "staging", "x"))
        for p in PROVIDERS:
            with self.subTest(provider=p):
                calls = self.codesign(team=teams[p])
                self.assertIs(ok(p, target), True)
                verify = [a for a, _k in calls if "--verify" in a]
                self.assertEqual(len(verify), 1)
                self.assertEqual(verify[0][0], "/usr/bin/codesign")
                self.assertIn("--strict", verify[0])
                self.assertEqual(norm(verify[0][-1]), norm(target))
                for argv, kw in calls:
                    self.assertEqual(argv[0], "/usr/bin/codesign")
                    self.assertFalse(kw.get("shell"))
                    self.assertIsInstance(kw.get("timeout"), (int, float), "codesign 에 timeout 이 없다")
                wrong = teams["gemini" if p != "gemini" else "claude"]
                for name, kw in (("서명 무효", {"verify_rc": 1, "team": teams[p]}),
                                 ("다른 회사의 서명", {"team": wrong}),
                                 ("TeamIdentifier 없음", {"team": None}),
                                 ("ad-hoc", {"team": "not set"}),
                                 ("codesign 없음", {"raises": FileNotFoundError("synthetic")}),
                                 ("codesign 멈춤", {"raises": subprocess.TimeoutExpired("codesign", 1)})):
                    with self.subTest(case=name):
                        self.codesign(**kw)
                        self.assertIs(ok(p, target), False)

    def test_windows_needs_a_valid_authenticode_signature_whose_organisation_is_the_vendor(self):
        """I4: Authenticode 상태가 "Valid" 이고 주체의 O 가 그 공급자일 때만 True. O 는 통째로 같아야 한다 —
        쉼표가 든 값은 따옴표로 묶여 온다.
        Rivals: CN 만 봄; 부분 문자열(`O=Google LLC Fake`); 상태를 안 봄(서명은 있는데 해시가 안 맞는 파일)."""
        ok = _require("authenticode_ok")
        good = {"claude": 'CN="Anthropic, PBC", O="Anthropic, PBC", L=San Francisco, S=California, C=US',
                "codex": 'CN="OpenAI OpCo, LLC", O="OpenAI OpCo, LLC", L=San Francisco, S=California, C=US',
                "gemini": "CN=Google LLC, O=Google LLC, L=Mountain View, S=California, C=US"}
        for p in PROVIDERS:
            with self.subTest(provider=p):
                self.assertIs(ok(p, "Valid", good[p]), True)
                for status in ("NotSigned", "HashMismatch", "UnknownError", "NotTrusted", "", None, "valid "):
                    self.assertIs(ok(p, status, good[p]), False, "상태 %r 를 받아들였다" % (status,))
                other = good["gemini" if p != "gemini" else "codex"]
                self.assertIs(ok(p, "Valid", other), False, "다른 회사의 서명을 받아들였다")
                self.assertIs(ok(p, "Valid", ""), False)
                self.assertIs(ok(p, "Valid", None), False)
        self.assertIs(ok("gemini", "Valid", "CN=Google LLC, O=Evil Corp, C=US"), False, "CN 만 봤다")
        self.assertIs(ok("gemini", "Valid", "CN=x, O=Google LLC Fake, C=US"), False, "부분 문자열로 봤다")
        self.assertIs(ok("gemini", "Valid", "CN=x, OU=Google LLC, O=Other, C=US"), False)
        self.assertIs(ok("claude", "Valid", "CN=x, O=Anthropic, OU=PBC, C=US"), False)
        self.assertIs(ok("nope", "Valid", good["gemini"]), False)


# ═════════════════════════════ I3·I4·I6 — 설치 한 번 ═════════════════════════════


class InstallCase(CliCase):

    def setUp(self):
        super().setUp()
        self.verified = []
        self.sig = True
        self.replaced = []
        real_replace = os.replace

        def replace(src, dst, *a, **k):
            self.replaced.append((str(src), str(dst)))
            return real_replace(src, dst, *a, **k)
        self._patch(mock.patch.object(claude_pet.os, "replace", replace))
        self._patch(mock.patch.object(claude_pet, "cli_signature_ok", self._verify, create=True))

    def _verify(self, provider, path):
        final = self.final(provider)
        self.verified.append((provider, str(path), rb(path),
                              rb(final) if os.path.exists(final) else None))
        return self.sig

    def install(self, provider, **kw):
        system, machine = self.system_machine()
        try:
            return _require("install_cli")(provider, http_get=self.net.http_get, opener=self.net.opener,
                                           system=system, machine=machine, **kw)
        except Exception as e:  # noqa: BLE001
            self.fail("install_cli 가 예외를 냈다: %s" % type(e).__name__)

    def release(self, provider, **kw):
        system, machine = self.system_machine()
        return self.net.serve(Release(provider, system, machine, **kw))


class InstallTests(InstallCase):

    def test_install_downloads_verifies_then_swaps_the_binary_into_the_app_bin(self):
        """I3·I4: 받기 → 해시 → (아카이브면 한 엔트리 꺼내기) → 서명 확인 → 같은 볼륨 os.replace. 끝나면 앱 bin
        (0700)에 실행 파일(0755) 하나, staging 은 비고, 버전 메타가 남는다. 서명 확인은 **바꿔 넣기 전에**
        staging 의 파일에 한다. 공식 설치 스크립트·`claude install` 은 실행하지 않고, 사용자의 셸 설정·PATH·홈을
        건드리지 않는다.
        Rivals: 서명 확인 전에 bin 에 둠(확인이 실패해도 실행 파일이 남는다); 아카이브를 그대로 bin 에 둠;
        ~/.zshrc 에 PATH 를 더함; install.sh 를 받아 bash 로 실행; shutil.move(다른 볼륨이면 복사 도중 반쪽
        파일이 실행된다)."""
        before = dict(os.environ)
        for p in PROVIDERS:
            with self.subTest(provider=p):
                rel = self.release(p)
                ok, path = self.install(p)
                self.assertIs(ok, True, "설치 실패: %r" % (path,))
                final = self.final(p)
                self.assertEqual(norm(path), norm(final))
                self.assertEqual(rb(final), rel.binary, "설치된 파일이 받은 실행 파일이 아니다")
                st = os.lstat(final)
                self.assertTrue(stat.S_ISREG(st.st_mode))
                self.assertEqual(stat.S_IMODE(st.st_mode), 0o755)
                self.assertEqual(stat.S_IMODE(os.lstat(self.bin_dir()).st_mode), 0o700)
                self.assertEqual(self.staging_files(), [], "staging 을 치우지 않았다")
                prov, staged, staged_body, final_then = self.verified[-1]
                self.assertEqual(prov, p)
                self.assertEqual(norm(os.path.dirname(staged)), norm(os.path.join(self.bin_dir(), "staging")))
                self.assertEqual(staged_body, rel.binary, "서명 확인한 것이 설치할 실행 파일이 아니다")
                self.assertIsNone(final_then, "서명 확인 전에 이미 bin 에 넣었다")
                swaps = [src for src, dst in self.replaced if norm(dst) == norm(final)]
                self.assertEqual(len(swaps), 1, "실행 파일을 os.replace 로 한 번에 바꿔 넣지 않았다")
                self.assertEqual(norm(os.path.dirname(swaps[0])), norm(os.path.join(self.bin_dir(), "staging")),
                                 "같은 볼륨(staging)에서 바꿔 넣지 않았다")
                meta = _require("read_app_cli_meta")(p)
                self.assertEqual((meta or {}).get("version"), rel.version)
                self.assertEqual(norm(_require("find_cli")(p)), norm(final))
                self.assertEqual(self.net.opens, [rel.url])
                self.net.opens.clear()
        self.assertEqual(self.spawned, [], "설치 중에 무언가를 실행했다")
        self.assertEqual([u for u in self.net.gets if "install." in u], [])
        self.assertEqual(self.urlopens, [])
        self.assertTrue(dict(os.environ) == before, "앱의 환경을 바꿨다")
        self.assert_user_shell_untouched()
        self.assert_no_secrets_logged()

    def test_windows_installs_exe_names_from_the_zip_and_the_bare_exe(self):
        """Windows: claude.exe(단일), codex.exe(zip 의 한 엔트리), agy.exe(단일) — %LOCALAPPDATA% 의 앱 bin 에."""
        self.platform = "win32"
        self._patch(mock.patch.object(sys, "platform", "win32"))
        for p in PROVIDERS:
            with self.subTest(provider=p):
                rel = self.release(p)
                ok, path = self.install(p)
                self.assertIs(ok, True, "설치 실패: %r" % (path,))
                self.assertEqual(norm(path), norm(self.final(p)))
                self.assertTrue(path.lower().endswith(".exe"))
                self.assertEqual(rb(path), rel.binary)
                self.assertEqual(self.staging_files(), [])

    def test_every_failure_cleans_staging_and_leaves_the_old_binary_alone(self):
        """I4: 실패·취소·예외 시 staging 삭제. 이미 있던 앱 bin 의 실행 파일과 버전 메타는 그대로다. 결과는
        (False, kind) — 예외가 아니다.
        Rivals: 해시가 틀린 파일을 그래도 설치; 서명이 틀렸는데 설치; 실패한 파일을 staging 에 남김; 실패하면서
        옛 실행 파일을 지움."""
        for p in PROVIDERS:
            rel = self.release(p, version="1.0.0")
            self.assertEqual(self.install(p)[0], True)
            old = rb(self.final(p))
            newer = Release(p, *self.system_machine(), version="2.0.0",
                            binary=b"\xcf\xfa\xed\xfe newer " * 4000)
            evil_tar = tar_gz([("something-else", newer.binary)])

            def tampered(net):
                net.serve(newer, payload=newer.payload[:-1] + bytes([newer.payload[-1] ^ 1]))

            def unsigned(net):
                net.serve(newer)
                self.sig = False

            def cancelled(net):
                net.serve(newer)
                net.cancel_after = 1

            def broken(net):
                net.serve(newer)
                net.break_after = 1

            def raising_verify(net):
                net.serve(newer)
                self.sig = None

            cases = [("hash", tampered), ("signature", unsigned), ("cancelled", cancelled),
                     ("network", broken), ("signature", raising_verify),
                     ("manifest", lambda net: (net.serve(newer), net.http.update(
                         {k: b"{}" for k in newer.http if k.endswith(".json") or "channels" in k})))]
            if newer.archive:
                def wrong_member(net):
                    net.serve(newer)
                    net.files[newer.url] = evil_tar if newer.archive == "tar.gz" else b"not an archive"
                    for url, body in list(net.http.items()):
                        obj = json.loads(body)
                        fixed = sha(newer.alg, net.files[newer.url])
                        if "sha512" in obj:
                            obj["sha512"] = fixed
                        for a in obj.get("assets", []):
                            if a["browser_download_url"] == newer.url:
                                a["digest"] = "sha256:" + fixed
                        net.http[url] = json.dumps(obj).encode()
                cases.append(("archive", wrong_member))
            for want, arrange in cases:
                with self.subTest(provider=p, failure=want):
                    self.net = Net()
                    self.sig = True
                    arrange(self.net)
                    if self.sig is None:
                        with mock.patch.object(claude_pet, "cli_signature_ok",
                                               side_effect=RuntimeError("synthetic")):
                            got = self.install(p, cancel=self.net.cancel)
                    else:
                        got = self.install(p, cancel=self.net.cancel)
                    self.assertEqual(tuple(got), (False, want))
                    self.assertEqual(self.staging_files(), [], "실패한 뒤 staging 에 파일이 남았다")
                    self.assertEqual(rb(self.final(p)), old, "실패했는데 실행 파일이 바뀌었다")
                    self.assertEqual(_require("read_app_cli_meta")(p).get("version"), "1.0.0")
            self.net = Net()
            self.sig = True
            del rel
        self.assert_no_secrets_logged()

    def test_a_cli_the_user_already_has_is_used_and_nothing_is_downloaded(self):
        """I2: 이미 있으면 쓰고 받지 않는다 — 서버에 묻지도 않는다.
        Rival: [설치]를 누르면 무조건 받음(사용자가 깐 것과 앱이 받은 것 두 벌이 생긴다)."""
        for p in PROVIDERS:
            with self.subTest(provider=p):
                self.release(p)
                user = self.put(os.path.join(self.home, ".local", "bin", EXE[p]))
                ok, path = self.install(p)
                self.assertIs(ok, True)
                self.assertEqual(norm(path), norm(user))
                self.assertEqual((self.net.gets, self.net.opens), ([], []))
                self.assertFalse(os.path.exists(self.final(p)))
                os.unlink(user)


class UpdateTests(InstallCase):

    DAY = 86400

    def update(self, provider, now, **kw):
        system, machine = self.system_machine()
        try:
            return _require("update_app_cli")(provider, http_get=self.net.http_get, opener=self.net.opener,
                                              system=system, machine=machine, now=now, **kw)
        except Exception as e:  # noqa: BLE001
            self.fail("update_app_cli 가 예외를 냈다: %s" % type(e).__name__)

    def test_only_a_cli_the_app_installed_is_updated_and_at_most_once_a_day(self):
        """I6: 앱이 깐 CLI 만, 하루 한 번 이하, 공식 최신 버전이 메타의 버전과 다를 때만 같은 받기·검증으로
        교체. 버전은 메타파일에서 읽는다 — 확인하려고 CLI 를 띄우지 않는다.
        Rivals: 새로고침마다 서버에 물음; `claude --version` 을 띄워 버전을 봄; 같은 버전인데 다시 받음;
        사용자가 깐 CLI 를 덮어씀."""
        due = _require("app_cli_update_due")
        t0 = 1_800_000_000.0
        for p in PROVIDERS:
            with self.subTest(provider=p):
                self.net = Net()
                self.assertIs(due(p, t0), False, "앱이 깔지 않은 CLI 를 갱신하려 한다")
                self.assertFalse(self.update(p, t0))
                self.assertEqual(self.net.gets, [])
                rel = self.release(p, version="1.0.0")
                with mock.patch.object(claude_pet.time, "time", lambda: t0):
                    self.assertIs(self.install(p)[0], True)
                self.assertIs(due(p, t0 + self.DAY - 60), False, "하루가 안 됐는데 확인하려 한다")
                self.assertIs(due(p, t0 + self.DAY + 60), True)
                # 같은 버전 — 묻기만 하고 받지 않는다. 확인 시각이 남아 다음 하루 동안 다시 묻지 않는다.
                self.net.gets.clear(); self.net.opens.clear()
                self.update(p, t0 + self.DAY + 60)
                self.assertTrue(self.net.gets)
                self.assertEqual(self.net.opens, [], "같은 버전인데 다시 받았다")
                self.assertIs(due(p, t0 + self.DAY + 120), False, "확인한 시각을 남기지 않았다")
                # 새 버전 — 교체.
                self.net = Net()
                newer = self.release(p, version="2.0.0", binary=b"\xcf\xfa\xed\xfe newer " * 4000)
                self.update(p, t0 + 2 * self.DAY + 120)
                self.assertEqual(rb(self.final(p)), newer.binary)
                self.assertEqual(_require("read_app_cli_meta")(p).get("version"), "2.0.0")
                self.assertEqual(self.staging_files(), [])
                # 사용자가 따로 깔았다 — 사용자의 것은 절대 건드리지 않는다.
                user = self.put(os.path.join(self.home, ".local", "bin", EXE[p]), b"user's own")
                self.net = Net()
                self.release(p, version="3.0.0", binary=b"\xcf\xfa\xed\xfe newest " * 4000)
                self.update(p, t0 + 9 * self.DAY)
                self.assertEqual(rb(user), b"user's own", "사용자가 깐 CLI 를 덮어썼다")
                os.unlink(user)
        self.assertEqual(self.spawned, [], "버전을 보려고 CLI 를 띄웠다")
        del rel

    def test_a_binary_locked_by_a_running_cli_skips_this_round(self):
        """I6(agy 동의 보완): Windows 에서 실행 중이라 바꿔 넣을 수 없으면(PermissionError) 그 주기는 조용히
        건너뛴다 — 옛 실행 파일은 그대로, staging 은 비운다, 예외 없음.
        Rival: 예외가 새로고침 워커를 죽임; 반쯤 지운 채 둠."""
        t0 = 1_800_000_000.0
        self.release("codex", version="1.0.0")
        with mock.patch.object(claude_pet.time, "time", lambda: t0):
            self.assertIs(self.install("codex")[0], True)
        old = rb(self.final("codex"))
        self.net = Net()
        self.release("codex", version="2.0.0", binary=b"\xcf\xfa\xed\xfe newer " * 4000)

        def locked(src, dst, *a, **k):
            if norm(dst) == norm(self.final("codex")):
                raise PermissionError(13, "synthetic: the file is in use")
            return os.rename(src, dst)
        with mock.patch.object(claude_pet.os, "replace", locked):
            self.update("codex", t0 + 2 * self.DAY)
        final = self.final("codex")
        moved = final + ".old"
        self.assertTrue(rb(final) == old or os.path.exists(moved),
                        "잠긴 실행 파일이 망가졌다")
        self.assertEqual(self.staging_files(), [])


# ═════════════════════════════ I5 — 로그인 ═════════════════════════════

_LOGIN_EMULATOR = r"""
import json, os, sys, time
spec = json.load(open(sys.argv[1], encoding="utf-8"))
sys.stderr.write(spec["stderr"]); sys.stderr.flush()
end = time.time() + spec["delay"]
while time.time() < end:
    time.sleep(0.02)
for path, body in spec["write"]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
sys.stdout.write(spec["stdout"]); sys.stdout.flush()
sys.exit(spec["rc"])
"""

GEMINI_OK = json.dumps({"schemaVersion": 1, "status": "SUCCESS", "command": {"name": "usage", "data": {
    "groups": [{"name": "Gemini Models", "buckets": [
        {"id": "gemini-5h", "window": "5h", "remaining_fraction": 0.5,
         "reset_time": "2099-01-01T05:00:00Z"}]}]}}}) + "\n"
GEMINI_PROMPT = ("Authentication required. Please visit the URL to log in:\n"
                 "  https://accounts.example.invalid/o/oauth2/auth?synthetic=1&state=SECRETSECRETSECRET\n\n"
                 "Waiting for authentication (timeout 60s)...\n")
CODEX_AUTH = json.dumps({"tokens": {"access_token": "synthetic-access", "account_id": "synthetic-acct"}})


class _LoginChild(_REAL_POPEN):
    case = None

    def kill(self):
        self.case.events.append("kill")
        return super().kill()

    def terminate(self):
        self.case.events.append("kill")
        return super().terminate()


class LoginCase(CliCase):

    def setUp(self):
        super().setUp()
        self.events = []            # "cancel-request" | "kill"
        self.children = []
        self.behave = {"stderr": "", "stdout": "", "rc": 0, "delay": 0.0, "write": []}
        self.kc = os.path.join(self.base, "keychain.json")       # agy 키체인 항목의 대역
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen", self._login_popen))
        self._patch(mock.patch.object(claude_pet.subprocess, "run", self._login_run))
        self._patch(mock.patch.object(claude_pet, "keychain_locked", lambda: False))
        self._patch(mock.patch.object(claude_pet.urllib.request, "urlopen", self._cancel_urlopen))
        if hasattr(os, "killpg"):
            real_killpg = os.killpg

            def killpg(pid, sig):
                self.events.append("kill")
                return real_killpg(pid, sig)
            self._patch(mock.patch.object(claude_pet.os, "killpg", killpg))
        self.addCleanup(self._reap)
        self.cli = {p: self.put(os.path.join(self.home, ".local", "bin", EXE[p])) for p in PROVIDERS}
        self.timeouts = dict(getattr(claude_pet, "CLI_LOGIN_TIMEOUT_SEC", {}) or {})

    def _reap(self):
        for c in self.children:
            try:
                if c.poll() is None:
                    _REAL_POPEN.kill(c)
                _REAL_POPEN.wait(c, 5)
                for s in (c.stdin, c.stdout, c.stderr):
                    if s is not None:
                        s.close()
            except Exception:  # noqa: BLE001
                pass

    def _cancel_urlopen(self, req, *a, **k):
        url = req if isinstance(req, str) else getattr(req, "full_url", str(req))
        self.urlopens.append((url, k.get("timeout", a[1] if len(a) > 1 else None)))
        if "127.0.0.1:1455/cancel" in url:
            self.events.append("cancel-request")
            return io.BytesIO(b"ok")
        raise OSError("synthetic: urlopen is not available in tests")

    def _login_run(self, argv, *a, **k):
        argv = [str(x) for x in argv]
        if os.path.basename(argv[0]) == "security":
            self.spawned.append((argv, dict(k)))
            try:
                mdat = json.loads(rb(self.kc))["mdat"]
            except (OSError, ValueError, KeyError):
                return subprocess.CompletedProcess(argv, 44, "", "not found\n")
            return subprocess.CompletedProcess(
                argv, 0, 'class: "genp"\nattributes:\n    "mdat"<timedate>=0x00 "%s\\000"\n' % mdat, "")
        self.spawned.append((argv, dict(k)))
        return subprocess.CompletedProcess(argv, 1, "", "")

    def _login_popen(self, argv, *a, **k):
        if isinstance(argv, (str, bytes)) or k.get("shell"):
            raise AssertionError("문자열 명령 — 셸 없이 argv 목록으로 띄워야 한다")
        argv = [str(x) for x in argv]
        self.spawned.append((argv, dict(k)))
        spec = os.path.join(self.base, "spec-%d.json" % len(self.spawned))
        with open(spec, "w", encoding="utf-8") as f:
            json.dump(self.behave, f)
        k = dict(k)
        for drop in ("executable", "cwd", "env", "creationflags", "startupinfo"):
            k.pop(drop, None)
        child = _LoginChild([sys.executable, "-I", "-S", "-c", _LOGIN_EMULATOR, spec], *a, env=REAL_ENV, **k)
        child.case = self
        self.children.append(child)
        return child

    def logins(self):
        return [(a, k) for a, k in self.spawned if os.path.basename(a[0]) in ("claude", "codex", "agy")]

    def login(self, provider, **kw):
        try:
            return _require("run_cli_login")(provider, **kw)
        except Exception as e:  # noqa: BLE001
            self.fail("run_cli_login 이 예외를 냈다: %s" % type(e).__name__)

    def short_timeout(self, provider, seconds=1.0):
        table = dict(self.timeouts)
        table[provider] = seconds
        self._patch(mock.patch.object(claude_pet, "CLI_LOGIN_TIMEOUT_SEC", table, create=True))

    def assert_child_is_gone(self):
        end = _real_time.time() + 3
        while _real_time.time() < end and any(c.poll() is None for c in self.children):
            _real_time.sleep(0.02)
        self.assertFalse([c for c in self.children if c.poll() is None], "로그인 프로세스가 남았다")

    def assert_spawn_shape(self, argv, kw, provider):
        self.assertFalse(kw.get("shell"))
        self.assertIn(kw.get("stdin"), (subprocess.DEVNULL,), "stdin 이 DEVNULL 이 아니다")
        cwd = kw.get("cwd")
        self.assertIsNotNone(cwd, "cwd 를 정하지 않았다")
        real = os.path.realpath(str(cwd))
        self.assertNotEqual(real, os.path.realpath(self.home), "CLI 를 홈에서 띄웠다")
        self.assertTrue(real.startswith(self.base), "cwd 가 앱의 전용 폴더가 아니다")
        self.assertEqual(os.listdir(real), [], "cwd 가 비어 있지 않다")
        self.assertFalse([a for a, _k in self.spawned if os.path.basename(a[0]) in ("open", "osascript")
                          or "Terminal" in a], "터미널을 열었다")


class LoginTableTests(CliCase):

    def test_the_login_commands_and_time_limits(self):
        """I5: Claude `[claude, auth, login, --claudeai]` 300초, Codex `[codex, login]` 300초.
        Gemini 는 (대표님 결정 2026-11-19) 보이는 창에서 `agy` 만 — `[agy]`, 앱이 끊는 시간 제한이 없다:
        CLI_LOGIN_TIMEOUT_SEC 에 gemini 가 없고, 표시용 `GEMINI_LOGIN_HINT_SEC = 300`("다시 시도" 안내)만 있다.
        Rivals: `--claudeai` 없음(구독/API 고르는 화면에서 멈춘다); Gemini 를 `-p /usage` 파이프로 띄움(코드를
        붙여 넣을 터미널이 없어 로그인이 끝나지 않는다 — Windows 실측); 90초 실행기가 남음."""
        argv = _require("cli_login_argv")
        self.assertEqual(argv("claude", "/x/claude"), ["/x/claude", "auth", "login", "--claudeai"])
        self.assertEqual(argv("codex", "/x/codex"), ["/x/codex", "login"])
        self.assertEqual(argv("gemini", "/x/agy"), ["/x/agy"])
        self.assertEqual(getattr(claude_pet, "CLI_LOGIN_TIMEOUT_SEC", None), {"claude": 300, "codex": 300})
        self.assertEqual(getattr(claude_pet, "GEMINI_LOGIN_HINT_SEC", None), 300)
        self.assertEqual(claude_pet.LOGIN_TIMEOUT_SEC, 300, "Claude 로그인 job 의 상한이 300초가 아니다")

    def test_the_environment_each_cli_is_started_with(self):
        """I5·I6: os.environ 의 사본. Gemini — SSH_* 를 지우고 AGY_CLI_DISABLE_AUTO_UPDATE=1, **가짜 open 을
        PATH 에 넣지 않는다**(브라우저가 떠야 한다). 앱 전용 bin 의 claude — DISABLE_AUTOUPDATER=1,
        DISABLE_INSTALLATION_CHECKS=1(사용자가 깐 claude 에는 넣지 않는다).
        Rivals: 폴링용 env 를 재사용(로그인 창이 안 뜬다); SSH_* 를 둠(agy 가 토큰을 파일에 쓴다); 사용자의
        claude 의 자동 업데이트를 끔; 앱 환경을 고침."""
        env_for = _require("cli_env")
        ssh = {"SSH_TTY": "x", "SSH_CLIENT": "y", "SSH_CONNECTION": "z"}
        self._patch(mock.patch.dict(os.environ, ssh))
        before = dict(os.environ)
        g = env_for("gemini", "/x/agy")
        self.assertFalse([k for k in ssh if k in g])
        self.assertEqual(g.get("AGY_CLI_DISABLE_AUTO_UPDATE"), "1")
        self.assertEqual(g.get("PATH"), before["PATH"], "로그인용 PATH 를 바꿨다(가짜 open?)")
        self.assertEqual(g.get("HOME"), self.home)
        app = self.put(self.final("claude"))
        a = env_for("claude", app)
        self.assertEqual((a.get("DISABLE_AUTOUPDATER"), a.get("DISABLE_INSTALLATION_CHECKS")), ("1", "1"))
        u = env_for("claude", "/x/user/claude")
        self.assertFalse("DISABLE_AUTOUPDATER" in u or "DISABLE_INSTALLATION_CHECKS" in u,
                         "사용자가 깐 claude 의 자동 업데이트를 껐다")
        c = env_for("codex", "/x/codex")
        self.assertEqual(c.get("PATH"), before["PATH"])
        self.assertTrue(dict(os.environ) == before, "앱 자신의 환경을 바꿨다")
        self.assertEqual(env_for("codex", "/x/codex", base_env={"A": "1"}).get("A"), "1")


class CodexLoginTests(LoginCase):

    def auth(self):
        return os.path.join(self.home, ".codex", "auth.json")

    def test_an_existing_codex_login_is_never_touched(self):
        """I2: 이미 로그인돼 있으면 `codex login` 을 띄우지 않는다 — 그 명령은 시작하자마자 기존 토큰을 지운다.
        Rival: 버튼만 숨기고 실행 직전에는 확인하지 않음(다른 길로 불리면 사용자가 로그아웃된다)."""
        self.put(self.auth(), CODEX_AUTH.encode(), 0o600)
        self.assertTrue(claude_pet.read_codex_token(self.auth()), "픽스처가 유효한 auth.json 이 아니다")
        self.assertIs(_require("cli_logged_in")("codex"), True)
        self.assertEqual(self.login("codex"), "already")
        self.assertEqual(self.logins(), [], "로그인돼 있는데 codex login 을 띄웠다")
        self.assertEqual(rb(self.auth()).decode("utf-8"), CODEX_AUTH)

    def test_success_is_exit_zero_and_a_token_in_auth_json(self):
        """I5: `[codex, login]` 을 터미널 없이(stdin DEVNULL, 빈 전용 cwd) 띄운다. 성공은 `rc == 0` **그리고**
        auth.json 에 토큰. rc 0 인데 토큰이 없으면 실패, rc 1 은 거부.
        Rivals: rc 만 믿음; 파일이 생겼는지만 봄(빈 파일); 터미널을 엶; 홈에서 띄움."""
        self.assertIs(_require("cli_logged_in")("codex"), False)
        self.behave.update(rc=0, delay=0.2, stderr="Successfully logged in\n", write=[(self.auth(), CODEX_AUTH)])
        self.assertEqual(self.login("codex"), "ok")
        (argv, kw), = self.logins()
        self.assertEqual(argv, [self.cli["codex"], "login"])
        self.assert_spawn_shape(argv, kw, "codex")
        self.assertEqual(self.events, [], "성공했는데 취소 요청이나 kill 을 했다")
        os.unlink(self.auth())
        for name, change, want in (("rc 0 인데 토큰 없음", {"rc": 0, "write": []}, "failed"),
                                   ("rc 0 인데 빈 auth.json", {"rc": 0, "write": [(self.auth(), "{}")]}, "failed"),
                                   ("거부", {"rc": 1, "write": [], "stderr": "Error logging in: denied\n"},
                                    "denied")):
            with self.subTest(case=name):
                self.spawned.clear()
                self.behave.update(change)
                self.assertEqual(self.login("codex"), want)
                if os.path.exists(self.auth()):
                    os.unlink(self.auth())
        self.assert_child_is_gone()
        self.assert_no_secrets_logged()

    def test_a_timeout_or_a_cancel_asks_codex_to_stop_then_ends_the_tree(self):
        """I5: 앱 타임아웃(300초)이나 취소 — `GET http://127.0.0.1:1455/cancel`(2초) **뒤에** 프로세스 트리를
        끝낸다. 결과는 "timeout" / "cancelled" 로 구분된다.
        Rivals: /cancel 없이 kill 만(계약은 먼저 codex 에게 끝내라고 한다); 취소를 시간 초과로 표시(사용자가 누른 것인데 오류 문구가 뜬다); 타임아웃
        없음(codex login 에는 내부 제한이 없다 — 영원히 "브라우저에서 로그인하세요")."""
        self.behave.update(delay=30.0, rc=0, write=[])
        for name, want in (("timeout", "timeout"), ("cancel", "cancelled")):
            with self.subTest(case=name):
                self.events.clear(); self.urlopens.clear(); self.spawned.clear()
                t0 = _real_time.time()
                if name == "timeout":
                    self.short_timeout("codex", 0.8)
                    got = self.login("codex")
                else:
                    self.short_timeout("codex", 20.0)
                    flag = threading.Event()
                    threading.Timer(0.5, flag.set).start()
                    got = self.login("codex", cancel=flag.is_set)
                self.assertEqual(got, want)
                self.assertLess(_real_time.time() - t0, 8.0)
                self.assertEqual(len(self.logins()), 1)
                self.assertIn("cancel-request", self.events, "codex 에 /cancel 을 보내지 않았다")
                self.assertIn("kill", self.events, "프로세스를 끝내지 않았다")
                self.assertLess(self.events.index("cancel-request"), self.events.index("kill"),
                                "/cancel 보다 kill 이 먼저다")
                url, timeout = [u for u in self.urlopens if "/cancel" in u[0]][0]
                self.assertEqual(url, "http://127.0.0.1:1455/cancel")
                self.assertTrue(isinstance(timeout, (int, float)) and 0 < timeout <= 2)
                self.assert_child_is_gone()


class GeminiLoginTests(LoginCase):

    def marker(self, mdat):
        with open(self.kc, "w", encoding="utf-8") as f:
            json.dump({"mdat": mdat}, f)

    def setUp(self):
        super().setUp()
        self.windows = []
        self._window_patch = mock.patch.object(claude_pet, "start_gemini_login", self._window)
        self._patch(self._window_patch)

    def _window(self, *a, **k):
        self.windows.append((a, k))

    def hint_after(self, seconds):
        self._patch(mock.patch.object(claude_pet, "GEMINI_LOGIN_HINT_SEC", seconds, create=True))

    def later(self, seconds, mdat):
        timer = threading.Timer(seconds, self.marker, args=(mdat,))
        timer.daemon = True
        timer.start()
        self.addCleanup(timer.cancel)

    def timed_login(self, **kw):
        t0 = _real_time.time()
        got = self.login("gemini", **kw)
        return got, _real_time.time() - t0

    def assert_app_only_watched(self):
        """앱은 창을 열고 지문만 본다 — agy 를 직접 띄우지 않고, 아무것도 죽이지 않고, 비밀값을 읽지 않는다."""
        self.assertEqual(len(self.windows), 1, "보이는 창을 정확히 한 번 열지 않았다")
        self.assertEqual(self.logins(), [], "앱이 agy 를 직접(숨은 프로세스로) 띄웠다")
        self.assertEqual(self.children, [])
        self.assertEqual(self.events, [], "앱이 프로세스를 끝내거나 취소 요청을 보냈다")
        self.assertEqual(self.urlopens, [])
        for argv, _kw in self.spawned:
            self.assertEqual(os.path.basename(argv[0]), "security", "지문 확인 말고 다른 것을 띄웠다: %r" % argv[0])
            self.assertFalse({"-w", "-g"} & set(argv), "키체인 비밀값을 읽었다")

    def test_login_opens_the_visible_window_and_succeeds_when_the_marker_changes(self):
        """I5(대표님 결정 2026-11-19): Gemini [로그인] = **보이는 창**(`start_gemini_login`)을 열고, 지문(키체인
        mdat)이 **바뀌면** 바로 "ok". 앱은 agy 를 직접 띄우지 않고, 창을 죽이지 않고, 코드를 다루지 않는다.
        지문이 이미 있어도(agy 는 로그아웃해도 항목을 남긴다) 바뀌기 전에는 성공이 아니다.
        Rivals: 파이프 90초 실행기(코드를 붙여 넣을 곳이 없다); 지문이 "있으면" 성공(누르자마자 연결됨);
        창을 안 엶; 지문이 바뀐 뒤에도 끝까지 기다림."""
        for name, before in (("처음 로그인(지문 없음)", None), ("다시 로그인(옛 지문 있음)", "20261101000000Z")):
            with self.subTest(case=name):
                self.windows.clear(); self.spawned.clear()
                if before is None:
                    if os.path.exists(self.kc):
                        os.unlink(self.kc)
                else:
                    self.marker(before)
                self.later(0.7, "20261119010203Z")
                got, took = self.timed_login()
                self.assertEqual(got, "ok")
                self.assertGreaterEqual(took, 0.6, "지문이 바뀌기 전에 성공이라고 했다")
                self.assertLess(took, 6.0, "지문이 바뀌었는데 5초 넘게 몰랐다")
                self.assert_app_only_watched()
        self.assert_no_secrets_logged()

    def test_the_wait_ends_only_on_a_cancel_or_the_five_minute_hint_and_nothing_is_killed(self):
        """I5: 앱의 대기는 지문 변화 또는 사용자의 [취소]까지. 5분(`GEMINI_LOGIN_HINT_SEC`)이 지나면 "timeout"
        ("다시 시도" 안내 — 표시용)을 돌려줄 뿐, 창도 프로세스도 건드리지 않는다. 취소는 오류가 아니다.
        Rivals: 90초에 끊음; 시간이 지나면 창을 닫음/agy 를 죽임; 취소를 눌러도 기다림; 취소를 실패로."""
        self.marker("20261101000000Z")
        flag = threading.Event()
        timer = threading.Timer(0.5, flag.set)
        timer.daemon = True
        timer.start()
        got, took = self.timed_login(cancel=flag.is_set)
        self.assertEqual(got, "cancelled")
        self.assertLess(took, 6.0, "취소를 눌러도 기다렸다")
        self.assert_app_only_watched()
        # 실제 값 300초로는 1.5초 안에 끝나지 않는다(옛 90초 실행기와는 무관하게, 짧은 시간 제한이 없다).
        self.windows.clear(); self.spawned.clear()
        box = []
        th = threading.Thread(target=lambda: box.append(self.login("gemini", cancel=flag.is_set)), daemon=True)
        flag.clear()
        th.start()
        th.join(1.5)
        self.assertTrue(th.is_alive(), "지문도 안 바뀌고 취소도 안 했는데 끝났다: %r" % box)
        flag.set()
        th.join(8)
        self.assertEqual(box, ["cancelled"])
        self.windows.clear(); self.spawned.clear()
        self.hint_after(0.8)
        got, took = self.timed_login()
        self.assertEqual(got, "timeout")
        self.assertGreaterEqual(took, 0.7)
        self.assert_app_only_watched()

    def test_the_terminal_window_prints_the_three_steps_before_agy_in_the_app_language(self):
        """I5(대표님 보완): 띄우는 터미널 창 **맨 위에 안내 세 줄**을 먼저 찍고 agy 를 실행한다 — 앱 언어로
        (4개 로케일): ① 브라우저에서 계정을 고르고 로그인 ② 나온 코드를 복사 ③ 이 창에 붙여 넣고 Enter.
        `agy` 만 연다(`-p`·`/usage` 없음).
        Rivals: 안내 없이 agy 만 띄움(코드를 어디에 넣는지 모른다); 안내를 agy 뒤에 찍음(agy 가 끝나야 보인다);
        영어로만; 한 줄만."""
        self._window_patch.stop()
        login = _require("start_gemini_login")
        for lang in ("en", "ko", "ja", "es"):
            with self.subTest(lang=lang):
                steps = [claude_pet.TR[lang].get("term_gemini_step%d" % i) for i in (1, 2, 3)]
                self.assertTrue(all(isinstance(x, str) and x.strip() for x in steps), "안내 문구가 없다")
                seen = []
                with mock.patch.dict(claude_pet.L, {"lang": lang}), \
                        mock.patch.object(claude_pet, "_run_in_terminal", side_effect=seen.append):
                    self.spawned.clear()
                    login()
                self.assertEqual(len(seen), 1, "Terminal 창을 한 번 열지 않았다")
                self.assertEqual(self.logins(), [])
                script = str(seen[0])
                at = [script.find(x) for x in steps]
                self.assertNotIn(-1, at, "터미널 창에 안내 세 줄이 다 없다")
                self.assertEqual(at, sorted(at), "안내 순서가 ①②③ 이 아니다")
                lines = script.splitlines()
                agy_line = [i for i, ln in enumerate(lines)
                            if ln.strip().strip("\"'") == "agy" or ln.strip().strip("\"'").endswith("/agy")]
                self.assertTrue(agy_line, "`agy` 만 실행하는 줄이 없다")
                step_lines = [i for i, ln in enumerate(lines) if any(x in ln for x in steps)]
                self.assertLess(max(step_lines), agy_line[0], "안내를 agy 보다 먼저 찍지 않았다")
                self.assertNotIn("/usage", script)
                self.assertNotIn("fake-open", script)

    def test_on_windows_the_same_steps_and_agy_open_in_a_new_console_window(self):
        """I5: Windows — 코어의 `start_gemini_login()` 이 **새 콘솔 창**(creationflags 에 CREATE_NEW_CONSOLE
        0x10, CREATE_NO_WINDOW 없음)에서 안내 세 줄을 먼저 찍고 `agy.exe` 를 실행한다. 가짜 rundll32 폴더를
        PATH 에 넣지 않는다(브라우저가 떠야 한다).
        Rivals: 숨은 창(CREATE_NO_WINDOW — 코드를 붙여 넣을 곳이 없다); 백그라운드 조회용 env 를 재사용."""
        self._window_patch.stop()
        login = _require("start_gemini_login")
        agy = os.path.join(self.home, ".local", "bin", "agy.exe")
        self.put(agy)
        opened = []

        def popen(argv, *a, **k):
            opened.append(([str(x) for x in argv] if not isinstance(argv, str) else [argv], dict(k)))
            return mock.Mock(pid=4242, returncode=None)
        with mock.patch.object(claude_pet.sys, "platform", "win32"), \
                mock.patch.object(claude_pet, "_find_agy_cli", lambda: agy), \
                mock.patch.dict(claude_pet.L, {"lang": "ko"}), \
                mock.patch.object(claude_pet, "_run_in_terminal",
                                  side_effect=AssertionError("Windows 에서 Terminal.app 을 열었다")), \
                mock.patch.object(claude_pet.subprocess, "Popen", popen):
            login()
        self.assertEqual(len(opened), 1, "새 콘솔 창을 한 번 열지 않았다")
        argv, kw = opened[0]
        flags = int(kw.get("creationflags") or 0)
        self.assertTrue(flags & 0x00000010, "CREATE_NEW_CONSOLE(0x10) 이 없다 — 보이는 창이 아니다")
        self.assertFalse(flags & 0x08000000, "CREATE_NO_WINDOW — 숨은 창이다")
        text = " ".join(argv)
        steps = [claude_pet.TR["ko"]["term_gemini_step%d" % i] for i in (1, 2, 3)]
        at = [text.find(x) for x in steps] + [text.find(agy)]
        self.assertNotIn(-1, at, "안내 세 줄과 agy.exe 가 명령에 다 없다")
        self.assertEqual(at, sorted(at), "안내 세 줄 → agy.exe 순서가 아니다")
        self.assertNotIn("/usage", text)
        env = kw.get("env")
        if env is not None:
            self.assertNotIn("fake-open", str(env.get("PATH", "")))
            self.assertFalse([k2 for k2 in ("SSH_TTY", "SSH_CLIENT", "SSH_CONNECTION") if k2 in env])

    def test_without_a_cli_nothing_is_started(self):
        for p in PROVIDERS:
            os.unlink(self.cli[p])
            with self.subTest(provider=p):
                self.assertEqual(self.login(p), "not_installed")
        self.assertEqual(self.logins(), [])


class ClaudeLoginTests(LoginCase):

    def test_claude_goes_through_the_existing_detached_job_for_300_seconds(self):
        """I5: Claude 는 기존 경로(`_run_refresh_job` + `login_spawn_argv`) — CLI 를 우리 자식으로 띄우지 않는다
        (CLAUDE.md "Token auto-recovery runs the CLI detached"). 상한 300초. 성공은 그 뒤 토큰이 있을 때.
        Rivals: Popen 으로 직접 띄움(보호 폴더 접근이 ClaudePet 의 것으로 잡힌다); job 이 끝났다는 것만으로
        성공; 이미 토큰이 있는데 다시 띄움."""
        jobs = []
        token = {"on": False}

        def job(argv, label, stem, timeout):
            jobs.append((list(argv), label, timeout))
            token["on"] = token["after"]
            return token["out"]
        self._patch(mock.patch.object(claude_pet, "_run_refresh_job", job))
        self._patch(mock.patch.object(claude_pet, "claude_token_present", lambda: token["on"]))
        for name, after, out, want_ok in (("토큰이 생김", True, "done", True), ("토큰이 안 생김", False, "done", False),
                                          ("띄우지 못함", False, None, False)):
            with self.subTest(case=name):
                jobs.clear()
                token.update(on=False, after=after, out=out)
                got = self.login("claude")
                self.assertEqual(got == "ok", want_ok, "결과 %r" % (got,))
                self.assertIn(got, ("ok", "denied", "failed", "timeout"))
                (argv, label, timeout), = jobs
                self.assertEqual(argv, claude_pet.login_spawn_argv(self.cli["claude"]))
                self.assertEqual(label, claude_pet.LOGIN_JOB_LABEL)
                self.assertEqual(timeout, 300)
        jobs.clear()
        token.update(on=True)
        self.assertEqual(self.login("claude"), "already")
        self.assertEqual(jobs, [])
        self.assertEqual(self.logins(), [], "claude 를 직접 자식으로 띄웠다")


# ═════════════════════════════ I1 — 설정 "AI 연결" ═════════════════════════════

KO = {"ai_not_installed": "설치 안 됨", "ai_need_login": "로그인 필요", "ai_connected": "연결됨",
      "ai_verifying": "확인 중", "ai_login_browser": "브라우저에서 로그인하세요",
      "ai_btn_install": "설치", "ai_btn_login": "로그인", "ai_btn_cancel": "취소", "ai_btn_retry": "다시 시도",
      "ai_sec": "AI 연결", "ai_login_paste": "열린 창에 붙여 넣으세요"}
GEMINI_STEPS_KO = (("①", "브라우저", "로그인"), ("②", "코드", "복사"), ("③", "붙여", "Enter"))
FAIL_REASONS = ("unsupported", "manifest", "network", "hash", "archive", "signature", "locked",
                "denied", "timeout", "failed")


class AiConnectRowTests(unittest.TestCase):

    def row(self, *a, **k):
        return _require("ai_connect_row")(*a, **k)

    def test_the_resting_states_and_their_one_button(self):
        """I1: `설치 안 됨 [설치]` → `로그인 필요 [로그인]` → `연결됨`(버튼 없음). 줄마다 한 줄 안내.
        Rivals: 연결됐는데 [로그인] 을 남김(Codex 에서 누르면 기존 토큰이 지워진다); 설치 안 됐는데 [로그인]."""
        for p in PROVIDERS:
            with self.subTest(provider=p):
                r = self.row(p, False, False)
                self.assertEqual((r["status"], r["button"]), ("ai_not_installed", "ai_btn_install"))
                r = self.row(p, True, False)
                self.assertEqual((r["status"], r["button"]), ("ai_need_login", "ai_btn_login"))
                for installed in (True, False):
                    r = self.row(p, installed, True)
                    self.assertEqual((r["status"], r["button"]), ("ai_connected", None))
                self.assertEqual(r["hint"], "ai_hint_" + p)
                self.assertEqual(self.row(p, False, False, job={"phase": None})["status"], "ai_not_installed")

    def test_a_running_job_shows_its_phase_and_a_cancel_and_a_failure_offers_a_retry(self):
        """I1: 진행 중 `받는 중 n%` / `확인 중` / `브라우저에서 로그인하세요` + [취소]. 실패면 짧은 이유 + [다시 시도].
        Rivals: 진행 중에 [설치] 를 그대로 둠(두 번 누르면 두 번 받는다); 실패를 "설치 안 됨"으로 되돌림(왜 안
        됐는지 모른다); 이유마다 같은 문구."""
        for p in PROVIDERS:
            r = self.row(p, False, False, job={"phase": "download", "pct": 37})
            self.assertEqual((r["status"], r["button"], r["pct"]), ("ai_downloading", "ai_btn_cancel", 37))
            r = self.row(p, False, False, job={"phase": "download", "pct": None})
            self.assertEqual((r["status"], r["button"]), ("ai_downloading", "ai_btn_cancel"))
            r = self.row(p, False, False, job={"phase": "verify"})
            self.assertEqual((r["status"], r["button"]), ("ai_verifying", "ai_btn_cancel"))
            r = self.row(p, True, False, job={"phase": "login"})
            if p == "gemini":
                # 대표님 결정 2026-11-19: Gemini 는 열린 창에 코드를 붙여 넣어야 한다 — 그 말을 그 줄에 보인다.
                self.assertEqual((r["status"], r["button"], r["hint"]),
                                 ("ai_login_paste", "ai_btn_cancel", "ai_gemini_guide"))
            else:
                self.assertEqual((r["status"], r["button"], r["hint"]),
                                 ("ai_login_browser", "ai_btn_cancel", "ai_hint_" + p))
            seen = set()
            for reason in FAIL_REASONS:
                r = self.row(p, reason in ("denied", "timeout", "failed"), False,
                             job={"phase": "failed", "reason": reason})
                self.assertEqual(r["button"], "ai_btn_retry")
                self.assertEqual(r["status"], "ai_fail_" + reason)
                seen.add(r["status"])
            self.assertEqual(len(seen), len(FAIL_REASONS))
            # 연결된 뒤에는 지난 실패를 보이지 않는다.
            self.assertEqual(self.row(p, True, True, job={"phase": "failed", "reason": "timeout"})["status"],
                             "ai_connected")

    def test_the_copy_exists_in_all_four_languages(self):
        """I1: 4개 로케일. 한국어 문구는 계약 그대로. `받는 중` 에는 {pct} 자리가 있다. 안내 줄: Claude =
        claude.ai 와 같은 한도, ChatGPT = Codex 사용량만, Gemini = Antigravity 한도만 — gemini.google.com 채팅과 별개."""
        keys = (list(KO) + ["ai_downloading", "ai_hint_claude", "ai_hint_codex", "ai_hint_gemini",
                            "ai_gemini_guide", "term_gemini_step1", "term_gemini_step2", "term_gemini_step3"]
                + ["ai_fail_" + r for r in FAIL_REASONS])
        for lang in ("en", "ko", "ja", "es"):
            table = claude_pet.TR[lang]
            missing = [k for k in keys if not (isinstance(table.get(k), str) and table[k].strip())]
            with self.subTest(lang=lang):
                self.assertEqual(missing, [], "문구가 없다")
                self.assertIn("{pct}", table["ai_downloading"])
                self.assertIn("claude.ai", table["ai_hint_claude"])
                self.assertIn("Codex", table["ai_hint_codex"])
                self.assertIn("Antigravity", table["ai_hint_gemini"])
                self.assertIn("gemini.google.com", table["ai_hint_gemini"])
                # Gemini 로그인 안내: 터미널 맨 위 세 줄은 ①②③ 으로 시작하고 셋째 줄에 Enter 가 있다.
                self.assertEqual([table["term_gemini_step%d" % i][:1] for i in (1, 2, 3)], ["①", "②", "③"])
                self.assertIn("Enter", table["term_gemini_step3"])
                self.assertIn("Enter", table["ai_gemini_guide"])
                self.assertEqual(len({table["ai_fail_" + r] for r in FAIL_REASONS}), len(FAIL_REASONS),
                                 "실패 이유의 문구가 서로 같다")
        ko = claude_pet.TR["ko"]
        self.assertEqual({k: ko.get(k) for k in KO}, KO)
        self.assertTrue(str(ko.get("ai_downloading", "")).startswith("받는 중"))
        for i, words in enumerate(GEMINI_STEPS_KO, 1):
            self.assertEqual([w for w in words if w not in ko["term_gemini_step%d" % i]], [])
        self.assertEqual([w for w in ("브라우저", "코드", "붙여", "Enter") if w not in ko["ai_gemini_guide"]], [])
        for lang in ("en", "ja", "es"):
            same = [k for k in list(KO) + ["ai_gemini_guide", "term_gemini_step1", "term_gemini_step2",
                                           "term_gemini_step3"] if claude_pet.TR[lang].get(k) == ko.get(k)]
            self.assertEqual(same, [], "%s 로케일에 한국어 문구가 그대로다" % lang)


class RunAiConnectTests(unittest.TestCase):

    def setUp(self):
        self.log = []
        self.installed = False
        self.logged = False
        self.install_result = (True, "/synthetic/bin/x")
        self.login_result = "ok"
        self.job = {"phase": None}
        self.phases = []
        self._patch(mock.patch.object(claude_pet, "find_cli",
                                      lambda p: "/synthetic/bin/x" if self.installed else None, create=True))
        self._patch(mock.patch.object(claude_pet, "cli_logged_in", lambda p: self.logged, create=True))
        self._patch(mock.patch.object(claude_pet, "install_cli", self._install, create=True))
        self._patch(mock.patch.object(claude_pet, "run_cli_login", self._login, create=True))
        self._patch(mock.patch.object(claude_pet, "_dbg", lambda *a, **k: None))
        for name in ("_oauth_cache", "_codex_cache", "_gemini_cache"):
            d = getattr(claude_pet, name)
            snap = dict(d)
            self.addCleanup(lambda d=d, snap=snap: (d.clear(), d.update(snap)))
            d["t"] = 12345.0
        claude_pet._gemini_cache.update(click=False, click_check=False)

    def _patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def _install(self, provider, *a, **k):
        self.log.append(("install", provider, self.job.get("phase")))
        progress = k.get("progress")
        if progress is not None:
            progress(50, 200)
            self.phases.append((self.job.get("phase"), self.job.get("pct")))
            progress(200, 200)
            self.phases.append((self.job.get("phase"), self.job.get("pct")))
        if self.install_result[0]:
            self.installed = True
        return self.install_result

    def _login(self, provider, *a, **k):
        self.log.append(("login", provider, self.job.get("phase")))
        if self.login_result == "ok":
            self.logged = True
        return self.login_result

    def connect(self, provider="codex", **kw):
        try:
            return _require("run_ai_connect")(provider, self.job, **kw)
        except Exception as e:  # noqa: BLE001
            self.fail("run_ai_connect 가 예외를 냈다: %s" % type(e).__name__)

    def test_install_runs_straight_on_into_the_login_window(self):
        """I1: [설치] 는 설치가 끝나면 **이어서 로그인 창까지** 띄운다. 받는 동안 job 은 "download" 와 퍼센트,
        로그인 동안 "login", 끝나면 비워진다. 성공하면 바로 사용량을 새로 받게 한다.
        Rivals: 설치만 하고 멈춤(사용자가 [로그인] 을 또 눌러야 한다); 진행률을 안 올림; 성공 뒤 다음 주기
        (최대 5분)까지 숫자가 안 뜸."""
        for p in PROVIDERS:
            with self.subTest(provider=p):
                self.log.clear(); self.phases.clear()
                self.installed = self.logged = False
                self.job = {"phase": None}
                self.assertEqual(self.connect(p), "ok")
                self.assertEqual([(w, pp) for w, pp, _ph in self.log], [("install", p), ("login", p)])
                self.assertEqual(self.log[0][2], "download")
                self.assertEqual(self.log[1][2], "login")
                self.assertEqual(self.phases[0], ("download", 25))
                self.assertIn(self.phases[1][0], ("download", "verify"))
                self.assertIsNone(self.job.get("phase"), "끝났는데 job 이 진행 중으로 남았다")
        self.assertEqual(claude_pet._oauth_cache["t"], 0.0, "Claude 사용량을 바로 다시 받게 하지 않았다")
        self.assertEqual(claude_pet._codex_cache["t"], 0.0)
        self.assertIs(claude_pet._gemini_cache.get("click"), True)

    def test_what_is_already_there_is_not_done_again(self):
        """I2: 설치돼 있으면 받지 않고 로그인만, 로그인돼 있으면 아무것도 하지 않는다."""
        self.installed = True
        self.assertEqual(self.connect(), "ok")
        self.assertEqual([w for w, _p, _ph in self.log], ["login"])
        self.log.clear()
        self.installed = self.logged = True
        self.assertIn(self.connect(), ("ok", "already"))
        self.assertEqual(self.log, [])
        self.assertIsNone(self.job.get("phase"))

    def test_a_failure_stops_there_and_says_why_and_a_cancel_is_not_a_failure(self):
        """I1: 설치가 실패하면 로그인으로 가지 않고 job 이 "failed" + 이유. 로그인이 거부·시간 초과면 그 이유.
        사용자가 취소하면 실패 문구 없이 원래 상태로 돌아간다. 로그인은 **자동으로 다시 띄우지 않는다**.
        Rivals: 설치가 실패했는데 로그인 창을 띄움; 취소를 "실패"로 보임; 시간 초과 뒤 스스로 다시 시도."""
        for kind in ("hash", "signature", "network", "archive", "manifest", "unsupported"):
            with self.subTest(install=kind):
                self.log.clear()
                self.installed = self.logged = False
                self.job = {"phase": None}
                self.install_result = (False, kind)
                self.assertEqual(self.connect(), kind)
                self.assertEqual([w for w, _p, _ph in self.log], ["install"])
                self.assertEqual((self.job.get("phase"), self.job.get("reason")), ("failed", kind))
        self.install_result = (True, "/synthetic/bin/x")
        for result in ("denied", "timeout", "failed"):
            with self.subTest(login=result):
                self.log.clear()
                self.installed, self.logged = True, False
                self.job = {"phase": None}
                self.login_result = result
                self.assertEqual(self.connect(), result)
                self.assertEqual([w for w, _p, _ph in self.log], ["login"], "로그인을 다시 띄웠다")
                self.assertEqual((self.job.get("phase"), self.job.get("reason")), ("failed", result))
        for where in ("install", "login"):
            with self.subTest(cancelled=where):
                self.log.clear()
                self.installed, self.logged = where == "login", False
                self.job = {"phase": None}
                self.install_result = (False, "cancelled")
                self.login_result = "cancelled"
                self.assertEqual(self.connect(), "cancelled")
                self.assertIsNone(self.job.get("phase"), "취소를 실패로 남겼다")
                self.assertEqual(len(self.log), 1)

    def test_nothing_on_the_refresh_path_can_start_an_install_or_a_login(self):
        """I4·I5: 받기와 로그인은 **사용자가 버튼을 눌렀을 때만**. 30초 새로고침·토큰 복구·Gemini 조회 경로에서
        install_cli·run_cli_login·run_ai_connect 에 닿는 길이 없다.
        Rival: 로그인 안 됨을 보면 스스로 로그인 창을 띄움("왜 로그인을 재시도해")."""
        tree = ast.parse(CORE.read_text(encoding="utf-8"))
        funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

        def reach(name):
            seen, frontier = set(), [name]
            while frontier:
                fn = frontier.pop()
                if fn in seen or fn not in funcs:
                    continue
                seen.add(fn)
                frontier += [c.func.id for c in ast.walk(funcs[fn])
                             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
            return seen
        for name in ("run_ai_connect", "install_cli", "run_cli_login"):
            self.assertIn(name, funcs, "claude_pet.%s 가 없다" % name)
        for start in ("fetch_gemini_usage", "start_gemini_refresh", "fetch_codex_usage", "fetch_exact_usage",
                      "recovery_tick", "run_token_refresh", "compute_usage", "learn_server_limits",
                      "compute_gemini_onboard_state", "compute_codex_onboard_state", "compute_onboard_state"):
            with self.subTest(start=start):
                self.assertIn(start, funcs)
                hit = reach(start) & {"run_ai_connect", "install_cli", "run_cli_login", "cli_stage_download"}
                self.assertEqual(hit, set(), "%s 에서 %s 에 닿는다" % (start, sorted(hit)))


# ═════════════════════════════ I1·I7 — 앱의 배선 ═════════════════════════════


def _run_gui():
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_gui")


def _calls(node):
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            out.add(c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", None))
    return out


class MacWiringTests(unittest.TestCase):

    TERMINAL = {"start_claude_install", "start_claude_login", "start_codex_install", "start_codex_login",
                "start_gemini_login", "_run_in_terminal"}

    def test_the_settings_panel_has_the_ai_connection_section(self):
        """I1: 설정 창에 "AI 연결" 구역 — 줄은 `ai_connect_row` 가 정하고 버튼은 `run_ai_connect` 로 간다.
        높이는 656 을 넘지 않는다(CLAUDE.md Danger zone — 다른 게이트가 본다)."""
        gui = _run_gui()
        settings = [n for n in ast.walk(gui) if isinstance(n, ast.FunctionDef) and n.name == "open_settings"]
        self.assertEqual(len(settings), 1)
        keys = {c.args[0].value for c in ast.walk(settings[0]) if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name) and c.func.id == "t" and c.args
                and isinstance(c.args[0], ast.Constant)}
        self.assertIn("ai_sec", keys)
        self.assertIn("ai_connect_row", _calls(gui))
        self.assertTrue({"run_ai_connect", "start_ai_connect"} & _calls(gui),
                        "run_gui 가 설치·로그인 흐름을 부르지 않는다")

    def test_the_menu_and_the_pill_use_this_flow_instead_of_a_terminal(self):
        """I1: 필·우클릭의 기존 "설치/로그인" 안내도 터미널 대신 이 흐름을 쓴다 — 다섯 메뉴 핸들러와 필 클릭
        (mouseUp_)이 Terminal 을 여는 함수를 부르지 않고 run_ai_connect 로 간다.
        Rival: 설정 창만 새 흐름이고 메뉴는 여전히 Terminal 을 엶."""
        gui = _run_gui()
        methods = {n.name: n for n in ast.walk(gui) if isinstance(n, ast.FunctionDef)}
        for name in ("installClaude_", "loginClaude_", "installCodex_", "loginCodex_", "loginGemini_",
                     "_summary_click_work"):
            with self.subTest(handler=name):
                self.assertIn(name, methods)
                reach, frontier = set(), [methods[name]]
                while frontier:
                    for called in _calls(frontier.pop()):
                        if called in methods and called not in reach:
                            frontier.append(methods[called])
                        reach.add(called)
                self.assertEqual(reach & self.TERMINAL, set(), "%s 가 아직 Terminal 을 연다" % name)
                self.assertTrue(reach & {"run_ai_connect", "start_ai_connect"},
                                "%s 가 설치·로그인 흐름으로 가지 않는다" % name)

    def test_the_optional_starter_runs_the_job_off_the_main_thread(self):
        """I4: 받기·로그인은 메인 스레드 밖. 코어에 `start_ai_connect` 를 두면(이름은 선택) 그것은
        `threading.Thread` 의 target 안에서 run_ai_connect 를 부른다 — 직접 기다리지 않는다."""
        tree = ast.parse(CORE.read_text(encoding="utf-8"))
        starter = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "start_ai_connect"]
        if not starter:
            self.assertIn("Thread", _calls(_run_gui()))
            return
        inner = [n for n in ast.walk(starter[0]) if isinstance(n, (ast.FunctionDef, ast.Lambda))
                 and n is not starter[0] and "run_ai_connect" in _calls(n)]
        self.assertTrue(inner, "start_ai_connect 가 run_ai_connect 를 스레드 밖에서 직접 부른다")
        self.assertIn("Thread", _calls(starter[0]))
        direct = [c for c in ast.walk(starter[0]) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                  and c.func.id == "run_ai_connect"
                  and not any(c in list(ast.walk(i)) for i in inner)]
        self.assertEqual(direct, [])


class UninstallScopeTests(CliCase):

    def test_complete_removal_takes_the_app_bin_and_leaves_the_users_clis_and_logins(self):
        """I7: "완전 삭제"는 앱 전용 bin·staging 까지 지운다(그 폴더나 그 위의 앱 폴더가 삭제 목록에 있다).
        사용자가 깐 CLI 와 각 CLI 의 로그인 정보(~/.claude, ~/.codex, ~/.gemini, ~/.local)는 목록에 없다.
        Rivals: 앱 bin 을 남김(지웠는데 수백 MB 가 남는다); ~/.codex 를 같이 지움(로그아웃된다)."""
        _require("app_cli_bin_dir")
        self.put(self.final("codex"))
        self.put(os.path.join(self.bin_dir(), "staging", "left"))
        keep = [self.put(os.path.join(self.home, ".local", "bin", "codex")),
                self.put(os.path.join(self.home, ".codex", "auth.json"), CODEX_AUTH.encode()),
                self.put(os.path.join(self.home, ".claude", ".credentials.json"), b"{}"),
                self.put(os.path.join(self.home, ".gemini", "antigravity-cli", "antigravity-oauth-token"), b"{}")]
        targets = [os.path.realpath(p) for p in claude_pet.uninstall_targets()]
        bin_dir = os.path.realpath(self.bin_dir())
        self.assertTrue(any(bin_dir == tgt or bin_dir.startswith(tgt + os.sep) for tgt in targets),
                        "완전 삭제 목록이 앱 전용 bin 을 덮지 않는다")
        for p in keep:
            real = os.path.realpath(p)
            self.assertFalse(any(real == tgt or real.startswith(tgt + os.sep) for tgt in targets),
                             "완전 삭제가 사용자의 것을 지운다: %s" % os.path.relpath(p, self.home))
        self.assertFalse(any(tgt == os.path.realpath(self.home) or
                             tgt == os.path.realpath(os.path.join(self.home, "Library", "Application Support"))
                             for tgt in targets), "삭제 목록이 너무 넓다")


if __name__ == "__main__":
    unittest.main()
