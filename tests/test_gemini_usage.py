"""Gemini 사용량 — agy CLI 로 읽기(TOK-44 계약 v2). Verifier 작성, 구현 전(90fd32b 에서 빨강).

── 왜 바뀌었나 (관측 — Coordinator, 2026-11-18, 이 저장소 주인의 Mac 한 대, agy 1.5.10) ─────────────

`agy -p "/usage" --output-format json` 은 약 4.9초, 모델 토큰 0(usage 가 전부 0)으로 쿼터를 돌려준다.
거기에는 우리가 부르던 HTTP 두 엔드포인트 어디에도 없는 "Gemini Models" 그룹이 있다:
retrieveUserQuota 의 모델별 비율은 1.0 에 머물고(서버 버그로 보임 — antigravity-cli#387 과 맞는다),
retrieveUserQuotaSummary 는 "Claude and GPT models" 만 준다. 그래서 v1 리더는 실제 5시간 사용률 66% 를
0% 로 보였다. 사용자 방향: agy 자신에게 묻는다. 위는 한 기기·한 시점의 관측이다(§5) — 아래 계약은 그
**모양**에 기대고, 숫자는 전부 합성이다.

── 계약 v2 (Coordinator) ────────────────────────────────────────────────────────────────

1. `fetch_gemini_usage()` 는 macOS 에서 정확히 `[<agy>, "-p", "/usage", "--output-format", "json"]` 를
   subprocess 로(셸 없이) 띄운다. timeout ≤ 30초, cwd 는 중립 디렉터리(홈 또는 개인 임시 디렉터리).
   `<agy>` = `shutil.which("agy")`, 없으면 실행 가능한 `~/.local/bin/agy`. 둘 다 없으면 None,
   last_error "not_installed", auth_error False. agy 키체인 항목은 더 이상 읽지 않는다(Gemini 를 위한
   `security` 호출 0).
2. `parse_agy_usage(payload)` — 순수(dict 또는 JSON 문자열, 예외 없음) → 행 `(label, pct_used, reset_dt,
   None)`. 0행 `"gemini"` = Gemini 그룹 버킷 중 remaining_fraction 이 가장 낮은 것(동률이면 리셋이 가장
   이른 것). Gemini 그룹 = 버킷 id 가 "gemini-" 로 시작하는 그룹(없으면 이름에 "Gemini" 가 든 그룹).
   이어서 모든 그룹의 버킷마다 한 행, 서버 순서, `gemini_group:<bucket id>`. 비율 규칙은 v1 과 같다(숫자
   또는 숫자 문자열, [0,1] 로 자름, 못 쓰는 값은 건너뜀, 0/100 을 지어내지 않음). status != "SUCCESS"
   이거나 쓸 버킷이 없으면 None.
3. 실패: 0 아닌 종료 → "agy_failed", 시간 초과 → "timeout", 깨진 JSON → "parse". 로그인이 필요하다는
   답 → auth_error True, last_error "login" — 그 답의 모양은 아직 관측하지 않았다(아래 모호점). 그래서
   여기서는 'SUCCESS 가 아니면 None + 비어 있지 않은 last_error' 만 고정한다.

── 계약 v3·v4 (2026-11-18 — agy 리뷰 지적 반영; v4 는 대표님 지시로 v3 의 로그인 항목을 바꾼 것) ──────────

대표님: "로그인 안 되어 있을 땐 로그인하면 된다고 하고, 로그인 안 하면 표시 안 하면 되는 거야! 왜 로그인을
재시도해". 사실: 로그인 안 된 상태에서 `agy -p /usage` 를 실행하는 것 자체가 agy 의 로그인 절차(OAuth)를
시작한다. agy 에는 로그인 상태만 묻는 명령이 없다. 그래서:

  1. 로그인 여부 = agy 키체인 항목이 **있는지**: `security find-generic-password -s gemini -a antigravity`
     (`-w` 없이 — 비밀값을 열지 않으므로 창이 뜨지 않는다). 종료 0 = 있음, 44 = 없음. 자동으로는 300초에
     한 번, 사용자가 누르면 바로. `keychain_locked()` 이면 이 확인도 하지 않는다(직전 판단 유지).
     `-w`/`-g` 로 agy 비밀값을 읽는 일은 없다.
  2. 항목 없음 → agy 를 **실행하지 않는다**. None, last_error "login", auth_error True. 필에는 아무것도
     없다(tests/test_gemini_pill.py). 다음 확인에서 항목이 보이면 그 조회에서 바로 읽는다.
  3. 항목 있음 → `/usage` 실행. 그런데 agy 가 로그인을 요구하면(refresh token 만료·취소 — stderr 에
     "Authentication required. Please visit the URL to log in" / "Run 'agy' to log in"): **그 즉시 agy 를
     끝내고**(timeout 을 기다리지 않는다, 남은 프로세스 없음), 행을 지우고, "login"/auth_error True, 자동
     실행을 멈춘다 — 사용자가 누를 때까지(tests/test_gemini_agy_cadence.py). 시간 초과 예외에 실린 출력
     (bytes)도 같은 낱말로 본다.
  4. 오프라인 토큰 갱신 실패("authentication failed or timed out", "Error: authentication failed: …")는
     로그인 안 됨이 아니다 — 일시 실패("agy_failed" / "timeout").
  5. 버킷에 `"disabled": true` 가 있으면 건너뛴다(0행 계산에서도, 행에서도).
  6. `mood_for(…, gemini_rows=…)` — 보이는 Gemini 의 고른 게이지 행도 펫 기분에 든다.

── 계약 v5 (agy 와 합의한 최종안, 2026-11-18 — v4 에 더한다) ──────────────────────────────────

  a. (v5-1 로 교체, 2026-11-18 — Developer 실측: agy 1.5.11 은 SSH 를 감지하면 토큰 저장소를 키체인에서
     파일로 바꿔 로그인된 사용자를 "로그인 필요"로 본다. `SSH_TTY=1` 은 쓸 수 없다.)
     백그라운드 `/usage` 실행의 env 는 os.environ 의 사본이고, `SSH_CLIENT`·`SSH_TTY`·`SSH_CONNECTION`
     은 **없다**(앱 환경에 있어도 사본에서 지운다). `NO_COLOR=1`. `PATH` 의 맨 앞은 앱 전용 폴더(0700,
     소유자 본인)이고 그 안의 실행 가능한 `open` 은 인자를 무시하고 아무것도 하지 않은 채 0 으로 끝난다 —
     agy 가 브라우저를 열려고 부르는 `open <url>` 이 거기서 끝난다. 나머지 PATH 는 원래 순서 그대로.
     앱 자신의 os.environ 은 바뀌지 않는다. 메뉴 로그인(start_gemini_login)에는 가짜 open 이 없다.
  b. stderr 에 "Authentication required" / "visit the URL to log in" / "Run 'agy'" 가 보이면 바로 프로세스
     **그룹**을 끝낸다(남은 프로세스 없음 — agy 가 띄운 자식도).
  c. 지문(marker) = 존재 확인 출력의 `"mdat"` 줄 + 폴백 파일 `~/.gemini/antigravity-cli/
     antigravity-oauth-token` 의 존재·mtime. 항목도 폴백 파일도 없으면 agy 0회. 항목(또는 폴백 파일)이
     있는데 agy 가 로그인을 요구하면 그때의 지문을 기억하고 자동 실행을 멈춘다. 300초마다의 확인에서
     지문이 **달라지면**(사용자가 로그인을 마쳐 agy 가 키체인을 다시 씀) 클릭 없이 다시 읽는다. 그대로면
     다시 띄우지 않는다.
  d. 오프라인 갱신 실패의 실제 모양: stdout `{"schemaVersion":1,"status":"ERROR","error":"authentication
     failed or timed out"}`, 종료 1, stderr 에 "token refresh failed due to network error" — 일시 실패.
     60초를 다 기다린 로그인 요구도 **같은 stdout** 으로 끝난다(stderr 에 "Run 'agy' interactively to log
     in") — 그쪽은 "login" 이다. 둘은 stderr 로만 갈린다.

관측(agy 리뷰·협의 보고, 한 기기, agy 1.5.10, 샌드박스 재현): 로그인하지 않은 agy 는 stdout 에 아무것도 쓰지 않고
stderr 에 위 안내를 쓴 뒤 60초를 기다린다. 바로 실패하는 경우의 stderr 는 "Error: authentication required.
Run 'agy' to log in." 이다. 아래 문구는 그 모양을 본뜬 합성이다.

이 파일은 하네스도 겸한다 — test_gemini_agy_cadence.py 와 test_gemini_pill.py 가 `AgyFake`, `agy_payload`,
`refresh_worker`, `wait_for`, `app_hook` 를 가져다 쓴다. 진짜 agy·키체인·네트워크는 건드리지 않는다.

v3 부터 가짜 agy 는 **진짜 자식 프로세스**다: 테스트 동안 `subprocess.Popen` 이 어떤 명령이든 작은 파이썬
에뮬레이터(`sys.executable -I -S -c …`)로 바꿔 띄운다. agy 를 띄우면 그 에뮬레이터가 mode 대로 stdout·
stderr 를 쓰고 끝나거나 끝나지 않는다. 이유: 로그인 판정은 stderr 를 읽다 일찍 끝내는 것, 시간 초과 예외에
실린 출력(bytes), 프로세스 정리에 달려 있고, 그것을 손으로 흉내 낸 대역은 리뷰가 찾은 바로 그 결함(예외의 stderr 를 안 봄, bytes)을
가릴 수 없다. 그리고 구현이 `subprocess.run` 을 쓰든 `Popen` 으로 stderr 를 읽다 일찍 끝내든 같은
하네스로 돈다. `security` 도 에뮬레이터가 대신한다(실행되지 않는다): `fake.keychain` 이 "present" 면 종료 0,
"absent" 면 44. 그 밖의 명령은 종료 1. 모두 기록만 남는다.
`os.system` 은 막혀 있다. HOME 은 임시 디렉터리, `shutil.which("agy")` 는 대역.
끝나지 않는 mode(timeout·login_wait·offline_wait)에서는 기다림을 SHORT 초로 줄인다(run 의 timeout 인자와
자식의 communicate/wait timeout 을 자르고, `claude_pet.GEMINI_AGY_TIMEOUT` 이 있으면 그것도) — 30초를
실제로 기다리지 않으려는 것뿐이다.
"""

import ast
import copy
import json
import math
import os
import stat
import shutil
import subprocess
import sys
import tempfile
import threading
import time as _real_time
import unittest
from datetime import datetime as _real_datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import claude_pet  # noqa: E402
except ImportError:
    from windows.win_core import import_core  # noqa: E402
    claude_pet = import_core()

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "claude_pet.py"
UTC = timezone.utc
AGY_ARGS = ["-p", "/usage", "--output-format", "json"]


def _require(name):
    value = getattr(claude_pet, name, None)
    if value is None:
        raise AssertionError(
            f"claude_pet.{name} 가 없다 — TOK-44 계약 v2(agy CLI 로 읽기)가 아직 구현되지 않았다. "
            "이 파일은 구현 전에 쓰였고 지금 빨간 것이 정상이다.")
    return value


def _utc(y, mo, d, h=0, mi=0, s=0):
    return _real_datetime(y, mo, d, h, mi, s, tzinfo=UTC)


# ═════════════════════════════ 합성 agy 응답 (관측된 모양) ═════════════════════════════

def _bucket(bid, window, frac, reset, name="synthetic"):
    b = {"id": bid, "name": name, "description": "synthetic", "window": window, "reset_time": reset}
    if frac is not _MISSING:
        b["remaining_fraction"] = frac
    return b


_MISSING = object()

# Gemini 그룹은 버킷 셋 — 가장 낮은 것(gemini-5h)이 **가운데**(AGENTS.md §3: 둘이면 첫째나 마지막과
# 반드시 겹친다). 세 번째 버킷(monthly)은 지어냈다. Claude·GPT 그룹에는 그보다 더 낮은 비율(0.1)을 둔다.
GEMINI_GROUP = {"name": "Gemini Models", "description": "Models within this group: synthetic",
                "buckets": [
                    _bucket("gemini-weekly", "weekly", 0.8, "2026-11-25T02:13:31Z"),
                    _bucket("gemini-5h", "5h", 0.34, "2026-11-18T07:13:31Z"),
                    _bucket("gemini-monthly", "monthly", "0.6", "2026-12-01T00:00:00Z"),
                ]}
OTHER_GROUP = {"name": "Claude and GPT models", "description": "synthetic",
               "buckets": [
                   _bucket("3p-weekly", "weekly", 0.9, "2026-11-25T03:45:42Z"),
                   _bucket("3p-5h", "5h", 0.1, "2026-11-18T08:45:42Z"),
               ]}


def agy_payload(groups=None, status="SUCCESS"):
    groups = [GEMINI_GROUP, OTHER_GROUP] if groups is None else groups
    return {"conversation_id": "", "status": status,
            "response": "Gemini Models\tWeekly Limit Remaining\t80%\t2026-11-25T02:13:31Z\n",
            "duration_seconds": 0, "num_turns": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "command": {"name": "usage", "data": {"description": "synthetic",
                                                  "groups": copy.deepcopy(groups)}}}


# TOK-63(1.2.2): 버킷 하나에 행 하나 — 대표 "gemini" 행은 없다. Gemini 묶음이 먼저, 묶음 안에서는 창이
# 짧은 것부터(세션 → 주간 → 그 밖). 서버는 주간을 먼저 준다(위 픽스처).
EXPECTED_ROWS = [
    ("gemini_group:gemini-5h", 66.0, _utc(2026, 11, 18, 7, 13, 31), None),
    ("gemini_group:gemini-weekly", 20.0, _utc(2026, 11, 25, 2, 13, 31), None),
    ("gemini_group:gemini-monthly", 40.0, _utc(2026, 12, 1), None),
    ("gemini_group:3p-5h", 90.0, _utc(2026, 11, 18, 8, 45, 42), None),
    ("gemini_group:3p-weekly", 10.0, _utc(2026, 11, 25, 3, 45, 42), None),
]


def assert_rows(test, got, expected, msg=""):
    test.assertIsInstance(got, list, "%s행은 list 여야 한다 (받은 것 %r)" % (msg, got))
    test.assertEqual([r[0] for r in got], [e[0] for e in expected], "%s라벨·순서" % msg)
    for row, exp in zip(got, expected):
        test.assertEqual(len(row), 4)
        test.assertIsInstance(row[1], float, "%s%s: pct 는 float" % (msg, row[0]))
        test.assertTrue(math.isfinite(row[1]))
        test.assertAlmostEqual(row[1], exp[1], places=6, msg="%s%s pct" % (msg, row[0]))
        if exp[2] is None:
            test.assertIsNone(row[2])
        else:
            test.assertIsNotNone(getattr(row[2], "tzinfo", None), "%s%s: aware reset" % (msg, row[0]))
            test.assertEqual(row[2], exp[2], "%s%s reset" % (msg, row[0]))
        test.assertIsNone(row[3])


# ═════════════════════════════ 하네스: agy 대역 ═════════════════════════════

_REAL_POPEN = subprocess.Popen
_REAL_RUN = subprocess.run
SHORT = 1.5              # 끝나지 않는 mode 에서 실제로 기다리는 상한(초)
_FOREVER = 20            # '끝나지 않는' 에뮬레이터가 스스로 끝나는 시각(초) — 고아가 남지 않게

# 관측된 문구의 모양을 본뜬 합성(위 계약 v3). 마지막 줄은 줄바꿈 없이 끝난다(입력 프롬프트).
LOGIN_WAIT_STDERR = (
    "Authentication required. Please visit the URL to log in:\n"
    "  https://accounts.example.invalid/o/oauth2/auth?synthetic=1\n"
    "\n"
    "Waiting for authentication (timeout 60s)...\n"
    "Or, paste the authorization code here and press Enter: ")
LOGIN_EXIT_STDERR = "Error: authentication required. Run 'agy' to log in.\n"
LOGIN_TIMEOUT_STDERR = (
    "Authentication required. Please visit the URL to log in:\n"
    "  https://accounts.example.invalid/o/oauth2/auth?synthetic=1\n"
    "\n"
    "Waiting for authentication (timeout 60s)...\n"
    "Error: authentication timed out after 60s. Run 'agy' interactively to log in.\n")
OFFLINE_STDERR_A = "Error: authentication failed: token refresh failed due to network error: synthetic\n"
OFFLINE_STDERR_B = "authentication failed or timed out\n"
# 오프라인 갱신 실패와 60초를 다 기다린 로그인 요구가 **똑같이** 내는 stdout(v5 d).
AUTH_ERROR_STDOUT = ('{"schemaVersion":1,"status":"ERROR",'
                     '"error":"authentication failed or timed out"}\n')

# mode → (stdout — None 이면 payload, stderr, 종료 코드, 끝나는 방식: exit | forever | release)
AGY_MODES = {
    "ok": (None, "", 0, "exit"),
    "hang": (None, "", 0, "release"),
    "fail": ("", "synthetic agy failure\n", 1, "exit"),
    "garbage": ("{not json", "", 0, "exit"),
    "timeout": ("", "", 0, "forever"),
    "login_wait": ("", LOGIN_WAIT_STDERR, 0, "forever"),
    "login_exit": ("", LOGIN_EXIT_STDERR, 1, "exit"),
    "login_timeout_exit": (AUTH_ERROR_STDOUT, LOGIN_TIMEOUT_STDERR, 1, "exit"),
    "offline_exit_a": (AUTH_ERROR_STDOUT, OFFLINE_STDERR_A, 1, "exit"),
    "offline_exit_b": (AUTH_ERROR_STDOUT, OFFLINE_STDERR_B, 1, "exit"),
    "offline_wait": ("", OFFLINE_STDERR_B, 0, "forever"),
}

_EMULATOR = r"""
import json, os, sys, time
spec = json.load(open(sys.argv[1], encoding="utf-8"))
if spec.get("gpids"):
    # agy 가 띄우는 자식(브라우저 여는 도우미 등)의 대역 — 같은 프로세스 그룹, 파이프는 물려받지 않는다.
    import subprocess
    g = subprocess.Popen([sys.executable, "-I", "-S", "-c", "import time; time.sleep(%d)" % spec["forever"]],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(spec["gpids"], "a", encoding="utf-8") as f:
        f.write("%d\n" % g.pid)
sys.stderr.write(spec["stderr"]); sys.stderr.flush()
end = time.time() + spec["forever"]
if spec["how"] == "forever":
    while time.time() < end:
        time.sleep(0.05)
    sys.exit(3)
if spec["how"] == "release":
    while not os.path.exists(spec["release"]) and time.time() < end:
        time.sleep(0.02)
sys.stdout.write(spec["stdout"]); sys.stdout.flush()
sys.exit(spec["rc"])
"""


class _Child(_REAL_POPEN):
    """에뮬레이터 자식. 끝나지 않는 mode 에서는 communicate/wait 의 timeout 을 _never(초)로 자른다."""

    _never = None

    def _clamp(self, timeout):
        if self._never is not None and isinstance(timeout, (int, float)):
            return min(timeout, self._never)
        return timeout

    def communicate(self, input=None, timeout=None):
        return super().communicate(input, self._clamp(timeout))

    def wait(self, timeout=None):
        return super().wait(self._clamp(timeout))


class _Release:
    """hang mode 의 자식을 풀어 주는 깃발(threading.Event 의 set/is_set 모양)."""

    def __init__(self, path):
        self.path = path

    def set(self):
        with open(self.path, "w", encoding="utf-8"):
            pass

    def is_set(self):
        return os.path.exists(self.path)


class AgyFake:
    """subprocess.run / subprocess.Popen 의 대역. 어떤 명령이든 진짜로는 실행하지 않고, 에뮬레이터 자식을
    대신 띄운다. agy 는 mode(AGY_MODES) 대로 답하고, `security` 는 종료 코드 44, 그 밖은 1 이다.
    calls: agy 를 띄운 기록 [(시각, argv, 띄운 쪽이 준 kwargs)] — run 으로 띄웠으면 run 의 kwargs."""

    def __init__(self, clock=None):
        self.clock = clock or _real_time
        self.payload = agy_payload()
        self.mode = "ok"
        self.keychain = "present"      # agy 키체인 항목: present(종료 0) | absent(종료 44)
        self.mdat = "20261118062000Z"  # 그 항목의 수정 시각(존재 확인 출력의 "mdat" 줄)
        self.wait = SHORT              # 끝나지 않는 mode 에서 실제로 기다리는 상한(초)
        self.calls = []
        self.security = []             # security argv 들
        self.security_at = []          # 그 시각들
        self.other = []
        self.blocked = []
        self.children = []       # agy 로 띄운 에뮬레이터 자식
        self._all = []
        self._dir = tempfile.mkdtemp(prefix="claudepet-agyfake-")
        self._n = 0
        self._local = threading.local()
        self.hang = _Release(os.path.join(self._dir, "release"))
        self._gpids = os.path.join(self._dir, "grandchildren")

    # ── subprocess.run ──
    def run(self, argv, *a, **k):
        if isinstance(argv, (str, bytes)) or k.get("shell"):
            self.other.append(("shell-string", str(argv)[:40]))
            raise AssertionError("문자열 명령 — 셸 없이 argv 목록으로 띄워야 한다")
        argv = [str(x) for x in argv]
        is_agy = bool(argv) and os.path.basename(argv[0]) == "agy"
        kk = dict(k)
        if is_agy:
            self.calls.append((self.clock.time(), argv, dict(k)))
            if AGY_MODES[self.mode][3] == "forever":
                given = kk.get("timeout")
                kk["timeout"] = (min(given, self.wait) if isinstance(given, (int, float))
                                 else self.wait)
        self._local.in_run = is_agy
        try:
            return _REAL_RUN(argv, *a, **kk)
        finally:
            self._local.in_run = False

    # ── subprocess.Popen ──
    def popen(self, args, *a, **k):
        if isinstance(args, (str, bytes)) or k.get("shell"):
            self.other.append(("shell-string", str(args)[:40]))
            raise AssertionError("문자열 명령 — 셸 없이 argv 목록으로 띄워야 한다")
        argv = [str(x) for x in args]
        base = os.path.basename(argv[0]) if argv else ""
        never = None
        if base == "agy":
            if not getattr(self._local, "in_run", False):
                self.calls.append((self.clock.time(), argv, dict(k)))
            stdout, stderr, rc, how = AGY_MODES[self.mode]
            if stdout is None:
                stdout = (self.payload if isinstance(self.payload, str)
                          else json.dumps(self.payload)) + "\n"
            never = self.wait if how == "forever" else None
        elif base == "security":
            self.security.append(argv)
            self.security_at.append(self.clock.time())
            if self.keychain == "present":
                # -w 없는 답의 모양(속성만). 비밀값은 어디에도 없다 — 합성이다.
                # 진짜 출력처럼 수정 시각 줄이 있다: "mdat"<timedate>=0x… "YYYYMMDDHHMMSSZ\000"
                stdout, stderr, rc, how = (
                    'keychain: "synthetic.keychain-db"\nversion: 512\nclass: "genp"\nattributes:\n'
                    '    "acct"<blob>="antigravity"\n'
                    '    "cdat"<timedate>=0x00 "20260101000000Z\\000"\n'
                    '    "mdat"<timedate>=0x00 "%s\\000"\n'
                    '    "svce"<blob>="gemini"\n' % self.mdat), "", 0, "exit"
            else:
                stdout, stderr, rc, how = "", ("security: SecKeychainSearchCopyNext: The specified "
                                               "item could not be found in the keychain.\n"), 44, "exit"
        else:
            self.other.append(argv[:2])
            stdout, stderr, rc, how = "", "", 1, "exit"
        self._n += 1
        spec = os.path.join(self._dir, "spec-%d.json" % self._n)
        with open(spec, "w", encoding="utf-8") as f:
            json.dump({"stdout": stdout, "stderr": stderr, "rc": rc, "how": how,
                       "release": self.hang.path, "forever": _FOREVER,
                       "gpids": self._gpids if (base == "agy" and self.mode == "login_wait")
                       else None}, f)
        k.pop("executable", None)
        child = _Child([sys.executable, "-I", "-S", "-c", _EMULATOR, spec], *a, **k)
        child._never = never
        self._all.append(child)
        if base == "agy":
            self.children.append(child)
        return child

    def system(self, *a, **k):
        self.blocked.append("os.system")
        return 1

    def grandchildren(self):
        """agy 대역이 띄운 자식 중 아직 살아 있는 pid 들."""
        try:
            with open(self._gpids, encoding="utf-8") as f:
                pids = [int(x) for x in f.read().split()]
        except OSError:
            return []
        live = []
        for pid in pids:
            try:
                os.kill(pid, 0)
                live.append(pid)
            except OSError:
                pass
        return live

    def alive(self, grace=2.0):
        """아직 돌고 있는 agy 프로세스의 수 — agy 자신과 그것이 띄운 자식(grace 초까지 기다려 본다)."""
        end = _real_time.time() + grace
        while _real_time.time() < end and (any(c.poll() is None for c in self.children)
                                           or self.grandchildren()):
            _real_time.sleep(0.02)
        return sum(1 for c in self.children if c.poll() is None) + len(self.grandchildren())

    def close(self):
        self.hang.set()
        for pid in self.grandchildren():
            try:
                os.kill(pid, 9)
            except OSError:
                pass
        for c in self._all:
            try:
                if c.poll() is None:
                    c.kill()
                c.wait(5)
                for stream in (c.stdin, c.stdout, c.stderr):
                    if stream is not None:
                        stream.close()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(self._dir, ignore_errors=True)


def _gemini_dicts():
    return {n: v for n, v in vars(claude_pet).items()
            if isinstance(v, dict) and "gemini" in n.lower()}


PRISTINE = {n: copy.deepcopy(v) for n, v in _gemini_dicts().items()}


def reset_gemini_state(test=None):
    """Gemini 모듈 상태를 임포트 시점으로(재시작). test 를 주면 끝나고 지금 값으로 되돌린다."""
    for name, d in _gemini_dicts().items():
        if test is not None:
            snap = copy.deepcopy(d)
            test.addCleanup(lambda d=d, snap=snap: (d.clear(), d.update(snap)))
        if name in PRISTINE:
            d.clear()
            d.update(copy.deepcopy(PRISTINE[name]))
    status = getattr(claude_pet, "GEMINI_STATUS", None)
    if isinstance(status, dict):
        status.update({"auth_error": False, "last_error": None})
    fn = getattr(claude_pet, "_reset_keychain_quiet_state", None)
    if fn is not None:
        fn()


class AgyCase(unittest.TestCase):
    """HOME 은 임시, agy 는 /…/bin/agy 대역(which), subprocess 는 AgyFake, 플랫폼은 darwin."""

    def never_exits(self, mode, wait=SHORT):
        """끝나지 않는 mode 로 바꾸고, 구현이 기다리는 상한을 wait 초로 줄인다(있으면)."""
        self.fake.mode = mode
        self.fake.wait = wait
        if isinstance(getattr(claude_pet, "GEMINI_AGY_TIMEOUT", None), (int, float)):
            self._patch(mock.patch.object(claude_pet, "GEMINI_AGY_TIMEOUT", wait))

    SSH_ENV = {"SSH_TTY": "/dev/ttys009", "SSH_CLIENT": "192.0.2.1 50000 22",
               "SSH_CONNECTION": "192.0.2.1 50000 192.0.2.2 22"}

    def app_runs_over_ssh(self):
        """앱 자신의 환경에 SSH_* 세 키를 넣어 둔다(합성 값) — 사본에서 빠지는지 보려고."""
        self._patch(mock.patch.dict(os.environ, self.SSH_ENV))

    def assert_background_env(self, env, app_env_before):
        """계약 v5-1: 백그라운드 agy 에 준 env. `app_env_before` 는 조회 전의 dict(os.environ)."""
        self.assertIsInstance(env, dict, "agy 에 env 를 주지 않았다 — 가짜 open 이 없으면 agy 가 브라우저를 연다")
        for key in ("SSH_CLIENT", "SSH_TTY", "SSH_CONNECTION"):
            # assertNotIn 은 실패 때 env 전체를 찍는다 — 환경변수 값이 기록에 남지 않게 참·거짓만 본다.
            self.assertFalse(key in env, "%s 가 agy 의 env 에 있다 — agy 가 토큰 저장소를 파일로 바꾼다" % key)
        self.assertEqual(env.get("NO_COLOR"), "1")
        # v7-W4: 조회용 agy 가 자동 업데이터를 띄우지 않게 — 끊을 때 바이너리 교체 도중 죽지 않는다.
        self.assertEqual(env.get("AGY_CLI_DISABLE_AUTO_UPDATE"), "1",
                         "백그라운드 agy 의 env 에 AGY_CLI_DISABLE_AUTO_UPDATE=1 이 없다")
        self.assertEqual(env.get("HOME"), self.home, "env 가 os.environ 의 사본이 아니다(HOME 이 없다)")
        self.assertTrue(dict(os.environ) == app_env_before, "앱 자신의 환경을 바꿨다")

        parts = (env.get("PATH") or "").split(os.pathsep)
        rest = app_env_before["PATH"].split(os.pathsep)
        self.assertTrue(parts[1:] == rest, "원래 PATH 가 순서 그대로 뒤에 붙지 않았다(맨 앞 하나만 더해야 한다)")
        folder = parts[0]
        self.assertTrue(os.path.isabs(folder), "PATH 맨 앞이 절대 경로가 아니다: %r" % folder)
        self.assertNotIn(folder, rest)
        real = os.path.realpath(folder)
        self.assertTrue(real.startswith(os.path.realpath(self.home) + os.sep)
                        or real.startswith(os.path.realpath(tempfile.gettempdir()) + os.sep),
                        "가짜 open 폴더가 테스트 홈·임시 폴더 밖이다: %r" % folder)
        self.assertTrue(os.path.lexists(folder), "PATH 맨 앞 폴더가 없다 — 가짜 open 폴더를 만들지 않았다")
        st = os.lstat(folder)
        self.assertTrue(stat.S_ISDIR(st.st_mode), "PATH 맨 앞이 진짜 폴더가 아니다(링크?)")
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o700, "가짜 open 폴더가 소유자 전용(0700)이 아니다")
        self.assertEqual(st.st_uid, os.getuid())

        fake = os.path.join(folder, "open")
        self.assertTrue(os.path.lexists(fake), "PATH 맨 앞 폴더에 `open` 이 없다")
        fst = os.lstat(fake)
        self.assertTrue(stat.S_ISREG(fst.st_mode), "`open` 이 보통 파일이 아니다(링크면 진짜 open 일 수 있다)")
        self.assertEqual(fst.st_uid, os.getuid())
        self.assertFalse(stat.S_IMODE(fst.st_mode) & 0o022, "`open` 을 남이 고칠 수 있다")
        self.assertTrue(os.access(fake, os.X_OK), "`open` 을 실행할 수 없다")
        # 실행해 보기 전에: 진짜 open 을 부르는 스크립트라면 여기서 브라우저가 열린다 — 돌리지 않고 떨어뜨린다.
        with open(fake, "rb") as f:
            body = f.read(4096)
        self.assertLess(len(body), 4096, "`open` 이 아무것도 안 하기에는 너무 크다")
        for word in (b"/usr/bin/open", b"osascript", b"$@", b"$*", b"exec ", b"http"):
            self.assertNotIn(word, body, "`open` 이 무언가를 실행하려 한다: %r" % word)
        # agy 가 부르는 그대로(이 env, 이름만으로 찾게) 진짜로 실행한다: 곧바로 0, 출력 없음, 남는 프로세스 없음.
        self.assertEqual(shutil.which("open", path=env["PATH"]), fake, "PATH 에서 찾은 open 이 가짜가 아니다")
        for args in ([], ["https://accounts.example.invalid/o/oauth2/auth?synthetic=1"],
                     ["-a", "Synthetic Browser", "https://example.invalid/"]):
            t0 = _real_time.time()
            child = _REAL_POPEN([fake] + args, env=env, cwd=self.home, start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                out, err = child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, 9)
                child.communicate()
                self.fail("가짜 open 이 끝나지 않는다(인자 %r)" % (args,))
            self.assertEqual(child.returncode, 0, "가짜 open 이 0 으로 끝나지 않았다(인자 %r)" % (args,))
            self.assertLess(_real_time.time() - t0, 3.0)
            self.assertEqual((out, err), (b"", b""))
            with self.assertRaises(OSError, msg="가짜 open 이 프로세스를 남겼다(인자 %r)" % (args,)):
                os.killpg(child.pid, 0)

    def write_fallback(self, mtime):
        """agy 의 파일 폴백 저장소(키체인을 못 쓰는 환경)를 만든다 — 내용은 합성, mtime 은 주는 값."""
        os.makedirs(os.path.dirname(self.fallback), exist_ok=True)
        with open(self.fallback, "w", encoding="utf-8") as f:
            f.write("{}")
        os.utime(self.fallback, (mtime, mtime))

    def assert_only_existence_checks(self, at_least=0):
        """Gemini 를 위한 security 호출은 존재 확인뿐이다: 정확히
        `security find-generic-password -s gemini -a antigravity`(-s/-a 의 순서는 상관없다). `-w`·`-g`
        (비밀값을 여는 인자)는 없다."""
        for argv in self.fake.security:
            self.assertNotIn("-w", argv, "agy 비밀값을 읽었다(-w)")
            self.assertNotIn("-g", argv, "agy 비밀값을 읽었다(-g)")
            self.assertEqual(argv[1:2], ["find-generic-password"], "존재 확인이 아니다: %r" % argv[1:])
            pairs = sorted(zip(argv[2::2], argv[3::2]))
            self.assertEqual((len(argv), pairs), (6, [("-a", "antigravity"), ("-s", "gemini")]),
                             "존재 확인의 인자가 다르다: %r" % argv[1:])
        self.assertGreaterEqual(len(self.fake.security), at_least,
                                "agy 키체인 항목이 있는지 확인하지 않았다")

    clock = None

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="claudepet-agy-")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.agy_path = os.path.join(self.home, "fakebin", "agy")
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home)
        env.pop("CLAUDE_PET_DEBUG", None)
        for name in ("ANTIGRAVITY_APP_DATA_DIR", "SSH_TTY", "SSH_CLIENT", "SSH_CONNECTION"):
            env.pop(name, None)
        self._patch(mock.patch.dict(os.environ, env, clear=True))
        self.fallback = os.path.join(self.home, ".gemini", "antigravity-cli", "antigravity-oauth-token")
        self.fake = AgyFake(self.clock)
        self.addCleanup(self.fake.close)
        self.which = {"agy": self.agy_path}
        real_which = shutil.which
        self._patch(mock.patch.object(claude_pet.shutil, "which",
                                      lambda name, *a, **k: self.which.get(name)
                                      if name in self.which else real_which(name, *a, **k)))
        self._patch(mock.patch.object(sys, "platform", "darwin"))
        self._patch(mock.patch.object(claude_pet.subprocess, "run", self.fake.run))
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen", self.fake.popen))
        self._patch(mock.patch.object(claude_pet.os, "system", self.fake.system))
        self._patch(mock.patch.object(claude_pet, "keychain_locked", lambda: False, create=True))
        self._patch(mock.patch.object(claude_pet, "_dbg", lambda *a, **k: None))
        self._patch(mock.patch("socket.create_connection",
                               side_effect=AssertionError("테스트가 네트워크에 나가려 했다")))
        reset_gemini_state(self)

    def _patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def status(self):
        return dict(getattr(claude_pet, "GEMINI_STATUS", {}) or {})


# ═════════════════════════════ 하네스: 새로고침 워커와 앱 훅 ═════════════════════════════

def refresh_worker(test, state, claude_rows, codex_rows):
    """run_gui 의 `refresh_` 를 꺼내 손으로 만든 scope 에서 돌릴 함수로. Claude/Codex 조회는 즉시 답하는
    대역, Gemini 쪽은 진짜 모듈 코드다(위 AgyFake 가 subprocess 를 대신한다)."""
    from test_companion_motion import gui_functions

    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    gui = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_gui")
    found = [n for n in ast.walk(gui) if isinstance(n, ast.FunctionDef) and n.name == "refresh_"]
    test.assertEqual(len(found), 1, "run_gui 에 refresh_ 가 정확히 하나여야 한다")
    scope = dict(vars(claude_pet))
    now_utc = _real_datetime.now(UTC)
    scope.update({
        "state": state,
        "fetch_exact_usage": lambda: claude_rows, "fetch_codex_usage": lambda: codex_rows,
        "compute_usage": lambda **k: {"now": now_utc, "rows": []},
        "model_keyword_from_rows": lambda rows: None, "parse_codex_entries": lambda since: [],
        "learn_server_limits": lambda *a, **k: None, "claude_spikes": lambda *a, **k: {},
        "codex_spikes": lambda *a, **k: {}, "fetch_api_cost_today": lambda: None,
        "fetch_api_cost_month": lambda: None, "fetch_codex_cost_today": lambda: None,
        "fetch_codex_cost_month": lambda: None,
        "compute_codex_onboard_state": lambda *a, **k: None,
        "read_codex_token": lambda *a, **k: None, "_find_codex_cli": lambda: None,
        "codex_home_exists": lambda *a, **k: False,
        "compute_onboard_state": lambda *a, **k: None, "claude_token_present": lambda: False,
        "session_reset_jump": lambda *a, **k: False, "_recovery_step": lambda *a, **k: None,
        "_run_update_check": lambda *a, **k: None, "set_override": lambda *a, **k: None,
        "_upd_cache": {"t": _real_time.time(), "busy": False}, "OAUTH_EXTRA": {"credit": None},
    })
    gui_defs = {n.name for n in gui.body if isinstance(n, ast.FunctionDef)}
    loads = {n.id for n in ast.walk(found[0]) if isinstance(n, ast.Name)
             and isinstance(n.ctx, ast.Load)}
    extra = sorted((loads & gui_defs) - set(scope))
    if extra:
        gui_functions(test, tuple(extra), scope)
    exec(compile(ast.Module(body=[found[0]], type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["refresh_"]


class _FakeTime:
    """`time` 모듈의 대역 — time() 만 dict 의 "now" 를 읽고 나머지는 진짜다."""

    def __init__(self, box):
        self.box = box

    def time(self):
        return self.box["now"]

    def __getattr__(self, name):
        return getattr(_real_time, name)


def wait_for(cond, seconds):
    end = _real_time.time() + seconds
    while _real_time.time() < end:
        if cond():
            return True
        _real_time.sleep(0.02)
    return cond()


def app_hook(test, state):
    """run_gui 의 `state["gemini_summary"]` 람다를 이 state 로 묶어 돌려준다(앱이 필에 쓰는 바로 그 훅)."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    gui = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_gui")
    hooks = [n.value for n in ast.walk(gui)
             if isinstance(n, ast.Assign) and len(n.targets) == 1
             and isinstance(n.targets[0], ast.Subscript)
             and isinstance(n.targets[0].slice, ast.Constant)
             and n.targets[0].slice.value == "gemini_summary"]
    test.assertEqual(len(hooks), 1, 'run_gui 에 state["gemini_summary"] 훅이 정확히 하나여야 한다')
    return eval(compile(ast.Expression(body=hooks[0]), str(SOURCE), "eval"),
                dict(vars(claude_pet), state=state))


# ═════════════════════════════ 2. parse_agy_usage ═════════════════════════════


class ParseAgyUsageTests(unittest.TestCase):

    def parse(self, payload):
        return _require("parse_agy_usage")(payload)

    def test_rows_are_the_lowest_gemini_bucket_then_every_bucket_in_server_order(self):
        """(이름은 옛 계약의 것이다.) TOK-63: 버킷 하나에 행 하나, 대표 "gemini" 행은 없다. Gemini 묶음이 먼저,
        묶음 안에서는 창이 짧은 것부터 — 서버는 주간을 먼저 줬다. dict 와 JSON 문자열이 같은 답.
        Rivals: 대표 행을 앞에 둠(같은 66% 가 두 번); 서버 순서(주간이 먼저); 남은 비율 그대로(34%); ×100
        누락; Gemini 묶음만; id 정렬(3p-5h 가 맨 앞); 버킷 이름을 라벨로; 숫자 문자열("0.6") 거부."""
        assert_rows(self, self.parse(agy_payload()), EXPECTED_ROWS, "dict: ")
        assert_rows(self, self.parse(json.dumps(agy_payload())), EXPECTED_ROWS, "JSON: ")

    def test_the_server_order_never_reaches_the_rows(self):
        """서버가 묶음·버킷을 어떤 순서로 보내도 행은 같다. Rival: 서버 순서를 따름."""
        def shuffled(group, order):
            return dict(group, buckets=[group["buckets"][i] for i in order])
        for name, groups in (
                ("groups swapped", [OTHER_GROUP, GEMINI_GROUP]),
                ("buckets reversed", [shuffled(GEMINI_GROUP, (2, 1, 0)), shuffled(OTHER_GROUP, (1, 0))]),
                ("both", [shuffled(OTHER_GROUP, (1, 0)), shuffled(GEMINI_GROUP, (1, 2, 0))])):
            with self.subTest(order=name):
                assert_rows(self, self.parse(agy_payload(groups)), EXPECTED_ROWS)

    def test_a_lowest_fraction_tie_takes_the_earliest_reset(self):
        """(이름은 옛 계약의 것이다.) 같은 창 길이의 버킷끼리는 서버 순서가 남고, 더 긴 창은 그 뒤다 —
        비율이나 리셋 시각으로 다시 줄 세우지 않는다. Rivals: 비율 순; 리셋 순; id 순."""
        g = {"name": "Gemini Models", "buckets": [
            _bucket("gemini-c", "5h", 0.2, "2026-11-18T11:00:00Z"),
            _bucket("gemini-w", "weekly", 0.5, "2026-11-18T08:00:00Z"),
            _bucket("gemini-a", "5h", 0.3, "2026-11-18T09:00:00Z"),
            _bucket("gemini-b", "5h", 0.1, "2026-11-18T10:00:00Z")]}
        rows = self.parse(agy_payload([g]))
        self.assertIsInstance(rows, list)
        self.assertEqual([r[0] for r in rows], ["gemini_group:gemini-c", "gemini_group:gemini-a",
                                                "gemini_group:gemini-b", "gemini_group:gemini-w"])

    def test_the_gemini_group_is_found_by_bucket_ids_then_by_name(self):
        """id 가 "gemini-" 로 시작하는 그룹이 Gemini 그룹이다 — 이름이 무엇이든. 그런 그룹이 없으면 이름에
        "Gemini" 가 든 그룹. Gemini 그룹의 행이 **먼저** 온다(서버는 둘째로 줬다).
        Rivals: 이름만 봄(첫 경우에 Claude 그룹 이름의 'Gemini' 에 속음); id 만 봄; 첫 그룹을 Gemini 로 봄."""
        by_id = [{"name": "Gemini-ish partner models", "buckets": [
                     _bucket("p-5h", "5h", 0.05, "2026-11-18T05:00:00Z")]},
                 {"name": "Quota A", "buckets": [
                     _bucket("gemini-5h", "5h", 0.3, "2026-11-18T06:00:00Z")]}]
        rows = self.parse(agy_payload(by_id))
        self.assertIsInstance(rows, list)
        assert_rows(self, rows, [("gemini_group:gemini-5h", 70.0, _utc(2026, 11, 18, 6), None),
                                 ("gemini_group:p-5h", 95.0, _utc(2026, 11, 18, 5), None)], "id: ")
        self.assertEqual(_require("agy_usage_buckets")(agy_payload(by_id)),
                         {"gemini-5h": ("5h", True), "p-5h": ("5h", False)})
        by_name = [{"name": "Claude and GPT models", "buckets": [
                       _bucket("3p-5h", "5h", 0.05, "2026-11-18T05:00:00Z")]},
                   {"name": "Gemini Models", "buckets": [
                       _bucket("g-5h", "5h", 0.3, "2026-11-18T06:00:00Z")]}]
        rows = self.parse(agy_payload(by_name))
        self.assertIsInstance(rows, list)
        assert_rows(self, rows, [("gemini_group:g-5h", 70.0, _utc(2026, 11, 18, 6), None),
                                 ("gemini_group:3p-5h", 95.0, _utc(2026, 11, 18, 5), None)], "name: ")
        self.assertEqual(_require("agy_usage_buckets")(agy_payload(by_name)),
                         {"g-5h": ("5h", True), "3p-5h": ("5h", False)})

    def test_unusable_fractions_are_skipped_and_values_are_clamped(self):
        """없음·null·글자·bool·NaN 은 건너뛴다(0%/100% 를 지어내지 않는다), 범위 밖은 자른다.
        Rivals: 없음을 1.0/0.0 으로; bool 을 숫자로; 자르지 않음(125%, −50%)."""
        bad = [_bucket("gemini-x%d" % i, "5h", v, "2026-11-18T05:00:00Z")
               for i, v in enumerate((_MISSING, None, "abc", True, "NaN", [0.1]))]
        g = {"name": "Gemini Models", "buckets": bad + [
            _bucket("gemini-lo", "5h", -0.25, "2026-11-18T06:00:00Z"),
            _bucket("gemini-hi", "weekly", 1.5, "2026-11-25T06:00:00Z")]}
        assert_rows(self, self.parse(agy_payload([g])), [
            ("gemini_group:gemini-lo", 100.0, _utc(2026, 11, 18, 6), None),
            ("gemini_group:gemini-hi", 0.0, _utc(2026, 11, 25, 6), None)])

    def test_no_answer_is_none_and_garbage_never_raises(self):
        """status 가 SUCCESS 가 아니거나, 쓸 버킷이 없거나, 모양이 이상하면 None. 예외는 없다.
        Gemini 그룹이 없고 다른 그룹만 쓸 수 있으면 그 그룹 행만(0행을 지어내지 않는다).
        Rivals: status 를 안 봄; [] 반환; 0% 0행."""
        parse = _require("parse_agy_usage")
        for name, payload in (("error status", agy_payload(status="ERROR")),
                              ("no groups", agy_payload([])),
                              ("unusable", agy_payload([{"name": "Gemini Models", "buckets": [
                                  _bucket("gemini-5h", "5h", None, "2026-11-18T05:00:00Z")]}])),
                              ("None", None), ("text", "not json"), ("list", []),
                              ("no command", {"status": "SUCCESS"}),
                              ("bad data", {"status": "SUCCESS", "command": {"data": "x"}})):
            with self.subTest(payload=name):
                try:
                    got = parse(payload)
                except Exception as e:  # noqa: BLE001
                    self.fail("예외: %s" % type(e).__name__)
                self.assertIsNone(got)
        rows = self.parse(agy_payload([OTHER_GROUP]))
        assert_rows(self, rows, EXPECTED_ROWS[3:])

    def test_disabled_buckets_are_skipped_everywhere(self):
        """v3: `"disabled": true` 인 버킷은 0행 계산에서도 행에서도 빠진다. `"disabled": false` 는 보통
        버킷이다. 비활성 버킷은 Gemini 묶음의 **가운데**, 가장 낮은 남은 비율(0)로 둔다.
        모두 비활성이면 None.
        Rivals: 63d5420(비활성 0 을 100% 로 — 0행이 100% 에 고정); 0행에서만 뺌(행은 남음); 행에서만 뺌
        (0행은 100%); `disabled` 키가 있기만 하면 뺌(false 도 빠짐 — gemini-5h 가 사라져 0행 20%)."""
        gem = {"name": "Gemini Models", "buckets": [
            _bucket("gemini-weekly", "weekly", 0.8, "2026-11-25T02:13:31Z"),
            dict(_bucket("gemini-off", "5h", 0, "2026-11-18T05:00:00Z"), disabled=True),
            dict(_bucket("gemini-5h", "5h", 0.34, "2026-11-18T07:13:31Z"), disabled=False)]}
        other = {"name": "Claude and GPT models", "buckets": [
            dict(_bucket("3p-off", "weekly", 0, "2026-11-25T03:45:42Z"), disabled=True),
            _bucket("3p-5h", "5h", 0.1, "2026-11-18T08:45:42Z")]}
        assert_rows(self, self.parse(agy_payload([gem, other])), [
            ("gemini_group:gemini-5h", 66.0, _utc(2026, 11, 18, 7, 13, 31), None),
            ("gemini_group:gemini-weekly", 20.0, _utc(2026, 11, 25, 2, 13, 31), None),
            ("gemini_group:3p-5h", 90.0, _utc(2026, 11, 18, 8, 45, 42), None)])
        all_off = {"name": "Gemini Models", "buckets": [
            dict(_bucket("gemini-5h", "5h", 0.5, "2026-11-18T07:13:31Z"), disabled=True)]}
        self.assertIsNone(self.parse(agy_payload([all_off])))

    def test_parse_agy_usage_is_pure(self):
        """모듈 상태(GEMINI_GROUP_WINDOWS 를 포함한 어떤 모듈 수준 dict·list·set 도)를 바꾸지 않는다.
        Rival: 파서가 window 표나 Gemini id 목록을 모듈에 적음."""
        parse = _require("parse_agy_usage")

        def snapshot():
            return {n: repr(v) for n, v in vars(claude_pet).items()
                    if isinstance(v, (dict, list, set)) and not n.startswith("__")}

        before = snapshot()
        first = parse(agy_payload())
        changed = sorted(k for k, v in snapshot().items() if before.get(k) != v)
        self.assertEqual(changed, [], "parse_agy_usage 가 모듈 상태를 바꿨다: %r" % changed)
        self.assertEqual(parse(agy_payload()), first)


# ═════════════════════════════ 1·3. fetch_gemini_usage ═════════════════════════════


class FetchViaAgyTests(AgyCase):

    def fetch(self):
        return _require("fetch_gemini_usage")()

    def test_it_runs_exactly_agy_usage_json_without_a_shell_in_a_neutral_dir(self):
        """argv 는 정확히 `[agy, "-p", "/usage", "--output-format", "json"]`(셸 없음), timeout 은 0 초과 30
        이하, cwd 는 홈이나 임시 디렉터리. 행은 parse 결과, 상태는 성공. v4: 그 전에 agy 키체인 항목이
        있는지 확인한다(`-w` 없이) — 그 밖의 security 호출은 없다. Rivals: 63d5420(확인 없이 agy 를 띄움 —
        로그인 안 된 사용자에게 OAuth 절차를 시작); `-w` 로 비밀값을 읽어 확인; env 없음(agy 가 기본
        브라우저에 로그인 탭을 연다); env 를 통째로 갈아치움(HOME·PATH 가 없어 agy 가 설정을 못 찾는다);
        v5 의 `SSH_TTY=1`(agy 1.5.11 이 토큰 저장소를 파일로 바꿔 로그인된 사용자를 못 읽는다); 앱 환경의
        SSH_* 를 사본에 그대로 둠; 가짜 open 없음(브라우저가 열린다); 가짜 open 을 PATH 끝에 둠(진짜
        /usr/bin/open 이 먼저 잡힌다); open 이 0 아닌 코드(agy 가 실패로 본다); 폴더 0755(남이 open 을
        바꿔치기한다); os.environ 자체를 고침(앱이 띄우는 다른 프로세스까지 바뀐다); 90fd32b(키체인 + cloudcode-pa HTTP — agy 를 띄우지 않음); 셸 문자열; timeout 없음
        (멈춘 agy 가 워커를 영원히 붙듦); cwd 없음(앱의 작업 디렉터리 — 번들 안 — 에서 agy 가 돎);
        `/usage` 대신 프롬프트(모델 토큰을 씀)."""
        self.app_runs_over_ssh()
        before = dict(os.environ)
        rows = self.fetch()
        self.assertEqual(len(self.fake.calls), 1, "agy 를 정확히 한 번 띄워야 한다")
        _t, argv, kw = self.fake.calls[0]
        self.assertEqual(argv, [self.agy_path] + AGY_ARGS)
        self.assertFalse(kw.get("shell"), "셸로 띄웠다")
        # run 으로 띄웠으면 그 timeout 인자, Popen 으로 띄웠으면 구현의 상한 상수.
        timeout = kw.get("timeout", getattr(claude_pet, "GEMINI_AGY_TIMEOUT", None))
        self.assertIsInstance(timeout, (int, float), "timeout 이 없다")
        self.assertTrue(0 < timeout <= 30, "timeout %r" % timeout)
        cwd = kw.get("cwd")
        self.assertIsNotNone(cwd, "cwd 를 정하지 않았다")
        real = os.path.realpath(str(cwd))
        self.assertTrue(real == os.path.realpath(self.home)
                        or real.startswith(os.path.realpath(tempfile.gettempdir())),
                        "cwd 가 중립 디렉터리가 아니다: %r" % cwd)
        self.assert_only_existence_checks(at_least=1)
        # v5-1: SSH_* 없음, NO_COLOR=1, PATH 맨 앞에 아무것도 안 하는 open, 앱 환경 불변.
        self.assert_background_env(kw.get("env"), before)
        assert_rows(self, rows, EXPECTED_ROWS)
        self.assertEqual(self.status().get("last_error"), None)
        self.assertIs(self.status().get("auth_error"), False)

    def test_a_deleted_fake_open_is_made_again_before_the_next_run(self):
        """v5-1 추가 1: 가짜 open 폴더(또는 그 안의 open 파일)가 지워졌으면 agy 를 띄우기 **직전에** 다시
        만든다 — 없으면 PATH 의 다음 open(/usr/bin/open)으로 넘어가 브라우저가 열린다. 임시 폴더는 시스템이
        치울 수 있다.
        Rivals: 앱이 켜질 때 한 번만 만듦; 폴더 경로를 기억해 두고 있는지만 봄(폴더는 있는데 open 이 없다);
        다시 만들되 권한·내용을 대충 함(같은 단언을 다시 통과해야 한다)."""
        _require("parse_agy_usage")
        box = {"now": 1_800_000_000.0}      # 다음 주기를 기다리지 않게 앱의 시계만 대역으로
        self._patch(mock.patch.object(claude_pet, "time", _FakeTime(box)))
        before = dict(os.environ)
        self.assertTrue(self.fetch())
        first = self.fake.calls[0][2].get("env")
        self.assert_background_env(first, before)
        folder = first["PATH"].split(os.pathsep)[0]
        for n, wipe in enumerate((lambda: shutil.rmtree(folder),
                                  lambda: os.unlink(os.path.join(folder, "open"))), start=1):
            wipe()
            box["now"] += 301
            self.assertTrue(self.fetch())
            self.assertEqual(len(self.fake.calls), n + 1, "다음 주기에 agy 를 띄우지 않았다")
            # 그 실행에 준 env 의 PATH 맨 앞 폴더에, 띄운 시점에 이미 실행 가능한 open 이 있어야 한다.
            self.assert_background_env(self.fake.calls[n][2].get("env"), before)
            folder = self.fake.calls[n][2]["env"]["PATH"].split(os.pathsep)[0]

    def test_agy_is_found_on_path_or_in_dot_local_bin_otherwise_not_installed(self):
        """which 가 없으면 실행 가능한 ~/.local/bin/agy. 그것도 없거나 실행 권한이 없으면 띄우지 않고 None,
        last_error "not_installed", auth_error False. Rivals: 'agy' 를 그대로 띄움(PATH 가 짧은 GUI 앱에서
        FileNotFoundError); 실행 권한을 안 봄; 없음을 로그인 필요로 보임."""
        self.which["agy"] = None
        local = os.path.join(self.home, ".local", "bin", "agy")
        for name, make, want_spawn in (("missing", None, False), ("not executable", 0o644, False),
                                       ("executable", 0o755, True)):
            with self.subTest(case=name):
                reset_gemini_state()
                self.fake.calls.clear()
                if make is not None:
                    os.makedirs(os.path.dirname(local), exist_ok=True)
                    with open(local, "w") as f:
                        f.write("#!/bin/sh\nexit 0\n")
                    os.chmod(local, make)
                rows = self.fetch()
                if want_spawn:
                    self.assertEqual([c[1][0] for c in self.fake.calls], [local])
                    self.assertTrue(rows)
                else:
                    self.assertEqual(self.fake.calls, [])
                    self.assertIsNone(rows)
                    self.assertEqual(self.status().get("last_error"), "not_installed")
                    self.assertIs(self.status().get("auth_error"), False)

    def test_failures_are_none_with_their_own_status(self):
        """0 아닌 종료 → "agy_failed", 시간 초과 → "timeout", 깨진 JSON → "parse", SUCCESS 아님 → None 과 비어
        있지 않은 last_error. 어느 것도 auth_error 를 올리지 않는다(로그인 판정은 모양을 관측한 뒤 — 모호점).
        Rivals: 실패를 '설치 안 됨'으로; 예외를 그대로 던짐; 실패를 0% 로."""
        for mode, payload, want in (("fail", None, "agy_failed"), ("timeout", None, "timeout"),
                                    ("garbage", None, "parse"),
                                    ("ok", agy_payload(status="ERROR"), None)):
            with self.subTest(mode=mode, status=None if payload is None else payload["status"]):
                reset_gemini_state()
                if mode == "timeout":
                    self.never_exits(mode)
                else:
                    self.fake.mode = mode
                if payload is not None:
                    self.fake.payload = payload
                fetch = _require("fetch_gemini_usage")
                try:
                    rows = fetch()
                except Exception as e:  # noqa: BLE001
                    self.fail("예외: %s" % type(e).__name__)
                self.assertIsNone(rows)
                last = self.status().get("last_error")
                if want is None:
                    self.assertTrue(isinstance(last, str) and last, "상태가 비어 있다: %r" % last)
                else:
                    self.assertEqual(last, want)
                self.assertIs(self.status().get("auth_error"), False)
                self.fake.payload = agy_payload()
                self.assertEqual(self.fake.alive(), 0, "agy 프로세스가 남았다")

    def test_off_macos_nothing_is_spawned(self):
        """macOS·Windows 가 아니면 None, 프로세스 0. Rival: 플랫폼을 안 봄.
        (v7-W: Windows 는 이제 읽는다 — 그 동작은 tests/test_gemini_windows.py 가 가른다.)"""
        _require("parse_agy_usage")
        for plat in ("linux",):
            with self.subTest(platform=plat):
                with mock.patch.object(sys, "platform", plat):
                    self.assertIsNone(self.fetch())
                self.assertEqual(self.fake.calls, [])

    def test_the_claude_keychain_reader_no_longer_takes_a_gemini_item(self):
        """`_security_read_blob` 은 다시 Claude 전용이다 — Gemini 항목(item=…) 갈래가 없다.
        Rival: 90fd32b(item 인자로 agy 항목을 읽는 갈래가 남아 있음)."""
        _require("parse_agy_usage")
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "_security_read_blob")
        self.assertNotIn("item", [a.arg for a in fn.args.args + fn.args.kwonlyargs])
        self.assertNotIn("antigravity", ast.unparse(fn))


# ═════════════════════════════ v3·v4: 로그인 안 됨 ═════════════════════════════


class AgyLoginTests(AgyCase):

    def fetch(self):
        return _require("fetch_gemini_usage")()

    def test_without_the_keychain_item_agy_is_never_run(self):
        """v4: agy 키체인 항목이 없다 = 로그인 안 됨 → agy 를 **띄우지 않는다**. None, last_error "login",
        auth_error True. 확인은 `-w` 없는 존재 확인 한 번.
        Rivals: 63d5420(확인 없이 agy 를 띄움 — 그 실행이 로그인 절차를 시작한다); 확인은 하고도 띄움;
        `-w` 로 읽음; 없음을 "not_installed"·일시 실패로 보임."""
        _require("parse_agy_usage")
        self.fake.keychain = "absent"
        rows = self.fetch()
        self.assertEqual(self.fake.calls, [], "로그인 안 된 사용자에게 agy 를 띄웠다")
        self.assert_only_existence_checks(at_least=1)
        self.assertEqual(len(self.fake.security), 1)
        self.assertIsNone(rows)
        self.assertEqual(self.status().get("last_error"), "login")
        self.assertIs(self.status().get("auth_error"), True)

    def test_the_fallback_token_file_counts_as_a_login(self):
        """v5 c: 키체인 항목은 없지만(44) 파일 폴백 `~/.gemini/antigravity-cli/antigravity-oauth-token` 이
        있다(키체인을 못 쓰는 환경의 agy) → 로그인된 것으로 보고 agy 를 띄워 행을 낸다. 파일을 읽지는
        않는다(존재와 mtime 만 본다 — 내용은 여기서 빈 JSON 이다).
        Rival: 키체인만 봄(파일 저장소를 쓰는 사용자는 영영 '로그인 안 됨')."""
        _require("parse_agy_usage")
        self.fake.keychain = "absent"
        self.write_fallback(1_800_000_000)
        rows = self.fetch()
        self.assertEqual(len(self.fake.calls), 1, "폴백 파일이 있는데 agy 를 띄우지 않았다")
        assert_rows(self, rows, EXPECTED_ROWS)
        self.assertIs(self.status().get("auth_error"), False)

    def test_a_locked_keychain_is_not_asked_and_the_last_answer_stands(self):
        """`keychain_locked()` 이면 존재 확인도 하지 않고 직전 판단을 유지한다: '있음'이었으면 agy 를 계속
        띄우고, '없음'이었으면 계속 띄우지 않는다. 잠긴 채 시작했으면 security 호출 0(그때 agy 를 띄우는지는
        계약에 없다 — 보지 않는다).
        Rivals: 잠겨도 확인함(잠긴 키체인에 묻는 것이 암호 창의 기회다); 잠기면 '없음'으로 봄(로그인된
        사용자의 수치가 사라짐); 잠기면 '있음'으로 봄(로그인 안 된 사용자에게 agy 를 띄움)."""
        _require("parse_agy_usage")
        locked = {"v": True}
        self._patch(mock.patch.object(claude_pet, "keychain_locked", lambda: locked["v"]))
        clock = {"now": 1_800_000_000.0}
        self._patch(mock.patch.object(claude_pet, "time", _FakeTime(clock)))
        self.fake.clock = _FakeTime(clock)
        self.fetch()
        self.assertEqual(self.fake.security, [], "잠긴 키체인에 물었다")
        for known, spawns in (("present", 1), ("absent", 0)):
            with self.subTest(known=known):
                reset_gemini_state()
                self.fake.calls.clear()
                del self.fake.security[:]
                self.fake.keychain = known
                locked["v"] = False
                self.fetch()
                self.assertEqual(len(self.fake.calls), spawns)
                asked = len(self.fake.security)
                self.assertGreaterEqual(asked, 1)
                locked["v"] = True
                self.fake.keychain = "absent" if known == "present" else "present"   # 물으면 답이 바뀐다
                clock["now"] += 330
                rows = self.fetch()
                self.assertEqual(len(self.fake.security), asked, "잠긴 키체인에 물었다")
                self.assertEqual(len(self.fake.calls), spawns * 2,
                                 "잠긴 동안 직전 판단(%s)을 유지하지 않았다" % known)
                self.assertEqual(bool(rows), known == "present")

    def test_agy_asking_for_a_login_is_ended_at_once(self):
        """항목은 있는데 agy 가 로그인을 요구한다(refresh token 만료·취소): stdout 없이 stderr 에 로그인
        안내를 쓰고 끝나지 않는다 → **그 즉시 끝낸다**: 상한(여기서는 8초)을 기다리지 않고 돌아오고, agy
        프로세스가 남지 않고, None, last_error "login", auth_error True.
        Rivals: 63d5420(상한까지 기다리고 "timeout" — 로그인 절차가 30초 동안 열려 있다); 상한까지 기다린 뒤
        예외의 출력에서 알아냄(v3 — 판정은 맞지만 그동안 프로세스가 산다); 판정만 하고 agy 를 끝내지 않고
        돌아옴(로그인 절차가 뒤에 남는다); agy 만 끝내고 그것이 띄운 자식은 남김(그룹이 아니라 pid 하나만). 이 테스트는 **돌고 있는** 프로세스만 본다 — 끝낸 뒤 거두지 않은
        좀비는 가르지 못한다(상태를 묻는 순간 거둬진다)."""
        self.never_exits("login_wait", wait=8)
        self.app_runs_over_ssh()
        before = dict(os.environ)
        t0 = _real_time.time()
        rows = self.fetch()
        took = _real_time.time() - t0
        self.assertEqual(len(self.fake.calls), 1)
        self.assertIsNone(rows)
        self.assertEqual(self.status().get("last_error"), "login")
        self.assertIs(self.status().get("auth_error"), True)
        self.assertLess(took, 4.0, "로그인 안내가 나왔는데 agy 를 바로 끝내지 않았다(%.1f초)" % took)
        # v5 b: 프로세스 **그룹**을 끝낸다 — 대역 agy 는 이 mode 에서 같은 그룹에 자식을 하나 띄워 둔다.
        self.assertEqual(self.fake.alive(), 0, "agy 프로세스(또는 그것이 띄운 자식)가 남았다")
        # v5-1: 로그인을 요구하는 agy 가 부를 `open <url>` 은 가짜 open 에서 끝난다.
        self.assert_background_env(self.fake.calls[0][2].get("env"), before)
        self.assert_only_existence_checks()

    def test_an_immediate_authentication_required_error_is_login(self):
        """바로 실패하는 로그인 요구: 0 아닌 종료, 빈 stdout, stderr "Error: authentication required. Run
        'agy' to log in." → "login", auth_error True.
        Rival: 63d5420(stdout 이 비면 로그인 낱말을 찾지 않음 → "agy_failed")."""
        self.fake.mode = "login_exit"
        self.assertIsNone(self.fetch())
        self.assertEqual(self.status().get("last_error"), "login")
        self.assertIs(self.status().get("auth_error"), True)

    def test_a_login_wait_that_ran_out_is_login_though_its_stdout_matches_offline(self):
        """60초를 다 기다린 로그인 요구: 종료 1, stdout 은 오프라인 실패와 **같은** ERROR JSON, stderr 에
        "Authentication required … Run 'agy' interactively to log in." → "login", auth_error True.
        Rivals: stdout 의 error 문구만 보고 가름(오프라인과 구분 못 함 → 일시 실패로 보고 5분마다 로그인
        절차를 다시 시작); stdout 이 비었을 때만 stderr 를 봄."""
        self.fake.mode = "login_timeout_exit"
        self.assertIsNone(self.fetch())
        self.assertEqual(self.status().get("last_error"), "login")
        self.assertIs(self.status().get("auth_error"), True)

    def test_offline_token_refresh_failures_are_not_login(self):
        """로그인된 사용자의 오프라인 토큰 갱신 실패는 로그인 안 됨이 아니다 — 일시 실패다(v5 d: stdout 은
        ERROR JSON "authentication failed or timed out", 종료 1, stderr 에 "token refresh failed due to
        network error"): "agy_failed", 끝나지 않으면 상한까지 기다려 "timeout", 어느 쪽도 auth_error False.
        **63d5420 에서는 판정 자체는 맞다**(그때는 stderr 를 거의 안 봤다) — 로그인 판정을 넓히는 구현을
        가르는 가드다. Rivals: 낱말을 "authentication"/"auth" 로 넓힘(오프라인인 사용자에게 로그인하라고
        함); stderr 에 무엇이든 나오면 바로 끝냄."""
        _require("parse_agy_usage")
        for mode, want in (("offline_exit_a", "agy_failed"), ("offline_exit_b", "agy_failed"),
                           ("offline_wait", "timeout")):
            with self.subTest(mode=mode):
                reset_gemini_state()
                self.fake.calls.clear()
                if want == "timeout":
                    self.never_exits(mode)
                else:
                    self.fake.mode = mode
                self.assertIsNone(self.fetch())
                self.assertEqual(len(self.fake.calls), 1)
                self.assertEqual(self.status().get("last_error"), want)
                self.assertIs(self.status().get("auth_error"), False)
                self.assertEqual(self.fake.alive(), 0, "agy 프로세스가 남았다")


# ═════════════════════════════ v3: 펫 기분 ═════════════════════════════


class GeminiMoodTests(AgyCase):
    """`mood_for(stats, rows, runtime, codex_rows=…, gemini_rows=…)` — 이름 `gemini_rows` 는 이 파일이 건다
    (codex_rows 의 짝). 보이는 Gemini 의 고른 게이지 행만 센다."""

    def rt(self, **over):
        rt = {"mode": "sub", "show_claude": False, "claude_gauges": ["session", "weekly"],
              "show_codex": False, "codex_mode": "sub", "codex_gauges": ["session", "weekly"],
              "show_gemini": True, "gemini_gauges": ["session", "weekly"]}
        rt.update(over)
        return rt

    def setUp(self):
        super().setUp()
        # 직접 만든 행이 쓰는 버킷 표(조회 경로가 적는 GEMINI_BUCKETS 의 대역): g-s 는 Gemini 묶음의 세션 창.
        patcher = mock.patch.dict(claude_pet.GEMINI_BUCKETS, {"g-s": ("5h", True), "x-1": ("5h", False)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def mood(self, rt, gemini_rows, rows=None, codex_rows=None):
        try:
            return claude_pet.mood_for(None, rows, rt, codex_rows=codex_rows, gemini_rows=gemini_rows)
        except TypeError as e:
            self.fail("mood_for 가 gemini_rows 를 받지 않는다 — v3 계약 3 이 아직 구현되지 않았다 (%s)" % e)

    def test_the_headline_row_sets_the_mood_at_the_same_thresholds(self):
        """Gemini 만 보이는 사용자: 0행 90% → failed, 60% → waiting, 10% → idle. 경계는 다른 제공자와
        같다(≥85, ≥50). Rivals: 63d5420(Gemini 를 안 봄 — 늘 idle); 남은 비율로 착각(10% 에서 failed)."""
        for pct, want in ((90.0, "failed"), (85.0, "failed"), (84.0, "waiting"), (60.0, "waiting"),
                          (50.0, "waiting"), (49.0, "idle"), (10.0, "idle")):
            with self.subTest(pct=pct):
                self.assertEqual(self.mood(self.rt(), [("gemini_group:g-s", pct, None, None)]), want)

    def test_hidden_gemini_and_unchosen_gauges_do_not_move_the_pet(self):
        """숨긴 Gemini 의 95% 는 기분을 바꾸지 않는다. 고르지 않은 게이지의 행도 그렇다(0행만 골랐는데 묶음
        행이 95%). 다른 제공자와 합치면 가장 높은 것이 이긴다 — 어느 쪽이 높든.
        Rivals: 표시 설정을 안 봄; 게이지 선택을 안 봄(모든 Gemini 행을 셈); Gemini 가 있으면 Claude 행을
        버림; Gemini 를 Codex 행 자리에 넣어 codex_gauges 로 거름(전부 사라짐)."""
        rows = [("gemini_group:g-s", 20.0, None, None), ("gemini_group:x-1", 95.0, None, None)]
        self.assertEqual(self.mood(self.rt(show_gemini=False), [("gemini_group:g-s", 95.0, None, None)]), "idle")
        self.assertEqual(self.mood(self.rt(gemini_gauges=[]), [("gemini_group:g-s", 95.0, None, None)]), "idle")
        self.assertEqual(self.mood(self.rt(), rows), "idle")
        both = self.rt(show_claude=True, claude_gauges=["session"])
        session = claude_pet.t("session")     # Claude 행은 번역된 라벨로 분류된다(_label_order)
        self.assertEqual(self.mood(both, [("gemini_group:g-s", 90.0, None, None)],
                                   rows=[(session, 10.0, None, None)]), "failed")
        self.assertEqual(self.mood(both, [("gemini_group:g-s", 10.0, None, None)],
                                   rows=[(session, 60.0, None, None)]), "waiting")
        self.assertEqual(self.mood(both, None, rows=[(session, 60.0, None, None)]), "waiting")

    def test_limits_and_group_gauges_follow_the_fetched_bucket_membership(self):
        """조회 경로로 받은 행: Gemini 묶음 버킷 5%, 나머지 묶음 버킷 95%. "limits" 만 고르면 idle, "group"
        만 고르면 failed, "gemini" 만 고르면 idle(0행 5%).
        Rivals: limits/group 을 가르지 않고 묶음 행을 다 셈; 필과 다른 분류(id 접두사)를 씀."""
        gem = {"name": "Gemini Models", "buckets": [_bucket("g-1", "5h", 0.95, "2026-11-18T07:00:00Z")]}
        other = {"name": "Claude and GPT models",
                 "buckets": [_bucket("p-1", "5h", 0.05, "2026-11-18T07:00:00Z")]}
        self.fake.payload = agy_payload([other, gem])
        rows = claude_pet.fetch_gemini_usage()
        self.assertIsInstance(rows, list)
        self.assertEqual(self.mood(self.rt(gemini_gauges=["session"]), rows), "idle")
        self.assertEqual(self.mood(self.rt(gemini_gauges=["weekly"]), rows), "idle")
        self.assertEqual(self.mood(self.rt(gemini_gauges=["group"]), rows), "failed")
        self.assertEqual(self.mood(self.rt(gemini_gauges=["gemini"]), rows), "idle")

    def test_the_app_passes_its_gemini_rows_to_mood_for(self):
        """run_gui 의 current_mood 가 mood_for 에 `gemini_rows=` 로 state 의 Gemini 행을 넘긴다.
        Rival: mood_for 만 고치고 앱은 넘기지 않음(펫은 그대로 idle)."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        gui = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_gui")
        fn = [n for n in ast.walk(gui) if isinstance(n, ast.FunctionDef) and n.name == "current_mood"]
        self.assertEqual(len(fn), 1)
        calls = [c for c in ast.walk(fn[0]) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Name) and c.func.id == "mood_for"]
        self.assertTrue(calls, "current_mood 가 mood_for 를 부르지 않는다")
        for call in calls:
            kw = {k.arg: k.value for k in call.keywords}
            self.assertIn("gemini_rows", kw, "current_mood 가 Gemini 행을 넘기지 않는다")
            consts = {n.value for n in ast.walk(kw["gemini_rows"]) if isinstance(n, ast.Constant)}
            self.assertIn("gemini", consts, 'gemini_rows 가 state["gemini"] 가 아니다')


if __name__ == "__main__":
    unittest.main()
