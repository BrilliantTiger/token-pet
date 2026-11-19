"""TOK-61 — 로그인돼 있는 Gemini 에 [로그인] 을 띄우지 않는다.

1.2.0 에서 실제로 난 일(대표님 Mac mini): agy 에 로그인돼 있는데 사용량 조회가 인증서 오류로 실패하자
설정 줄이 "로그인 필요 [로그인]" 이 됐고, 누르니 로그인 창이 떠서 같은 오류를 찍고 "시간이 지났어요" 로
끝났다. 대표님: "로그인 이미 되어잇어! 근데 그걸 로그인 쳐하라고 띄운다고?!"

기준
  ① 로그인 정보(키체인 gemini/antigravity, Windows gemini:antigravity)가 있으면, agy 가 로그인을 요구한
     경우(`_agy_wants_login`)가 아닌 한 [로그인] 버튼도 로그인 창도 없다.
  ② 조회가 다른 이유(네트워크·인증서·서버)로 실패하면 줄은 "연결됨 · 지금은 사용량을 못 읽음" 이다.
  (로그인 창이 오류로 끝났을 때의 문구는 tests/test_v8_fixes.py 의 창 테스트가 본다.)

여기서 정한 이름(코어 claude_pet.py)
  gemini_link_state()          "connected" | "unreadable" | "cert" | "login" | "unknown"
  ai_connect_detail(provider)  None | (kind, 오류 글자 또는 None) — kind: "unreadable" | "cert" | "checking".
                               ai_connect_row(..., detail=) 로 넘긴다. row["error"] 가 그 오류 글자다.
  run_cli_login("gemini")      창을 띄우기 전에 확인한다 → "already" | "unreadable" | (창을 띄운 뒤의 결과)
  GEMINI_FAIL_RETRY_SEC        로그인 요구가 아닌 실패 뒤 자동으로 다시 읽기까지(자동 간격보다 짧다)
  TR: ai_unreadable, ai_hint_unreadable, ai_hint_cert, ai_hint_error (4개 로케일)
  child_env(base_env=None)     자식 프로세스의 환경 — 못 쓸 SSL_CERT_FILE·SSL_CERT_DIR 을 뺀 사본

원인(대표님 Mac mini 실측): py2app 번들은 자기 환경에 SSL_CERT_FILE·SSL_CERT_DIR=<번들>/Contents/
Resources/openssl.ca/no-such-file 을 넣는다. 앱이 띄운 agy 와 앱이 연 터미널이 그것을 물려받아 x509 오류가 났다.

진짜 agy·키체인·자격 증명 관리자·터미널은 건드리지 않는다. agy 실행(`_agy_exec`), 로그인 지문
(`_gemini_login_marker`), 로그인 창(`start_gemini_login`)은 모두 대역이다. macOS 와 Windows CI 에서 돈다.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import claude_pet  # noqa: E402
except ImportError:
    from windows.win_core import import_core  # noqa: E402
    claude_pet = import_core()

LANGS = ("en", "ko", "ja", "es")
# 대표님 Mac mini 의 창에 찍힌 줄과 같은 모양(주소는 합성).
X509 = ('error: Eligibility check failed: Post "https://synthetic.invalid/v1internal:loadCodeAssist": '
        "tls: failed to verify certificate: x509: certificate signed by unknown authority\n")
NETWORK = 'error: Post "https://synthetic.invalid/x": dial tcp: lookup synthetic.invalid: no such host\n'
WANTS_LOGIN = "Authentication required. Visit the URL to log in:\nhttps://synthetic.invalid/o/oauth2\n"
SIGNED_IN = (True, "20261101000000Z", ())
NO_SIGN_IN = (False, None, ())
ROWS = [("gemini", 12.0, None, None)]


def _require(name):
    fn = getattr(claude_pet, name, None)
    if fn is None:
        raise AssertionError("claude_pet.%s 가 없다 — TOK-61 미구현" % name)
    return fn


class Case(unittest.TestCase):

    def setUp(self):
        for d in (claude_pet._gemini_cache, claude_pet.GEMINI_STATUS, claude_pet._gemini_refresh,
                  claude_pet.GEMINI_BUCKETS):
            snap = dict(d)
            self.addCleanup(lambda d=d, snap=snap: (d.clear(), d.update(snap)))
        claude_pet._gemini_cache.update(t=0.0, rows=None, ok_t=None, click=False, click_check=False,
                                        check_t=0.0, login=None, marker=None, auth_failed_marker=None,
                                        cause=None, error_text=None)
        claude_pet.GEMINI_STATUS.update(auth_error=False, last_error=None)
        claude_pet._gemini_refresh["busy"] = False
        self.marker = SIGNED_IN
        self.stderr = X509
        self.succeed = False
        self.runs = []
        self.windows = []
        self.dbg = []
        boom = AssertionError("진짜 프로세스를 띄우려 했다")
        for name, fake in (("_find_agy_cli", lambda: "/synthetic/bin/agy"),
                           ("find_cli", lambda p: "/synthetic/bin/agy"),
                           ("_gemini_login_marker", lambda rules: self.marker),
                           ("keychain_locked", lambda: False),
                           ("_agy_exec", self._exec),
                           ("start_gemini_login", lambda *a, **k: self.windows.append(1)),
                           ("_dbg", lambda *a, **k: self.dbg.append(a))):
            self._patch(mock.patch.object(claude_pet, name, fake))
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen", side_effect=boom))
        self._patch(mock.patch.object(claude_pet.subprocess, "run", side_effect=boom))

    def _patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def _exec(self, agy, rules):
        self.runs.append(agy)
        if self.succeed:
            return 0, "SYNTHETIC", "", None
        return 1, "", self.stderr, ("login" if self.stderr == WANTS_LOGIN else None)

    def succeed_next(self):
        self.succeed = True
        self._patch(mock.patch.object(claude_pet, "_run_agy_usage",
                                      lambda agy, rules: (self.runs.append(agy), (list(ROWS), None, {}))[1]))

    def read(self):
        """새로고침이 하는 조회 한 번(누른 것처럼 — 60초 하한과 무관하게 지금)."""
        claude_pet._gemini_cache.update(t=0.0, click=True, click_check=True)
        return claude_pet.fetch_gemini_usage()

    def row(self, job=None):
        detail = _require("ai_connect_detail")("gemini")
        return claude_pet.ai_connect_row("gemini", True, claude_pet.cli_logged_in("gemini"), job, detail=detail)

    def login(self, cancel=lambda: True):
        """[로그인] 한 번. 창이 뜨면 곧바로 취소한다(창을 띄웠는지만 본다)."""
        return claude_pet.run_cli_login("gemini", cancel=cancel)

    def assert_nothing_leaked(self):
        text = repr(self.dbg)
        for secret in ("synthetic.invalid", "x509", "unknown authority"):
            self.assertNotIn(secret, text, "agy 의 출력이 디버그 로그로 나갔다")


class RowAfterAFailedReadTests(Case):

    def test_a_certificate_error_does_not_turn_a_signed_in_gemini_into_sign_in(self):
        """①②: 로그인 정보가 있고 조회가 인증서 오류(x509)로 실패했다 → 연결된 것으로 보고 [로그인] 이 없다.
        줄은 "연결됨 · 지금은 사용량을 못 읽음", 안내는 인증서 오류.
        Rivals: 마지막 조회 성공만 봄(1.2.0 — [로그인] 이 뜬다); 실패를 모두 로그인 요구로; 그냥 "연결됨"
        (못 읽는다는 것을 숨긴다)."""
        self.assertIsNone(self.read())
        self.assertEqual(len(self.runs), 1)
        self.assertIs(claude_pet.GEMINI_STATUS["auth_error"], False)
        self.assertEqual(_require("gemini_link_state")(), "cert")
        self.assertIs(claude_pet.cli_logged_in("gemini"), True)
        row = self.row()
        self.assertEqual((row["status"], row["button"], row["hint"]), ("ai_unreadable", None, "ai_hint_cert"))
        # 오류를 그대로 보여 준다 — 안내 칸에 들어가는 길이로, 원인이 있는 끝쪽을.
        self.assertIn("x509: certificate signed by unknown authority", str(row["error"]))
        self.assertLessEqual(len(row["error"]), 61)
        for lang in LANGS:
            with mock.patch.dict(claude_pet.L, {"lang": lang}):
                status, button, hint = claude_pet.ai_connect_text(row)
            self.assertEqual(status, claude_pet.TR[lang]["ai_unreadable"])
            self.assertIsNone(button)
            self.assertIn("x509: certificate signed by unknown authority", hint)
            self.assertLessEqual(len(hint), 175, "%s: 안내 칸(세 줄)을 넘는다" % lang)
        self.assert_nothing_leaked()

    def test_a_failed_read_is_tried_again_soon_without_a_click(self):
        """실패하면 자동으로 다시 읽는다 — 5분을 기다리지 않고 GEMINI_FAIL_RETRY_SEC 뒤에. 그 전에는 띄우지 않는다."""
        retry = _require("GEMINI_FAIL_RETRY_SEC")
        self.assertLess(retry, claude_pet.GEMINI_AUTO_SEC)
        self.read()
        self.assertEqual(len(self.runs), 1)
        now = claude_pet.time.time()
        claude_pet._gemini_cache["t"] = now - retry + 20
        claude_pet.fetch_gemini_usage()
        self.assertEqual(len(self.runs), 1, "실패 직후에 또 띄웠다")
        claude_pet._gemini_cache["t"] = now - retry - 1
        claude_pet.fetch_gemini_usage()
        self.assertEqual(len(self.runs), 2, "실패한 뒤 누르지 않으면 다시 읽지 않는다")

    def test_before_the_first_answer_the_row_says_checking_not_sign_in(self):
        """로그인 정보를 아직 확인하지 않았거나(설정을 막 열었다) 첫 조회를 기다리는 동안은 "확인 중" — 버튼
        없음. 확인했는데 알 수 없었으면 [로그인] 이 남는다."""
        self.assertEqual(_require("ai_connect_detail")("gemini"), ("checking", None))
        row = self.row()
        self.assertEqual((row["status"], row["button"]), ("ai_verifying", None))
        claude_pet._gemini_cache.update(login=True, check_t=claude_pet.time.time())
        self.assertEqual(self.row()["status"], "ai_verifying")
        claude_pet._gemini_cache.update(login=None)
        row = self.row()
        self.assertEqual((row["status"], row["button"]), ("ai_need_login", "ai_btn_login"))
        self.assertEqual(claude_pet.ai_connect_row("gemini", False, False, None, detail=("checking", None))["button"],
                         "ai_btn_install")

    def test_the_error_text_helper(self):
        text = _require("_agy_error_text")
        self.assertIsNone(text(""))
        self.assertEqual(text("warn\nerror: short one\n"), "error: short one")
        long = text(X509)
        self.assertTrue(long.startswith("…") and long.endswith("x509: certificate signed by unknown authority"))
        self.assertLessEqual(len(text("x" * 500)), 61)
        cause = _require("_agy_failure_cause")
        self.assertEqual((cause(X509), cause(NETWORK), cause("")), ("cert", None, None))

    def test_a_network_error_reads_as_connected_but_unreadable(self):
        """②: 인증서가 아닌 실패(네트워크·서버·시간 초과)도 [로그인] 이 아니다 — 안내만 다르다."""
        self.stderr = NETWORK
        self.read()
        self.assertEqual(_require("gemini_link_state")(), "unreadable")
        row = self.row()
        self.assertEqual((row["status"], row["button"], row["hint"]),
                         ("ai_unreadable", None, "ai_hint_unreadable"))
        self.assert_nothing_leaked()

    def test_only_a_login_demand_offers_sign_in(self):
        """①: agy 가 로그인을 요구했을 때만 "로그인 필요 [로그인]". 로그인 정보가 아예 없을 때도 그렇다
        (그때는 agy 를 띄우지 않는다)."""
        self.stderr = WANTS_LOGIN
        self.read()
        self.assertEqual(_require("gemini_link_state")(), "login")
        self.assertIs(claude_pet.cli_logged_in("gemini"), False)
        row = self.row()
        self.assertEqual((row["status"], row["button"]), ("ai_need_login", "ai_btn_login"))
        self.assertIsNone(_require("ai_connect_detail")("gemini"))
        self.runs.clear()
        self.marker = NO_SIGN_IN
        claude_pet._gemini_cache.update(auth_failed_marker=None, login=None)
        self.read()
        self.assertEqual(self.runs, [], "로그인 정보가 없는데 agy 를 띄웠다")
        row = self.row()
        self.assertEqual((row["status"], row["button"]), ("ai_need_login", "ai_btn_login"))

    def test_a_good_read_is_plain_connected_and_a_kept_value_stays_connected(self):
        """성공하면 그냥 "연결됨". 그 뒤 한 번의 일시 실패로 직전 값이 유지되는 동안에도 "연결됨" 이다."""
        self.succeed_next()
        self.assertEqual(self.read(), ROWS)
        self.assertEqual(_require("gemini_link_state")(), "connected")
        row = self.row()
        self.assertEqual((row["status"], row["button"], row["hint"]), ("ai_connected", None, "ai_hint_gemini"))
        self._patch(mock.patch.object(claude_pet, "_run_agy_usage", lambda agy, rules: (None, "timeout", None)))
        self.assertEqual(self.read(), ROWS)
        self.assertEqual(claude_pet.gemini_link_state(), "connected")
        self.assertEqual(self.row()["status"], "ai_connected")

    def test_the_new_copy_exists_in_four_languages(self):
        ko = claude_pet.TR["ko"]
        self.assertEqual([w for w in ("연결됨", "못 읽") if w not in str(ko.get("ai_unreadable"))], [])
        self.assertIn("인증서", str(ko.get("ai_hint_cert")))
        self.assertIn("로그인", str(ko.get("ai_hint_unreadable")))
        for lang in LANGS:
            for key in ("ai_unreadable", "ai_hint_unreadable", "ai_hint_cert", "ai_hint_error"):
                val = claude_pet.TR[lang].get(key)
                self.assertTrue(isinstance(val, str) and val.strip(), "%s.%s 가 없다" % (lang, key))
                if lang != "ko":
                    self.assertNotEqual(val, ko.get(key), "%s.%s 에 한국어 문구가 그대로다" % (lang, key))
            self.assertIn("{err}", claude_pet.TR[lang]["ai_hint_error"])


class SignInWindowTests(Case):
    """[로그인] 을 눌렀을 때(run_cli_login) — 창을 띄우기 전에 확인한다."""

    def test_a_signed_in_user_behind_a_certificate_error_never_gets_the_window(self):
        """①: 1.2.0 의 그 장면 — 아직 한 번도 읽지 못했고(줄은 [로그인]), 로그인 정보는 있고, agy 는 인증서
        오류로 끝난다. 눌러도 창은 뜨지 않고 줄은 "연결됨 · 지금은 사용량을 못 읽음" 이 된다.
        Rivals: 확인 없이 창부터 띄움(1.2.0); 지문이 있으면 무조건 "already"(못 읽는 것을 숨긴다)."""
        claude_pet._gemini_cache["check_t"] = 1.0        # 확인했지만 알 수 없었다 → 줄에 [로그인] 이 남아 있다
        self.assertEqual(self.row()["button"], "ai_btn_login")
        self.assertEqual(self.login(), "unreadable")
        self.assertEqual(self.windows, [], "로그인돼 있는데 로그인 창을 띄웠다")
        self.assertEqual(len(self.runs), 1, "확인하는 조회는 한 번이다")
        row = self.row()
        self.assertEqual((row["status"], row["button"], row["hint"]), ("ai_unreadable", None, "ai_hint_cert"))
        self.assert_nothing_leaked()

    def test_the_whole_connect_flow_ends_without_a_window_and_without_a_failure(self):
        job = claude_pet.new_ai_job()
        got = claude_pet.run_ai_connect("gemini", job, cancel=lambda: False)
        self.assertEqual(self.windows, [])
        self.assertIsNone(job["phase"], "실패가 아니다 — [다시 시도] 가 아니라 연결됨 줄이다")
        self.assertIn(got, ("unreadable", "already"))
        row = self.row(job)
        self.assertEqual((row["status"], row["button"]), ("ai_unreadable", None))

    def test_a_working_sign_in_says_already(self):
        """①: 로그인 정보가 있고 조회가 된다 → "already", 창 없음(Claude 와 같다)."""
        self.succeed_next()
        self.assertEqual(self.login(), "already")
        self.assertEqual(self.windows, [])
        self.assertEqual(self.row()["status"], "ai_connected")

    def test_a_login_demand_opens_the_window(self):
        """①: agy 가 로그인을 요구하면(항목만 남은 로그아웃·만료) 창을 띄운다. 이미 요구를 받아 멈춰 있고
        지문이 그대로면 확인하려고 agy 를 다시 띄우지 않는다."""
        self.stderr = WANTS_LOGIN
        self.assertEqual(self.login(), "cancelled")
        self.assertEqual(len(self.windows), 1, "로그인 요구인데 창을 띄우지 않았다")
        self.assertEqual(len(self.runs), 1)
        self.assertEqual(self.login(), "cancelled")
        self.assertEqual(len(self.windows), 2)
        self.assertEqual(len(self.runs), 1, "지문이 그대로인데 로그인 안 된 agy 를 또 띄웠다")

    def test_without_any_sign_in_the_window_opens_and_agy_is_not_run(self):
        self.marker = NO_SIGN_IN
        self.assertEqual(self.login(), "cancelled")
        self.assertEqual(len(self.windows), 1)
        self.assertEqual(self.runs, [], "로그인 정보가 없는데 agy 를 숨은 프로세스로 띄웠다")

    def test_a_demand_that_the_user_has_since_answered_elsewhere_is_checked_again(self):
        """옛 로그인 요구가 남아 있어도 그 뒤 지문이 바뀌었으면(다른 곳에서 로그인했다) 다시 확인한다 —
        되면 "already", 창 없음."""
        claude_pet._gemini_cache.update(login=True, marker=(True, "20261001000000Z", ()),
                                        auth_failed_marker=(True, "20261001000000Z", ()),
                                        t=claude_pet.time.time())
        claude_pet.GEMINI_STATUS.update(auth_error=True, last_error="login")
        self.succeed_next()
        self.assertEqual(self.login(), "already")
        self.assertEqual(self.windows, [])

    def test_the_row_says_checking_until_the_window_really_opens(self):
        """누른 뒤 확인하는 동안은 "확인 중" 이고, 창이 실제로 뜰 때에야 "열린 창에 붙여 넣으세요" 다."""
        job = claude_pet.new_ai_job()
        seen = []
        self._patch(mock.patch.object(claude_pet, "_agy_exec",
                                      lambda agy, rules: (seen.append(job["phase"]), self._exec(agy, rules))[1]))
        self._patch(mock.patch.object(claude_pet, "start_gemini_login",
                                      lambda *a, **k: (seen.append(job["phase"]), self.windows.append(1))))
        self.stderr = WANTS_LOGIN
        self.assertEqual(claude_pet.run_ai_connect("gemini", job, cancel=lambda: bool(self.windows)), "cancelled")
        self.assertEqual(seen, ["verify", "login"])

    def test_when_the_sign_in_cannot_be_looked_up_the_window_still_opens(self):
        """지문을 알 수 없으면(확인 실패) 로그인 정보가 있다고 할 수 없다 → 창을 띄운다. agy 는 띄우지 않는다."""
        self.marker = None
        self.assertEqual(self.login(), "cancelled")
        self.assertEqual(len(self.windows), 1)
        self.assertEqual(self.runs, [])


BUNDLE_CA = "/Applications/ClaudePet.app/Contents/Resources/openssl.ca/no-such-file"


class ChildEnvironmentTests(unittest.TestCase):
    """번들이 넣은 인증서 변수를 자식에게 물려주지 않는다."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp(prefix="claudepet-tok61-")
        self.addCleanup(__import__("shutil").rmtree, self.dir, ignore_errors=True)
        self.real = os.path.join(self.dir, "corp-ca.pem")
        with open(self.real, "w", encoding="utf-8") as f:
            f.write("synthetic")

    def test_the_bundle_values_are_dropped_and_a_real_user_value_is_kept(self):
        """Rivals: 그대로 물려줌(1.2.0); 무조건 지움(회사 CA 묶음을 직접 정한 사용자의 agy 가 깨진다);
        os.environ 자체를 고침(앱 자신의 HTTPS 를 건드린다)."""
        child_env = _require("child_env")
        base = {"SSL_CERT_FILE": BUNDLE_CA, "SSL_CERT_DIR": BUNDLE_CA, "KEEP": "1"}
        self.assertEqual(child_env(base), {"KEEP": "1"})
        self.assertEqual(base["SSL_CERT_FILE"], BUNDLE_CA, "넘겨받은 dict 를 고쳤다")
        gone = os.path.join(self.dir, "nope.pem")
        self.assertEqual(child_env({"SSL_CERT_FILE": gone, "SSL_CERT_DIR": ""}), {})
        self.assertEqual(child_env({"SSL_CERT_FILE": self.real, "SSL_CERT_DIR": self.dir}),
                         {"SSL_CERT_FILE": self.real, "SSL_CERT_DIR": self.dir})
        with mock.patch.dict(os.environ, {"SSL_CERT_FILE": BUNDLE_CA, "SSL_CERT_DIR": BUNDLE_CA}):
            got = child_env()
            self.assertEqual([k for k in got if k.upper() in ("SSL_CERT_FILE", "SSL_CERT_DIR")], [])
            self.assertEqual(os.environ["SSL_CERT_FILE"], BUNDLE_CA, "앱 자신의 환경을 바꿨다")

    def test_every_cli_environment_goes_through_it(self):
        with mock.patch.dict(os.environ, {"SSL_CERT_FILE": BUNDLE_CA, "SSL_CERT_DIR": BUNDLE_CA}):
            for provider in ("claude", "codex", "gemini"):
                env = claude_pet.cli_env(provider, "/synthetic/bin/x")
                self.assertEqual([k for k in env if k.upper() in ("SSL_CERT_FILE", "SSL_CERT_DIR")], [],
                                 "%s 의 환경에 번들의 인증서 변수가 남았다" % provider)
            with mock.patch.object(claude_pet, "_gemini_fake_open_dir", lambda: self.dir, create=True), \
                    mock.patch.object(claude_pet, "_gemini_fake_rundll_dir", lambda: self.dir, create=True):
                env = claude_pet._agy_env(claude_pet._gemini_edge_rules())
            self.assertIsInstance(env, dict)
            self.assertEqual([k for k in env if k.upper() in ("SSL_CERT_FILE", "SSL_CERT_DIR")], [])

    @unittest.skipIf(sys.platform == "win32", "bash 줄을 실제로 돌려 본다")
    def test_the_terminal_script_clears_them_first_by_the_same_rule(self):
        """Terminal 이 이미 그 값을 물려받은 채 떠 있을 수 있다 — 스크립트 맨 앞에서 지운다. 실제로 있는
        사용자 값은 남긴다."""
        import subprocess
        head = _require("_SSL_UNSET_SH")
        self.assertIn("unset SSL_CERT_FILE", head)
        self.assertIn("unset SSL_CERT_DIR", head)
        show = head + 'echo "F=${SSL_CERT_FILE:-} D=${SSL_CERT_DIR:-}"\n'
        for env, want in (({"SSL_CERT_FILE": BUNDLE_CA, "SSL_CERT_DIR": BUNDLE_CA}, "F= D="),
                          ({"SSL_CERT_FILE": os.path.join(self.dir, "nope")}, "F= D="),
                          ({}, "F= D="),
                          ({"SSL_CERT_FILE": self.real, "SSL_CERT_DIR": self.dir},
                           "F=%s D=%s" % (self.real, self.dir))):
            r = subprocess.run(["/bin/bash", "-c", show], env=dict(env, PATH="/usr/bin:/bin"),
                               capture_output=True, text=True, timeout=20)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, want), r.stderr)

    def test_the_sign_in_window_starts_with_the_clearing_line_on_both_platforms(self):
        seen = []
        with mock.patch.object(claude_pet, "_find_agy_cli", lambda: "/synthetic/bin/agy"), \
                mock.patch.object(claude_pet, "_run_in_terminal", seen.append), \
                mock.patch.object(sys, "platform", "darwin"):
            claude_pet.start_gemini_login()
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith(claude_pet._SSL_UNSET_SH), "스크립트 맨 앞이 아니다")
        ps = _require("_SSL_UNSET_PS")
        for word in ("SSL_CERT_FILE", "SSL_CERT_DIR", "Remove-Item"):
            self.assertIn(word, ps)
        src = open(claude_pet.__file__.replace(".pyc", ".py"), encoding="utf-8").read()
        self.assertIn("[_SSL_UNSET_PS] +", src, "Windows 콘솔의 명령 맨 앞에 없다")
        # macOS 의 Terminal 을 여는 `open` 에도 걸러진 환경을 준다.
        self.assertIn('["/usr/bin/open", "-a", "Terminal", path], env=child_env()', src)


if __name__ == "__main__":
    unittest.main()
