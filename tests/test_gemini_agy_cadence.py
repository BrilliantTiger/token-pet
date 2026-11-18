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
                               refresh_worker, reset_gemini_state, wait_for)

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
        # v4: 존재 확인도 자동으로는 300초에 한 번을 넘지 않고, 비밀값을 열지 않는다.
        self.assert_only_existence_checks(at_least=1)
        self.assertLessEqual(len(self.fake.security), 13,
                             "한 시간에 키체인 확인 %d번" % len(self.fake.security))

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


class KeychainCheckCadenceTests(_ClockCase):
    """v4: 로그인 여부는 agy 키체인 항목이 있는지로 본다. 없으면 agy 를 띄우지 않고, 그 확인도 자동으로는
    300초에 한 번, 사용자가 누르면 바로."""

    def status(self):
        return dict(claude_pet.GEMINI_STATUS)

    def test_logged_out_for_an_hour_runs_no_agy_and_checks_every_five_minutes_at_most(self):
        """항목이 없는 채로 한 시간, 30초마다 조회: agy 0번, 존재 확인은 13번 이하·간격 ≥ 300초, 내내 None,
        상태는 "login"/auth_error True.
        Rivals: 63d5420(확인 없이 agy 를 300초마다 — 로그인 절차를 13번 시작); 새로고침마다 확인(120번);
        처음 한 번만 확인하고 영영 안 봄(아래 테스트)."""
        _require("parse_agy_usage")
        self.fake.keychain = "absent"
        out = self.run_until(T0 + 3600)
        self.assertEqual(self.spawns(), [], "로그인 안 된 사용자에게 agy 를 띄웠다")
        self.assert_only_existence_checks(at_least=1)
        checks = self.fake.security_at
        self.assertLessEqual(len(checks), 13, "한 시간에 키체인 확인 %d번" % len(checks))
        gaps = [b - a for a, b in zip(checks, checks[1:])]
        self.assertTrue(all(g >= 300 for g in gaps), "확인 간격: %r" % gaps)
        self.assertTrue(all(rows is None for _t, rows in out))
        self.assertEqual(self.status().get("last_error"), "login")
        self.assertIs(self.status().get("auth_error"), True)

    def test_once_the_item_appears_the_next_check_reads_usage_in_the_same_pass(self):
        """사용자가 터미널에서 로그인했다(항목이 생김): 다음 자동 확인(300초 안쪽 주기)이 그것을 보고 **그
        조회에서 바로** agy 를 띄워 행을 낸다. 상태도 내려간다.
        Rivals: 처음 한 번만 확인(로그인해도 영영 안 보임); 항목을 본 뒤 다음 주기까지 또 기다림(5분 더);
        '없음'을 본 뒤로 자동 실행을 멈춤(agy 가 로그인을 요구한 경우와 섞음)."""
        _require("parse_agy_usage")
        self.fake.keychain = "absent"
        self.assertIsNone(claude_pet.fetch_gemini_usage())
        self.fake.keychain = "present"
        out = self.run_until(T0 + 330)
        self.assertEqual(len(self.spawns()), 1, "항목이 생겼는데 agy 를 띄우지 않았다")
        when = self.spawns()[0]
        got = dict(out)
        self.assertTrue(got[when], "항목을 본 그 조회에서 행을 내지 않았다")
        self.assertEqual(self.status().get("last_error"), None)
        self.assertIs(self.status().get("auth_error"), False)
        self.assertEqual(self.fake.security_at[-1], when, "확인과 실행이 같은 조회가 아니다")

    def test_once_the_item_is_gone_the_rows_go_at_once(self):
        """행을 받던 사용자의 항목이 사라졌다(로그아웃): 다음 주기에 agy 를 띄우지 않고 행을 바로 지운다.
        Rivals: 처음 한 번만 확인(로그아웃한 사용자에게 agy 를 띄움); 일시 실패처럼 옛 행을 유지."""
        _require("parse_agy_usage")
        self.assertTrue(claude_pet.fetch_gemini_usage())
        self.assertEqual(len(self.spawns()), 1)
        self.fake.keychain = "absent"
        self.clock.now = T0 + 330
        self.assertIsNone(claude_pet.fetch_gemini_usage(), "로그아웃했는데 옛 행을 보였다")
        self.assertEqual(len(self.spawns()), 1, "항목이 없는데 agy 를 띄웠다")
        self.assertEqual(self.status().get("last_error"), "login")
        self.assertIs(self.status().get("auth_error"), True)
        self.clock.now = T0 + 360
        self.assertIsNone(claude_pet.fetch_gemini_usage(), "캐시에 옛 행이 남았다")

    def test_a_click_checks_the_keychain_right_away(self):
        """항목이 없는 사용자가 로그인하고 펫을 눌렀다: 마지막 확인 30초 뒤여도 바로 다시 확인하고, 항목이
        있으면 그 조회에서 agy 를 띄운다. 누르지 않으면 300초 안에는 다시 확인하지 않는다.
        Rivals: 클릭을 무시(로그인하고도 5분을 기다림); 클릭에는 확인만 하고 실행은 다음 주기로 미룸."""
        _require("parse_agy_usage")
        self.fake.keychain = "absent"
        self.assertIsNone(claude_pet.fetch_gemini_usage())
        self.assertEqual(len(self.fake.security), 1)
        self.clock.now = T0 + 30
        self.assertIsNone(claude_pet.fetch_gemini_usage())
        self.assertEqual(len(self.fake.security), 1, "누르지 않았는데 30초 만에 다시 확인했다")
        self.fake.keychain = "present"
        self.user_click()
        rows = claude_pet.fetch_gemini_usage()
        self.assertEqual(len(self.fake.security), 2, "클릭에 바로 확인하지 않았다")
        self.assertEqual(self.spawns(), [T0 + 30], "클릭으로 항목을 보고도 agy 를 바로 띄우지 않았다")
        self.assertTrue(rows)


class LoginStopsTheRunsTests(_ClockCase):
    """v3·v4: 키체인 항목은 있는데 agy 가 로그인을 요구한다(refresh token 만료·취소). 그 실행이 로그인
    절차(브라우저 주소 + 60초 대기)를 시작한 것이다. 그것을 자동으로 다시 시작하지 않는다 — "login" 이 한
    번 나오면 자동 실행은 멈추고, 사용자가 눌러야 다시 띄운다. (이 클래스에서 키체인 항목은 내내 있다.)"""

    def status(self):
        return dict(claude_pet.GEMINI_STATUS)

    def test_login_drops_the_last_rows_at_once(self):
        """행을 받아 둔 사용자가 로그아웃했다 → 다음 실행에서 행이 바로 사라지고(일시 실패의 유지 없음)
        auth_error 가 오른다. 그 뒤의 조회(캐시)도 None 이다. 두 미로그인 모양 모두.
        Rivals: 63d5420(끝나지 않는 쪽은 "timeout", 바로 실패하는 쪽은 "agy_failed" — 둘 다 일시 실패로
        보고 옛 행을 30분까지 보임); 이번 답만 None 이고 캐시에는 옛 행이 남음."""
        _require("parse_agy_usage")
        for mode in ("login_wait", "login_exit"):
            with self.subTest(mode=mode):
                reset_gemini_state()
                self.fake.calls.clear()
                self.clock.now = T0
                self.fake.mode = "ok"
                self.assertTrue(claude_pet.fetch_gemini_usage(), "먼저 행을 받아야 한다")
                self.clock.now = T0 + 330
                if mode == "login_wait":
                    self.never_exits(mode)
                else:
                    self.fake.mode = mode
                self.assertIsNone(claude_pet.fetch_gemini_usage(), "로그아웃했는데 옛 행을 보였다")
                self.assertEqual(len(self.spawns()), 2)
                self.assertEqual(self.status().get("last_error"), "login")
                self.assertIs(self.status().get("auth_error"), True)
                self.clock.now = T0 + 360
                self.assertIsNone(claude_pet.fetch_gemini_usage(), "캐시에 옛 행이 남았다")

    def test_after_login_nothing_runs_while_the_keychain_marker_stands(self):
        """"login" 뒤 한 시간 동안 30초마다 조회해도 — 키체인 항목의 수정 시각(mdat)이 그대로인 한 — agy 는
        다시 뜨지 않는다. 그동안 상태는 "login" 그대로이고, 존재 확인은 계속 돈다(300초에 한 번 이하).
        Rivals: 63d5420(300초마다 다시 띄움 — 한 시간에 13번 로그인 절차를 시작); 멈추면서 상태를 지움;
        멈춘 뒤로 확인도 그만둠(아래 테스트의 자동 복구가 불가능해진다)."""
        _require("parse_agy_usage")
        self.never_exits("login_wait")
        out = self.run_until(T0 + 3600)
        self.assertEqual(self.spawns(), [T0], "지문이 그대로인데 로그인 안 된 agy 를 다시 띄웠다")
        self.assertTrue(all(rows is None for _t, rows in out))
        self.assertEqual(self.status().get("last_error"), "login")
        self.assertIs(self.status().get("auth_error"), True)
        self.assert_only_existence_checks(at_least=1)
        checks = self.fake.security_at
        self.assertGreaterEqual(len(checks), 6, "멈춘 뒤 키체인 확인도 멈췄다(한 시간에 %d번)" % len(checks))
        self.assertLessEqual(len(checks), 13)
        self.assertTrue(all(b - a >= 300 for a, b in zip(checks, checks[1:])))

    def test_a_changed_marker_resumes_by_itself_without_a_click(self):
        """v5 c: 사용자가 로그인을 마쳐 agy 가 키체인을 다시 썼다(mdat 가 바뀜) → 클릭 없이, 다음 확인 주기
        (330초 안)에 agy 를 다시 띄워 행을 내고 상태가 내려가고 자동 갱신이 이어진다. 폴백 파일이 생기거나
        그 mtime 이 바뀌는 것도 같은 신호다. 바뀐 뒤에도 agy 가 로그인을 요구하면 새 지문을 기억하고 다시
        멈춘다.
        Rivals: 클릭해야만 복구(v4); 지문에 mdat 만 넣음(파일 저장소 사용자는 복구 안 됨); 지문에 존재
        여부만 넣음(로그아웃 뒤에도 항목은 남으므로 영영 같다); 바뀐 지문을 기억하지 않아 그 뒤로 매 주기
        다시 띄움."""
        _require("parse_agy_usage")
        for name, change in (("mdat", lambda: setattr(self.fake, "mdat", "20261118071500Z")),
                             ("fallback file appears", lambda: self.write_fallback(1_800_000_100)),
                             ("fallback mtime", lambda: self.write_fallback(1_800_000_200))):
            with self.subTest(change=name):
                reset_gemini_state()
                self.fake.calls.clear()
                self.clock.now = T0
                self.never_exits("login_wait")
                self.assertIsNone(claude_pet.fetch_gemini_usage())
                self.clock.now = T0 + STEP
                self.run_until(T0 + 660)
                self.assertEqual(self.spawns(), [T0])
                # 지문은 바뀌었는데 여전히 로그인 요구 → 한 번 더 띄우고, 새 지문으로 다시 멈춘다.
                change()
                t1 = self.clock.now
                self.run_until(t1 + 1200)
                self.assertEqual(len(self.spawns()), 2, "바뀐 지문에 한 번만 다시 띄워야 한다")
                self.assertLessEqual(self.spawns()[1] - t1, 330, "지문이 바뀌었는데 다음 주기에 읽지 않았다")
                self.assertEqual(self.status().get("last_error"), "login")
        # 이번에는 로그인이 실제로 됐다.
        self.fake.mode = "ok"
        self.fake.mdat = "20261118080000Z"
        t2 = self.clock.now
        out = self.run_until(t2 + 330)
        self.assertEqual(len(self.spawns()), 3, "로그인을 마쳤는데(지문 바뀜) 클릭 없이 복구되지 않았다")
        self.assertTrue(dict(out)[self.spawns()[2]], "복구한 조회에서 행을 내지 않았다")
        self.assertEqual(self.status().get("last_error"), None)
        self.assertIs(self.status().get("auth_error"), False)
        self.run_until(self.clock.now + 900)
        self.assertGreaterEqual(len(self.spawns()), 5, "복구 뒤 자동 갱신이 이어지지 않았다")

    def test_a_click_retries_at_once_even_when_the_marker_stands(self):
        """멈춘 상태에서 사용자가 누르면(지문이 그대로여도) 그 조회에서 바로 띄운다. 여전히 로그인 요구면
        다시 멈추고, 로그인됐으면 행이 오고 자동 갱신이 돌아온다.
        Rivals: 멈춘 뒤 클릭도 무시; 클릭 뒤에도 영영 멈춤."""
        _require("parse_agy_usage")
        self.never_exits("login_wait")
        self.assertIsNone(claude_pet.fetch_gemini_usage())
        self.clock.now = t1 = T0 + 600
        self.user_click()
        self.assertIsNone(claude_pet.fetch_gemini_usage())
        self.assertEqual(self.spawns(), [T0, t1], "멈춘 뒤의 클릭에 바로 띄우지 않았다")
        self.clock.now = t1 + STEP
        self.run_until(t1 + 1200)
        self.assertEqual(len(self.spawns()), 2, "여전히 로그인 요구인데 자동 실행이 다시 돌았다")
        t2 = self.clock.now
        self.fake.mode = "ok"
        self.user_click()
        rows = claude_pet.fetch_gemini_usage()
        self.assertEqual(self.spawns(), [T0, t1, t2])
        self.assertTrue(rows, "로그인한 뒤의 클릭에 행이 오지 않았다")
        self.assertIs(self.status().get("auth_error"), False)
        self.clock.now = t2 + STEP
        self.run_until(t2 + 900)
        self.assertGreaterEqual(len(self.spawns()), 4, "로그인한 뒤 자동 갱신이 돌아오지 않았다")


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
        state = {"oauth": None, "codex": None, "gemini": None, "gemini_onboard": None,
                 "stats": None, "refresh_generation": 0, "repaint": False}
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

    def test_a_logged_out_user_gets_the_menu_flag_and_no_agy(self):
        """v4: 보이는 Gemini, 키체인 항목 없음 → 새로고침 뒤 state["gemini_onboard"] 가 "login"(우클릭 메뉴가
        읽는다 — Codex 의 state["codex_onboard"] 와 같은 자리), state["gemini"] 는 None, agy 0번, 앱의 훅은
        구간을 내지 않는다(필에 아무것도 없다). 항목이 있고 읽히면 깃발은 None, 항목은 있는데 agy 가
        로그인을 요구하면 "login". agy 가 설치돼 있지 않으면 깃발이 없다(v5). 숨긴 Gemini 에는 깃발도 확인도
        없다. 이름 `gemini_onboard` 는 이 파일이 건다.
        Rivals: 63d5420(agy 를 띄움, 깃발 없음); 필에 상태 줄을 냄; 숨겨도 메뉴 항목을 냄; agy 가 없어도
        메뉴 항목을 냄; 항목 없음에만 깃발(로그아웃 뒤에는 항목이 남으므로 메뉴가 안 뜬다)."""
        _require("parse_agy_usage")
        self.fake.keychain = "absent"
        state, claude, _codex = self.drive(show_gemini=True)
        self.assertTrue(wait_for(lambda: state.get("gemini_onboard") == "login", 5.0),
                        "로그인 안 된 사용자의 메뉴 깃발(state['gemini_onboard'])이 오르지 않았다")
        self.assertTrue(wait_for(lambda: state["oauth"] == claude, 3.0))
        self.assertEqual(self.fake.calls, [], "로그인 안 된 사용자에게 agy 를 띄웠다")
        self.assertIsNone(state.get("gemini"))
        self.assertIsNone(app_hook(self, state)(), "로그인 안 된 Gemini 가 필에 무언가를 냈다")
        self.assert_only_existence_checks(at_least=1)

        reset_gemini_state()
        self.fake.keychain = "present"
        state, _claude, _codex = self.drive(show_gemini=True)
        self.assertTrue(wait_for(lambda: bool(state.get("gemini")), 5.0))
        self.assertIsNone(state.get("gemini_onboard"))

        # 항목은 있는데 agy 가 로그인을 요구(auth 실패) → 깃발이 오른다.
        reset_gemini_state()
        self.fake.mode = "login_exit"
        state, _claude, _codex = self.drive(show_gemini=True)
        self.assertTrue(wait_for(lambda: state.get("gemini_onboard") == "login", 5.0),
                        "agy 가 로그인을 요구했는데 메뉴 깃발이 오르지 않았다")
        self.assertIsNone(state.get("gemini"))
        self.fake.mode = "ok"

        # v5: agy 가 설치돼 있지 않으면 메뉴 항목을 내지 않는다(눌러도 열 것이 없다).
        reset_gemini_state()
        self.fake.calls.clear()
        self.fake.keychain = "absent"
        self.which["agy"] = None
        state, claude, _codex = self.drive(show_gemini=True)
        self.assertTrue(wait_for(lambda: state["oauth"] == claude, 3.0))
        self.assertTrue(wait_for(lambda: state.get("repaint") is True, 3.0))
        _real_time.sleep(0.5)
        self.assertIsNone(state.get("gemini_onboard"), "agy 가 없는 사용자에게 로그인 메뉴 깃발을 올렸다")
        self.assertEqual(self.fake.calls, [])
        self.which["agy"] = self.agy_path

        reset_gemini_state()
        del self.fake.security[:]
        self.fake.keychain = "absent"
        state, claude, _codex = self.drive(show_gemini=False)
        self.assertTrue(wait_for(lambda: state["oauth"] == claude, 3.0))
        _real_time.sleep(0.3)
        self.assertIsNone(state.get("gemini_onboard"), "숨긴 Gemini 에 로그인 메뉴 깃발을 올렸다")
        self.assertEqual(self.fake.security, [], "숨긴 Gemini 때문에 키체인을 확인했다")

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
