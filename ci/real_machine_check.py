#!/usr/bin/env python3
"""실기기 잡 (TOK-62) — 이 기기에 **실제로 깔린 CLI 와 실제 로그인 상태**로 앱의 판정을 확인한다.

    python3 ci/real_machine_check.py        (저장소 루트에서, self-hosted 러너가 돌린다)

기준(대표님, 2026-11-19): 로그인돼 있으면 로그인을 묻지 않고 **바로 사용량 값이 뜬다**.
제공자(Claude Code · Codex · Gemini)마다:

  · CLI 가 없거나 로그인 정보가 없으면 — 그 사실만 적고 넘어간다(이 기기의 상태이지 결함이 아니다).
    단, 그때 설정 줄은 [설치]/[로그인]이어야 한다.
  · 이 잡은 막는 게이트다. 세 제공자 중 **하나도 확인하지 못했으면 실패**다 — 아무것도 로그인돼 있지 않은
    기기는 아무것도 검증하지 못한 것이고, 그것을 초록이라고 하지 않는다.
  · 로그인 정보가 있으면 — 사용량을 한 번 읽는다. 값(행)이 나와야 한다. 안 나오면 실패이고 오류의
    종류(http:<코드>·net·agy_failed·timeout·login …)를 적는다. 설정 줄은 [로그인]·[설치]를 내밀면 안 되고,
    흐름을 시작해도(run_ai_connect) 로그인 창·프로세스·설치가 뜨면 안 된다.

브라우저·터미널·로그인 프로세스를 열 수 있는 자리는 전부 기록만 하는 대역으로 바꿔 둔다 — 이 스크립트는
어떤 창도 열지 않는다. 읽기에 쓰는 CLI(`agy -p /usage`)와 서버 요청은 진짜다. 로그에는 제공자 이름·참/거짓·
행 개수·오류 종류만 찍는다 — 토큰·경로·계정·사용량 값은 찍지 않는다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import claude_pet as cp
except ImportError:
    from windows.win_core import import_core
    cp = import_core()

PROVIDERS = ("claude", "codex", "gemini")


def signin_present(provider):
    """로그인 정보가 있는가 — 창이 뜰 수 없는 확인만. 모르면 None."""
    if provider == "claude":
        return bool(cp.claude_token_present())
    if provider == "codex":
        return bool(cp.read_codex_token(cp.codex_auth_path()))
    marker = cp._gemini_login_marker(cp._gemini_edge_rules())
    return None if marker is None else bool(cp._gemini_marker_logged_in(marker))


def read_usage(provider):
    """사용량을 한 번 읽는다 → (행 개수, 오류 종류 또는 None, 로그인을 요구받았는가)."""
    if provider == "claude":
        rows, status = cp.fetch_exact_usage(), cp.OAUTH_STATUS
    elif provider == "codex":
        rows, status = cp.fetch_codex_usage(), cp.CODEX_STATUS
    else:
        rows, status = cp.fetch_gemini_usage(), cp.GEMINI_STATUS
    return len(rows or ()), status.get("last_error"), bool(status.get("auth_error"))


def why_no_rows(provider):
    """값이 없을 때 그 까닭을 앱의 상태에서 읽어 한 줄로 — error=None 인 채 값이 없는 칸을 남기지 않는다.
    참/거짓과 종류만 적는다."""
    if provider == "claude":
        if not cp._oauth_token_cache.get("tok"):
            return "no token could be read (file: %s, keychain locked: %s) — no request was sent" % (
                bool(cp._token_from_file()), cp.keychain_locked())
        return "request sent; last error: %s" % cp.OAUTH_STATUS.get("last_error")
    if provider == "codex":
        if not cp.read_codex_token(cp.codex_auth_path()):
            return "no sign-in data — no request was sent"
        if cp._codex_cache.get("ok_t") is not None:
            return "the server answered, but with no usable usage window"
        return "last error: %s" % cp.CODEX_STATUS.get("last_error")
    c = cp._gemini_cache
    if c.get("login") is None:
        return "sign-in state unknown — agy was not run (keychain locked: %s)" % cp.keychain_locked()
    if c.get("login") is False:
        return "no sign-in marker — agy was not run"
    return "agy was run; last error: %s" % cp.GEMINI_STATUS.get("last_error")


def main():
    # 러너의 콘솔 인코딩(한국어 Windows 는 cp949)이 못 쓰는 글자로 죽지 않게 — 실제로 한 번 죽었다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    # Windows 의 자격 증명 프로브는 "지금 도는 진입 스크립트"를 숨은 인자로 다시 띄운다 — 그게 이 파일이다.
    if cp.GEMINI_CRED_PROBE_FLAG in sys.argv[1:]:
        return cp.gemini_cred_probe_main()
    cp.apply_config(cp.load_config())
    cp.RUNTIME["mode"] = "sub"

    opened = []

    def tripwire(name, result):
        def fake(*_a, **_kw):
            opened.append(name)
            return result
        return fake

    cp.start_gemini_login = tripwire("gemini login window", None)
    cp._run_in_terminal = tripwire("terminal window", None)
    cp._run_refresh_job = tripwire("claude login job", None)
    cp._run_codex_login = tripwire("codex login process", "failed")
    cp._run_gemini_login = tripwire("gemini login wait", "failed")
    cp.install_cli = tripwire("cli download", (False, "network"))

    failures = []
    verified = 0
    # 잠긴 키체인에서는 Claude·Gemini 의 로그인 정보를 읽을 수 없다 — 앱도 그때는 묻지 않고 기다린다.
    # 러너가 로그인한 화면 세션 밖에서(SSH 등) 돌면 이렇게 된다. 검증할 수 없는 것이므로 분명히 실패시킨다.
    locked = cp.keychain_locked() if sys.platform == "darwin" else False
    if sys.platform == "darwin":
        print("login keychain locked: %s" % locked)
    print("python %d.%d, PATH entries: %d, HOME set: %s"
          % (sys.version_info[0], sys.version_info[1], len(os.environ.get("PATH", "").split(os.pathsep)),
             bool(os.environ.get("HOME") or os.environ.get("USERPROFILE"))))
    if locked is True:
        failures.append("the login keychain is locked in the runner's session — Claude Code and Gemini cannot be "
                        "verified. Remove SessionCreate from the runner's LaunchAgent (ci/SELF_HOSTED_RUNNERS.md)")
    for p in PROVIDERS:
        if locked is True and p in ("claude", "gemini"):
            print("%-7s not checked — keychain locked" % p)
            continue
        installed = bool(cp.find_cli(p))
        # 앱의 새로고침과 같은 순서: 먼저 읽는다. 키체인에 로그인 정보를 둔 Claude 사용자는 읽고 난 뒤에야
        # "로그인 정보 있음"이 된다(claude_token_present 는 창이 뜰 수 있는 키체인 API 를 타지 않는다).
        count, err, asked = read_usage(p) if installed else (0, None, False)
        if installed and count == 0:
            print("%-7s no rows: %s" % (p, why_no_rows(p)))
        present = signin_present(p) if installed else False
        if not installed or present is not True:
            row = cp.ai_connect_row(p, installed, cp.cli_logged_in(p), cp.new_ai_job())
            print("%-7s installed=%s sign-in=%s — skipped (row: %s / %s)"
                  % (p, installed, {True: "yes", False: "no", None: "unknown"}[present], row["status"], row["button"]))
            if present is False:
                want = "ai_btn_login" if installed else "ai_btn_install"
                if row["button"] != want:
                    failures.append("%s: no sign-in on this machine, but the row offers %s" % (p, row["button"]))
            continue
        row = cp.ai_connect_row(p, installed, cp.cli_logged_in(p), cp.new_ai_job())
        print("%-7s installed=True sign-in=yes rows=%d error=%s login-demanded=%s row: %s / %s"
              % (p, count, err, asked, row["status"], row["button"]))
        verified += 1
        if asked:
            # 로그인 정보는 남아 있지만 서버·CLI 가 로그인을 요구했다(만료·로그아웃) — 이때는 [로그인]이 맞다.
            if row["button"] != "ai_btn_login":
                failures.append("%s: sign-in was rejected, but the row does not offer [Sign in]" % p)
            continue
        if count == 0 and err is None and p == "codex":
            # 서버가 정상으로 답했는데 쓸 사용량 창이 없다(한도 창이 없는 계정) — 보여 줄 값이 없는 것이지
            # 읽지 못한 것이 아니다. 실패로도, 확인한 것으로도 세지 않는다.
            print("codex   the server answered without usage windows — nothing to show, not counted")
            verified -= 1
        elif count == 0:
            failures.append("%s: signed in, but no usage value was read — %s" % (p, why_no_rows(p)))
        if row["button"] in ("ai_btn_login", "ai_btn_install") or row["status"] in ("ai_need_login", "ai_not_installed"):
            failures.append("%s: signed in, but the row says %s / %s" % (p, row["status"], row["button"]))
        before = len(opened)
        cp.run_ai_connect(p, cp.new_ai_job())
        if len(opened) != before:
            failures.append("%s: signed in, but starting the flow opened: %s" % (p, ", ".join(opened[before:])))

    if not verified:
        failures.append("no provider is signed in on this machine — nothing was verified")
    print("providers verified: %d of %d" % (verified, len(PROVIDERS)))
    for f in failures:
        print("FAIL ", f)
    print("real machine:", "FAILED (%d)" % len(failures) if failures else "OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
