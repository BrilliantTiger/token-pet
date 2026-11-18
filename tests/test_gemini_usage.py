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

이 파일은 하네스도 겸한다 — test_gemini_agy_cadence.py 와 test_gemini_pill.py 가 `AgyFake`, `agy_payload`,
`refresh_worker`, `wait_for`, `app_hook` 를 가져다 쓴다. 진짜 agy·키체인·네트워크는 건드리지 않는다:
subprocess.run 은 기록기, Popen·os.system 은 막힘, HOME 은 임시 디렉터리, `shutil.which("agy")` 는 대역.
subprocess 는 `subprocess.run` 으로 부른다(코드베이스의 다른 CLI 호출 — `claude -p /usage` — 과 같다).
"""

import ast
import copy
import json
import math
import os
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


EXPECTED_ROWS = [
    ("gemini", 66.0, _utc(2026, 11, 18, 7, 13, 31), None),
    ("gemini_group:gemini-weekly", 20.0, _utc(2026, 11, 25, 2, 13, 31), None),
    ("gemini_group:gemini-5h", 66.0, _utc(2026, 11, 18, 7, 13, 31), None),
    ("gemini_group:gemini-monthly", 40.0, _utc(2026, 12, 1), None),
    ("gemini_group:3p-weekly", 10.0, _utc(2026, 11, 25, 3, 45, 42), None),
    ("gemini_group:3p-5h", 90.0, _utc(2026, 11, 18, 8, 45, 42), None),
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

class AgyFake:
    """subprocess.run 의 대역. agy 를 띄우면 기록하고 mode 대로 답한다. 아무것도 실행하지 않는다.
    mode: ok | fail | timeout | garbage | hang. hang 은 Event 를 기다린다(run 의 timeout 을 지킨다)."""

    def __init__(self, clock=None):
        self.clock = clock or _real_time
        self.payload = agy_payload()
        self.mode = "ok"
        self.calls = []          # (시각, argv, kwargs)
        self.security = []
        self.other = []
        self.blocked = []
        self.hang = threading.Event()

    def agy_calls(self):
        return [c for c in self.calls]

    def run(self, argv, *a, **k):
        if isinstance(argv, (str, bytes)):
            self.other.append(("shell-string", str(argv)[:40]))
            raise AssertionError("문자열 명령 — 셸 없이 argv 목록으로 띄워야 한다")
        argv = [str(x) for x in argv]
        base = os.path.basename(argv[0]) if argv else ""
        text = bool(k.get("text") or k.get("universal_newlines") or k.get("encoding"))
        conv = (lambda s: s) if text else (lambda s: s.encode())
        if base == "security":
            self.security.append(argv)
            res = subprocess.CompletedProcess(argv, 44, conv(""), conv(""))
        elif base == "agy":
            self.calls.append((self.clock.time(), argv, dict(k)))
            if self.mode == "timeout":
                raise subprocess.TimeoutExpired(argv, k.get("timeout") or 30)
            if self.mode == "hang":
                if not self.hang.wait(k.get("timeout") or 60):
                    raise subprocess.TimeoutExpired(argv, k.get("timeout") or 60)
            if self.mode == "fail":
                res = subprocess.CompletedProcess(argv, 1, conv(""), conv("synthetic agy failure\n"))
            elif self.mode == "garbage":
                res = subprocess.CompletedProcess(argv, 0, conv("{not json"), conv(""))
            else:
                body = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
                res = subprocess.CompletedProcess(argv, 0, conv(body + "\n"), conv(""))
        else:
            self.other.append(argv[:2])
            res = subprocess.CompletedProcess(argv, 1, conv(""), conv(""))
        if k.get("check") and res.returncode:
            raise subprocess.CalledProcessError(res.returncode, argv, res.stdout, res.stderr)
        return res

    def popen(self, *a, **k):
        self.blocked.append("Popen")
        raise OSError("Popen 은 막혀 있다 — subprocess.run 을 쓴다")

    def system(self, *a, **k):
        self.blocked.append("os.system")
        return 1


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

    clock = None

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="claudepet-agy-")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.agy_path = os.path.join(self.home, "fakebin", "agy")
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home)
        env.pop("CLAUDE_PET_DEBUG", None)
        self._patch(mock.patch.dict(os.environ, env, clear=True))
        self.fake = AgyFake(self.clock)
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
        """0행 = Gemini 그룹에서 가장 낮은 남은 비율(gemini-5h 0.34 → 66%), 그 버킷의 리셋. 이어 모든 그룹의
        모든 버킷, 서버 순서. dict 와 JSON 문자열이 같은 답.
        Rivals(0행): 첫 버킷(20%); 마지막(40%); 최대(20%); Claude·GPT 그룹까지 섞음(3p-5h → 90%); 남은
        비율 그대로(34%); ×100 누락. Rivals(나머지): Gemini 그룹만; id 정렬; 버킷 이름을 라벨로;
        숫자 문자열("0.6") 거부."""
        assert_rows(self, self.parse(agy_payload()), EXPECTED_ROWS, "dict: ")
        assert_rows(self, self.parse(json.dumps(agy_payload())), EXPECTED_ROWS, "JSON: ")

    def test_a_lowest_fraction_tie_takes_the_earliest_reset(self):
        """동률 셋 중 가장 이른 리셋을 가운데에(§3). Rivals: first-wins(11:00); last-wins(10:00);
        비율 무시하고 가장 이른 리셋(08:00 — 0.5 짜리)."""
        g = {"name": "Gemini Models", "buckets": [
            _bucket("gemini-a", "5h", 0.2, "2026-11-18T11:00:00Z"),
            _bucket("gemini-w", "weekly", 0.5, "2026-11-18T08:00:00Z"),
            _bucket("gemini-b", "5h", 0.2, "2026-11-18T09:00:00Z"),
            _bucket("gemini-c", "5h", 0.2, "2026-11-18T10:00:00Z")]}
        rows = self.parse(agy_payload([g]))
        self.assertIsInstance(rows, list)
        assert_rows(self, rows[:1], [("gemini", 80.0, _utc(2026, 11, 18, 9), None)])

    def test_the_gemini_group_is_found_by_bucket_ids_then_by_name(self):
        """id 가 "gemini-" 로 시작하는 그룹이 Gemini 그룹이다 — 이름이 무엇이든. 그런 그룹이 없으면 이름에
        "Gemini" 가 든 그룹. Rivals: 이름만 봄(첫 경우에 Claude 그룹 이름의 'Gemini' 에 속음); id 만 봄(둘째
        경우 0행 없음); 첫 그룹을 Gemini 로 봄."""
        by_id = [{"name": "Gemini-ish partner models", "buckets": [
                     _bucket("p-5h", "5h", 0.05, "2026-11-18T05:00:00Z")]},
                 {"name": "Quota A", "buckets": [
                     _bucket("gemini-5h", "5h", 0.3, "2026-11-18T06:00:00Z")]}]
        rows = self.parse(agy_payload(by_id))
        self.assertIsInstance(rows, list)
        assert_rows(self, rows[:1], [("gemini", 70.0, _utc(2026, 11, 18, 6), None)], "id: ")
        by_name = [{"name": "Claude and GPT models", "buckets": [
                       _bucket("3p-5h", "5h", 0.05, "2026-11-18T05:00:00Z")]},
                   {"name": "Gemini Models", "buckets": [
                       _bucket("g-5h", "5h", 0.3, "2026-11-18T06:00:00Z")]}]
        rows = self.parse(agy_payload(by_name))
        self.assertIsInstance(rows, list)
        assert_rows(self, rows[:1], [("gemini", 70.0, _utc(2026, 11, 18, 6), None)], "name: ")

    def test_unusable_fractions_are_skipped_and_values_are_clamped(self):
        """없음·null·글자·bool·NaN 은 건너뛴다(0%/100% 를 지어내지 않는다), 범위 밖은 자른다.
        Rivals: 없음을 1.0/0.0 으로; bool 을 숫자로; 자르지 않음(125%, −50%)."""
        bad = [_bucket("gemini-x%d" % i, "5h", v, "2026-11-18T05:00:00Z")
               for i, v in enumerate((_MISSING, None, "abc", True, "NaN", [0.1]))]
        g = {"name": "Gemini Models", "buckets": bad + [
            _bucket("gemini-lo", "5h", -0.25, "2026-11-18T06:00:00Z"),
            _bucket("gemini-hi", "weekly", 1.5, "2026-11-25T06:00:00Z")]}
        assert_rows(self, self.parse(agy_payload([g])), [
            ("gemini", 100.0, _utc(2026, 11, 18, 6), None),
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
        assert_rows(self, rows, EXPECTED_ROWS[4:])

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
        이하, cwd 는 홈이나 임시 디렉터리. 행은 parse 결과, 상태는 성공. Gemini 를 위해 security 를 부르지
        않는다. Rivals: 90fd32b(키체인 + cloudcode-pa HTTP — agy 를 띄우지 않음); 셸 문자열; timeout 없음
        (멈춘 agy 가 워커를 영원히 붙듦); cwd 없음(앱의 작업 디렉터리 — 번들 안 — 에서 agy 가 돎);
        `/usage` 대신 프롬프트(모델 토큰을 씀)."""
        rows = self.fetch()
        self.assertEqual(len(self.fake.calls), 1, "agy 를 정확히 한 번 띄워야 한다")
        _t, argv, kw = self.fake.calls[0]
        self.assertEqual(argv, [self.agy_path] + AGY_ARGS)
        self.assertFalse(kw.get("shell"), "셸로 띄웠다")
        timeout = kw.get("timeout")
        self.assertIsInstance(timeout, (int, float), "timeout 이 없다")
        self.assertTrue(0 < timeout <= 30, "timeout %r" % timeout)
        cwd = kw.get("cwd")
        self.assertIsNotNone(cwd, "cwd 를 정하지 않았다")
        real = os.path.realpath(str(cwd))
        self.assertTrue(real == os.path.realpath(self.home)
                        or real.startswith(os.path.realpath(tempfile.gettempdir())),
                        "cwd 가 중립 디렉터리가 아니다: %r" % cwd)
        self.assertEqual(self.fake.security, [], "Gemini 를 위해 키체인을 읽었다")
        assert_rows(self, rows, EXPECTED_ROWS)
        self.assertEqual(self.status().get("last_error"), None)
        self.assertIs(self.status().get("auth_error"), False)

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

    def test_off_macos_nothing_is_spawned(self):
        """macOS 가 아니면 None, 프로세스 0. Rival: 플랫폼을 안 봄."""
        _require("parse_agy_usage")
        for plat in ("win32", "linux"):
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


if __name__ == "__main__":
    unittest.main()
