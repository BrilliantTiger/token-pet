"""Gemini — agy 를 얼마나 자주, 어느 경로에서 띄우나(TOK-44 계약 v2 의 4). Verifier 작성, 구현 전.

tests/test_gemini_keychain_quiet.py(키체인 조용히, M1·리뷰 2차)를 대신한다 — 계약 v2 에서 앱은 agy 키체인
항목을 읽지 않으므로 그 게이트들은 대상이 사라졌다. 남는 위험은 프로세스다: agy 는 한 번에 약 4.9초
걸리는 CLI 이고(관측, 한 기기), 그것을 30초 새로고침마다 띄우거나, 숨긴 사용자에게 띄우거나, 멈춘 agy 가
Claude/Codex 를 붙들면 안 된다.

계약(Coordinator): Claude/Codex 경로 밖에서; 자동으로는 300초에 한 번을 넘지 않게; 사용자가 누르면 바로
(단 60초 하한); Gemini 를 숨기면 절대 띄우지 않음; 멈춘 agy 가 Claude/Codex 를 늦추지 않음.

'사용자가 누름'은 앱이 더블클릭 새로고침과 필 클릭에서 부르는 바로 그 함수 `allow_keychain_prompt()` 로 흉내
낸다(90fd32b 에서도 그 함수가 Gemini 캐시 시각을 0 으로 돌린다). 구현이 다른 신호를 쓰면 이 헬퍼(user_click)를
같이 고쳐야 한다 — 보고서의 모호점에 적었다.
"""

import os
import sys
import time as _real_time
import unittest
from datetime import datetime as _real_datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_gemini_usage import (AgyCase, _require, app_hook, claude_pet,  # noqa: E402
                               refresh_worker, wait_for)

T0 = 1_800_000_000.0
STEP = 30.0


class _Clock:
    def __init__(self, now):
        self.now = float(now)

    def time(self):
        return self.now

    def __getattr__(self, name):
        return getattr(_real_time, name)


class _ClockCase(AgyCase):

    def setUp(self):
        self.clock = _Clock(T0)
        super().setUp()
        clock = self.clock

        class _DT(_real_datetime):
            @classmethod
            def now(cls, tz=None):
                return _real_datetime.fromtimestamp(clock.time(), tz)

        self._patch(mock.patch.object(claude_pet, "time", self.clock))
        self._patch(mock.patch.object(claude_pet, "datetime", _DT))
        saved = dict(claude_pet.RUNTIME)
        self.addCleanup(lambda: (claude_pet.RUNTIME.clear(), claude_pet.RUNTIME.update(saved)))
        claude_pet.RUNTIME.update({"show_gemini": True, "gemini_gauges": ["gemini"]})

    def user_click(self):
        claude_pet.allow_keychain_prompt()

    def run_until(self, end, step=STEP):
        out = []
        while self.clock.time() <= end:
            out.append((self.clock.time(), claude_pet.fetch_gemini_usage()))
            self.clock.now += step
        return out

    def spawns(self):
        return [t for t, _argv, _kw in self.fake.calls]


class AutomaticCadenceTests(_ClockCase):

    def test_agy_runs_at_most_once_per_five_minutes_on_its_own(self):
        """30초마다 조회해도 한 시간에 agy 는 13번 이하(300초에 한 번 + 시작), 두 실행 사이 ≥ 300초, 행은
        그 사이 내내 이어진다(캐시). Rivals: 새로고침마다(120번); 180초 캐시(20번); 실패 캐시 60초를 성공에도."""
        _require("parse_agy_usage")
        out = self.run_until(T0 + 3600)
        times = self.spawns()
        self.assertGreaterEqual(len(times), 1, "agy 를 한 번도 띄우지 않았다")
        self.assertLessEqual(len(times), 13, "한 시간에 agy %d번" % len(times))
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertTrue(all(g >= 300 for g in gaps), "실행 간격: %r" % gaps)
        self.assertTrue(all(rows for _t, rows in out), "캐시 사이에 행이 비었다")

    def test_a_click_runs_agy_now_but_not_twice_within_a_minute(self):
        """사용자가 누르면 그 조회에서 바로 띄운다 — 단 마지막 실행 60초 안이면 아니다. 한 번의 클릭은 한 번만
        쓴다: 그 뒤로는 다시 300초 규칙이다.
        Rivals: 클릭을 무시(최대 5분 옛 값); 클릭마다 띄움(연타 = agy 연타); 클릭 깃발이 남아 그 뒤 조회마다
        (또는 60초마다) 띄움."""
        _require("parse_agy_usage")
        claude_pet.fetch_gemini_usage()
        self.assertEqual(len(self.spawns()), 1)
        self.clock.now = T0 + 30
        self.user_click()
        claude_pet.fetch_gemini_usage()
        self.assertEqual(len(self.spawns()), 1, "마지막 실행 30초 뒤의 클릭에 agy 를 또 띄웠다")
        self.clock.now = T0 + 90
        self.user_click()
        claude_pet.fetch_gemini_usage()
        self.assertEqual(self.spawns(), [T0, T0 + 90], "마지막 실행 90초 뒤의 클릭에 바로 띄우지 않았다")
        for dt in (120, 160, 290, 380):
            self.clock.now = T0 + dt
            claude_pet.fetch_gemini_usage()
            self.assertEqual(len(self.spawns()), 2,
                             "클릭 없이 마지막 실행 %d초 만에 다시 띄웠다" % (dt - 90))
        while self.clock.now < T0 + 90 + 900:      # 자동 갱신은 이어진다(상한은 계약에 없다 — 넉넉히 15분)
            self.clock.now += STEP
            claude_pet.fetch_gemini_usage()
        self.assertGreaterEqual(len(self.spawns()), 3, "클릭 뒤로 자동 갱신이 멈췄다")


class RefreshPathTests(AgyCase):
    """run_gui 의 새로고침 워커(refresh_)를 진짜 스레드로 돌린다(실시간, 몇 초)."""

    def setUp(self):
        super().setUp()
        saved = dict(claude_pet.RUNTIME)
        self.addCleanup(lambda: (claude_pet.RUNTIME.clear(), claude_pet.RUNTIME.update(saved)))
        claude_pet.RUNTIME.update({"mode": "sub", "show_claude": True,
                                   "claude_gauges": ["session", "weekly"], "show_codex": True,
                                   "codex_mode": "sub", "codex_gauges": ["session", "weekly"],
                                   "gemini_gauges": ["gemini"]})

    def drive(self, show_gemini):
        claude_pet.RUNTIME["show_gemini"] = show_gemini
        state = {"oauth": None, "codex": None, "gemini": None, "stats": None,
                 "refresh_generation": 0, "repaint": False}
        claude = [("session", 10.0, None, None)]
        codex = [("codex_weekly", 20.0, None, None)]
        refresh_worker(self, state, claude, codex)(None, None)
        return state, claude, codex

    def test_hidden_gemini_spawns_nothing_and_shown_gemini_is_fetched(self):
        """숨기면 새로고침이 끝나도 agy 0번(security 도 0번). 보이면 같은 새로고침이 agy 를 띄우고
        state["gemini"] 에 행을 넣고, 앱의 훅이 그 행으로 Gemini 구간을 만든다.
        Rivals: 표시 설정과 상관없이 띄움; 90fd32b(키체인·HTTP — agy 를 안 띄움)."""
        _require("parse_agy_usage")
        state, claude, _codex = self.drive(show_gemini=False)
        self.assertTrue(wait_for(lambda: state["oauth"] == claude, 3.0))
        _real_time.sleep(0.3)
        self.assertEqual(self.fake.calls, [], "숨긴 Gemini 때문에 agy 를 띄웠다")
        self.assertEqual(self.fake.security, [])
        state, _claude, _codex = self.drive(show_gemini=True)
        self.assertTrue(wait_for(lambda: bool(state.get("gemini")), 5.0), "Gemini 행이 안 들어왔다")
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(state["gemini"][0][0], "gemini")
        lang = claude_pet.L.get("lang")
        self.addCleanup(lambda: claude_pet.L.__setitem__("lang", lang))
        claude_pet.L["lang"] = "en"
        seg = app_hook(self, state)()
        self.assertIsNotNone(seg)
        self.assertEqual(seg[0], "exact")
        self.assertEqual(seg[1][0][0], "Gemini")
        self.assertAlmostEqual(seg[1][0][1], 66.0)

    def test_a_hung_agy_does_not_hold_back_claude_and_codex(self):
        """agy 가 답하지 않는 동안에도 Claude/Codex 행은 3초 안에 state 에 들어간다. agy 가 풀리면 Gemini 행도
        들어온다. Rivals: agy 를 같은 패스에서 기다린 뒤 commit(최대 30초 동안 Claude/Codex 가 옛 값)."""
        _require("parse_agy_usage")
        self.fake.mode = "hang"
        self.addCleanup(self.fake.hang.set)
        state, claude, codex = self.drive(show_gemini=True)
        self.assertTrue(wait_for(lambda: state["oauth"] == claude and state["codex"] == codex, 3.0),
                        "agy 가 멈춘 동안 Claude/Codex 행이 3초 안에 들어오지 않았다")
        self.assertTrue(wait_for(lambda: bool(self.fake.calls), 3.0), "agy 를 띄우지도 않았다")
        self.fake.hang.set()
        self.assertTrue(wait_for(lambda: bool(state.get("gemini")), 5.0),
                        "agy 가 풀린 뒤에도 Gemini 행이 들어오지 않았다")


if __name__ == "__main__":
    unittest.main()
