#!/usr/bin/env python3
"""배포 번들이 CLI 에게 넘기는 환경을 검사한다 (TOK-62). 소스가 아니라 **빌드한 산출물**에게 묻는다.

    python3 ci/bundle_cli_env_check.py dist/ClaudePet.app/Contents/MacOS/ClaudePet
    python ci\\bundle_cli_env_check.py dist-win\\ClaudePet\\ClaudePet.exe

1.2.0 의 Gemini 인증서 오류(TOK-61)는 번들에만 있었다 — py2app 의 부트 스크립트가 SSL_CERT_FILE·
SSL_CERT_DIR 을 없는 경로로 넣었고 그 환경이 앱이 띄운 agy·로그인 창으로 넘어갔다. 그래서:

  1. 산출물을 `--cli-env-probe <out.json> --agy <가짜 agy>` 로 띄운다(창·CLI·브라우저를 열지 않는다).
  2. 로그인 CLI 의 환경(cli_env × 세 제공자)과 백그라운드 agy 의 환경(_agy_env)마다
       ① SSL_CERT_FILE·SSL_CERT_DIR 이 남아 있지 않고  ② 그 환경으로 curl https://www.google.com 이 성공한다.
  3. Gemini 로그인 창의 스크립트를 번들의 환경에서 가짜 agy 로 실제로 돌린다 — 그 agy 가 본 환경에도
     ①·② 가 성립해야 한다.

환경의 **값**은 찍지 않는다(이름과 통과 여부만). 하나라도 어긋나면 종료 코드 1.
"""
import json
import os
import subprocess
import sys
import tempfile

WIN = sys.platform == "win32"
SSL_KEYS = ("SSL_CERT_FILE", "SSL_CERT_DIR")
URL = "https://www.google.com"
CURL = "curl.exe" if WIN else "/usr/bin/curl"


def make_fake_agy(folder, record):
    """받은 환경에 SSL_* 가 있는지와 curl 의 종료 코드를 record 에 적는 가짜 agy → 경로."""
    if WIN:
        path = os.path.join(folder, "agy.cmd")
        lines = ["@echo off"]
        for i, key in enumerate(SSL_KEYS):
            to = ">" if i == 0 else ">>"
            lines.append('if defined %s (echo %s=set%s "%s") else (echo %s=unset%s "%s")'
                         % (key, key, to, record, key, to, record))
        lines += ["%s -sS -o NUL %s" % (CURL, URL), 'echo curl=%%ERRORLEVEL%%>> "%s"' % record, "exit /b 0"]
        with open(path, "w", encoding="ascii", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        return path
    path = os.path.join(folder, "agy")
    lines = ["#!/bin/sh", ': > "%s"' % record]
    for key in SSL_KEYS:
        lines.append('if [ -n "${%s+x}" ]; then echo %s=set >> "%s"; else echo %s=unset >> "%s"; fi'
                     % (key, key, record, key, record))
    lines += ['%s -sS -o /dev/null %s' % (CURL, URL), 'echo "curl=$?" >> "%s"' % record, "exit 0"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o755)
    return path


def leaked(env):
    return sorted(k for k in env if k.upper() in SSL_KEYS)


def curl_rc(env):
    try:
        return subprocess.run([CURL, "-sS", "-o", os.devnull, URL], env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60).returncode
    except Exception as e:
        return type(e).__name__


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    exe = os.path.abspath(argv[1])
    problems = []
    with tempfile.TemporaryDirectory(prefix="cp-bundle-env-") as tmp:
        tmp = os.path.realpath(tmp)
        out = os.path.join(tmp, "probe.json")
        record = os.path.join(tmp, "agy-saw.txt")
        agy = make_fake_agy(tmp, record)
        try:
            r = subprocess.run([exe, "--cli-env-probe", out, "--agy", agy], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
            print("probe exit code:", r.returncode)
        except subprocess.TimeoutExpired:
            print("FAIL  the bundle did not answer --cli-env-probe within 180 s (flag missing?)")
            return 1
        try:
            with open(out, encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, ValueError) as e:
            print("FAIL  the bundle wrote no probe report:", type(e).__name__)
            return 1
        print("bundle: platform=%s frozen=%s; its own environment carries %s"
              % (report.get("platform"), report.get("frozen"), leaked(report.get("environ") or {}) or "no SSL_CERT_*"))

        envs = [("cli_env(%s)" % p, e) for p, e in sorted((report.get("cli_env") or {}).items())]
        envs.append(("_agy_env()", report.get("agy_env")))
        if len(envs) != 4:
            problems.append("cli_env did not cover the three providers")
        for name, env in envs:
            if not isinstance(env, dict):
                problems.append("%s: no environment was produced" % name)
                continue
            left = leaked(env)
            rc = curl_rc(env)
            print("%-18s SSL_CERT_* left: %-32s curl: %s" % (name, left or "none", rc))
            if left:
                problems.append("%s still carries %s" % (name, ", ".join(left)))
            if rc != 0:
                problems.append("%s: curl %s failed (%s)" % (name, URL, rc))

        win = report.get("login_window")
        if not isinstance(win, dict):
            problems.append("login window: nothing was produced (%s)" % report.get("login_window_error"))
        else:
            base = win.get("env") if isinstance(win.get("env"), dict) else report.get("environ") or {}
            if win.get("kind") == "bash":
                cmd = ["/bin/bash", "-c", win.get("script") or "exit 97"]
            else:
                cmd = [a for a in (win.get("argv") or []) if a != "-NoExit"]
            try:
                subprocess.run(cmd, env=base, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=120, cwd=tmp)
            except Exception as e:
                problems.append("login window: the script did not run (%s)" % type(e).__name__)
            try:
                with open(record, encoding="utf-8") as f:
                    saw = dict(line.strip().split("=", 1) for line in f if "=" in line)
            except OSError:
                saw = {}
            print("login window agy    saw: %s" % (saw or "nothing — agy was not run"))
            if not saw:
                problems.append("login window: the script never ran agy")
            for key in SSL_KEYS:
                if saw and saw.get(key) != "unset":
                    problems.append("login window: agy still received %s" % key)
            if saw and saw.get("curl") != "0":
                problems.append("login window: curl %s failed inside the window (%s)" % (URL, saw.get("curl")))

    for p in problems:
        print("FAIL ", p)
    print("bundle CLI environment:", "FAILED (%d)" % len(problems) if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
