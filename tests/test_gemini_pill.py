"""Gemini 필·설정 게이팅 테스트 — TOK-47 v2(릴리즈 1.2.0, macOS 먼저), Verifier 작성, 구현 전.

v2(2026-11-18): 사용량은 `agy -p "/usage" --output-format json` 에서 온다(tests/test_gemini_usage.py).
그래서 모델별 줄("models" 게이지, `gemini:<modelId>` 행)은 없어지고, Gemini 묶음의 한도 줄("limits")이
생겼다. v4(대표님 지시): 로그인 안 됨 = **필에 아무것도 없다**(상태 줄 `gemini_login` 은 없앴다) — 대신
우클릭 메뉴에 "Gemini 로그인(agy)"(TR `menu_gemini_login`)이 뜬다. 90fd32b 에서 v2 게이트는 빨강이어야 한다(AGENTS.md §3) —
빨강은 ImportError 가 아니라 `_require` 의 AssertionError 이거나 단언 실패다.

── 계약 (Coordinator, TOK-47 v2) ────────────────────────────────────────────────────

1. 설정: RUNTIME 기본값 `"show_gemini": True`, `"gemini_gauges": ["gemini"]`;
   `GEMINI_GAUGES = ("gemini", "limits", "group")`; codex_gauges 처럼 `_gauge_list` 로 검증·저장,
   망가진 값(목록이 아님) → ["gemini"].
2. `provider_shown(runtime, "gemini")` 는 `show_gemini` 를 따른다.
3. 행(TOK-44 v2): 0행 `("gemini", …)`, 이어 모든 묶음의 버킷 `gemini_group:<bucket id>`, 서버 순서.
   게이지 "gemini" → 0행, 라벨 "Gemini"; "limits" → **Gemini 묶음**의 행, 라벨은 버킷 window 에 따라
   그 로케일의 5시간/주간(ko "5시간"/"주간"; 5시간은 새 TR 키 `gemini_5h`, 주간은 `t("weekly")` 그대로);
   "group" → 나머지 묶음의 행, "Claude·GPT 5시간"/"Claude·GPT 주간"(TR `gemini_group_5h` /
   `gemini_group_weekly`), window 를 모르면 "Claude·GPT"(TR `gemini_group`).
   rows None → None(블록 없음, 0% 금지). auth_error(로그인 안 됨)여도 None — Gemini 에는 상태 구간이 없다.
   agy 가 없으면(last_error "not_installed") 블록 없음.
4. 필: 제공자 순서 claude, codex, gemini; 마크 `SUMMARY_LOGO_FILES["gemini"] = "gemini.svg"`;
   roam_summary_text 루프가 gemini 를 포함한다(`state["gemini_summary"]` 훅).
5. 설정 창: Gemini 구역(표시 토글 + GEMINI_GAUGES 체크박스), 저장 트랜잭션이 두 키를 저장한다.
6. Gemini 에는 급증 감지가 없다.
7. Windows 포트: 리더 없음(fetch → None) — 포트가 죽지 않고 Gemini 블록을 내지 않는다(회귀 가드).

── 어느 행이 Gemini 묶음이고 window 가 무엇인지가 구간에 닿는 길 ─────────────────────────────

계약은 "창 표 {bucket id: window} 와 Gemini 묶음 소속을 순수 도우미로 낸다"고만 하고 이름·경로는 정하지
않았다. 그래서 limits/group 을 가르는 테스트(GeminiLimitsAndGroupTests)는 **조회 경로 전체**를 탄다: 가짜
agy 응답 → `fetch_gemini_usage()` → `state["gemini"]` → 앱의 `state["gemini_summary"]` 훅. 표가 모듈
dict 로 가든, 인자로 가든, 다른 길로 가든 통과한다. bucket id 는 일부러 window 를 이름에 담지 않거나
(`gemini-a`) 거꾸로 담는다(`gemini-weekly` 인데 window 는 5h) — id 접미사를 읽는 구현을 가른다.

── 이 파일이 Developer 에게 거는 이름 ──────────────────────────────────────────────────

  · Gemini 행은 `state["gemini"]`, 훅은 `state["gemini_summary"]`(v1 그대로).
  · 설정 구역 제목 TR 키 `s_sec_gemini`(v1 그대로).
  · `gemini_summary_segment(runtime, rows, auth_error=…)` 는 v1 처럼 직접 부를 수 있다(0행·상태·숨김).
"""

import ast
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
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
PORT = ROOT / "windows" / "claude_pet_win.py"
UTC = timezone.utc
LANGS = ("en", "ko", "ja", "es")


def _require(name):
    value = getattr(claude_pet, name, None)
    if value is None:
        raise AssertionError(
            f"claude_pet.{name} 가 없다 — TOK-47 Gemini 필·설정 계약이 아직 구현되지 않았다. "
            "이 파일은 구현 전에 쓰였고 지금 빨간 것이 정상이다.")
    return value


class _Guard(unittest.TestCase):
    """RUNTIME·언어·GEMINI_STATUS 를 테스트 뒤에 되돌린다."""

    def setUp(self):
        saved = dict(claude_pet.RUNTIME)
        self.addCleanup(lambda: (claude_pet.RUNTIME.clear(), claude_pet.RUNTIME.update(saved)))
        lang = claude_pet.L.get("lang")
        self.addCleanup(lambda: claude_pet.L.__setitem__("lang", lang))
        status = getattr(claude_pet, "GEMINI_STATUS", None)
        if isinstance(status, dict):
            snap = dict(status)
            self.addCleanup(lambda: (status.clear(), status.update(snap)))


# ═════════════════════════════ 합성 행 (TOK-44 모양) ═════════════════════════════

T_NOW = datetime.now(UTC).replace(microsecond=0)
R_HEAD = T_NOW + timedelta(hours=2, minutes=30, seconds=30)   # 분 경계에서 멀다
R_FLASH = T_NOW + timedelta(hours=1, minutes=10, seconds=30)
R_WEEK = T_NOW + timedelta(days=3, hours=4, minutes=20, seconds=30)
R_5H = T_NOW + timedelta(hours=4, minutes=5, seconds=30)

HEAD = ("gemini", 75.0, R_HEAD, None)
# v1 의 모델 행 — v2 에는 그런 행도 게이지도 없다. 남은 것이 있으면 어느 게이지에서도 보이지 않아야 한다.
STALE_MODEL = ("gemini:gemini-2.5-flash", 60.0, R_FLASH, None)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _b(bid, window, frac, reset=None):
    b = {"id": bid, "name": "synthetic", "description": "synthetic", "remaining_fraction": frac}
    if window is not None:
        b["window"] = window
    if reset is not None:
        b["reset_time"] = _iso(reset)
    return b


# 서버 순서 그대로: 나머지 묶음이 **먼저**, 그리고 각 묶음에서 weekly 가 먼저다. 순서로 라벨을 붙이는 구현
# (첫째 = 5h), 첫 묶음을 Gemini 로 보는 구현, 게이지 순서로 행을 재배열하는 구현을 가른다.
# Gemini 묶음의 가장 낮은 남은 비율(0.25 → 75%)은 가운데 버킷이다.
G_OTHER = {"name": "Claude and GPT models", "description": "synthetic", "buckets": [
    _b("3p-a", "weekly", 0.9, R_WEEK),            # 실제 weekly — 이름에 없다
    _b("x-weekly", "5h", 0.1, R_5H),              # 실제 5h — 이름이 거짓말을 한다
    _b("y-5h", None, 0.8),                        # window 없음 — 이름은 5h 라고 한다
    _b("z", "monthly", 0.7)]}                     # 모르는 window
G_GEMINI = {"name": "Gemini Models", "description": "synthetic", "buckets": [
    _b("gemini-a", "weekly", 0.6, R_WEEK),        # 실제 weekly — 이름에 없다
    _b("gemini-weekly", "5h", 0.25, R_HEAD),      # 실제 5h — 이름이 거짓말을 한다
    _b("gemini-c", "weekly", 0.5, R_FLASH)]}
# id 에 "gemini-" 가 없는 Gemini 묶음 — 묶음 이름으로 찾아야 한다(TOK-44 v2 계약 2).
G_GEMINI_BY_NAME = {"name": "Gemini Models", "description": "synthetic", "buckets": [
    _b("g-1", "5h", 0.4, R_5H), _b("g-2", "weekly", 0.7, R_WEEK)]}
G_OTHER_SMALL = {"name": "Claude and GPT models", "description": "synthetic", "buckets": [
    _b("p-1", "weekly", 0.9, R_WEEK)]}


def _rt(**over):
    rt = {"show_claude": True, "claude_gauges": ["session", "weekly"],
          "show_codex": True, "codex_mode": "sub", "codex_gauges": ["session", "weekly"],
          "show_gemini": True, "gemini_gauges": ["gemini"]}
    rt.update(over)
    return rt


def _segment(test, rt, rows, auth_error=False, last_error=None, lang="en"):
    """gemini_summary_segment 를 한 번, GEMINI_STATUS 도 같은 상태로 맞춰서(어느 쪽을 읽든 통과)."""
    fn = _require("gemini_summary_segment")
    claude_pet.L["lang"] = lang
    status = {"auth_error": bool(auth_error), "last_error": last_error}
    with mock.patch.object(claude_pet, "GEMINI_STATUS", status, create=True):
        return fn(rt, rows, auth_error=auth_error)


def _tr(lang, key):
    return claude_pet.TR[lang].get(key, "<TR %s.%s 없음>" % (lang, key))


def _group_label(lang, window):
    """나머지 묶음 라벨의 기대값 — 주간은 그 로케일의 t("weekly") 표기를 그대로 품는다."""
    return {"5h": _tr(lang, "gemini_group_5h"),
            "weekly": "Claude·GPT " + claude_pet.TR[lang]["weekly"],
            None: "Claude·GPT"}[window]


def _limit_label(lang, window):
    """Gemini 묶음 라벨의 기대값 — 5시간은 새 TR 키 gemini_5h, 주간은 그 로케일의 t("weekly")."""
    return {"5h": _tr(lang, "gemini_5h"), "weekly": claude_pet.TR[lang]["weekly"]}[window]


def _labels(seg):
    test_kind, payload = seg
    return [r[0] for r in payload]


# ═════════════════════════════ 1·2. 설정 ═════════════════════════════


def _runtime_literal_defaults():
    """claude_pet.py 의 `RUNTIME = {...}` 리터럴에서 상수 값만 읽는다(다른 테스트가 바꾼 RUNTIME 이
    아니라 **소스의 기본값**을 본다)."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "RUNTIME"
                and isinstance(node.value, ast.Dict)):
            out = {}
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant):
                    try:
                        out[k.value] = ast.literal_eval(v)
                    except ValueError:
                        out[k.value] = None
            return out
    raise AssertionError("claude_pet.py 에 RUNTIME = {...} 리터럴이 없다")


class GeminiConfigTests(_Guard):

    def test_defaults_show_gemini_with_only_the_headline_gauge(self):
        """기본값: 보이고, 게이지는 0행 하나(TOK-43 사용자 결정 — 기본은 Gemini 한 줄).
        Rivals: 세 게이지를 다 켬; show_gemini 기본 False; 90fd32b 의 ("gemini", "models", "group")
        — v2 에는 모델별 줄이 없다; 순서·이름이 다름(체크박스와 필터가 같은 이름을 써야 한다)."""
        self.assertEqual(_require("GEMINI_GAUGES"), ("gemini", "limits", "group"))
        d = _runtime_literal_defaults()
        self.assertIs(d.get("show_gemini"), True)
        self.assertEqual(d.get("gemini_gauges"), ["gemini"])

    def test_the_keys_are_loaded_owned_and_normalised_like_codex(self):
        """apply_config 가 두 키를 읽고, 손으로 고친 값을 Codex 처럼 정규화한다("false" → False,
        모르는 게이지 — v1 의 "models" 도 — 는 버림). 설정 창이 소유하는 키이기도 하다.
        Rivals: _RUNTIME_CONFIG_KEYS 에 빠뜨림(저장해도 재시작하면 기본값); 정규화 루프가
        ("claude", "codex") 그대로라 문자열 "false" 가 참으로 남음."""
        _require("GEMINI_GAUGES")
        for key in ("show_gemini", "gemini_gauges"):
            with self.subTest(key=key):
                self.assertIn(key, claude_pet._RUNTIME_CONFIG_KEYS)
                self.assertIn(key, claude_pet.SETTINGS_OWNED_KEYS)
        claude_pet.apply_config({"show_gemini": "false",
                                 "gemini_gauges": ["group", "nope", "models", "limits"],
                                 "lang": claude_pet.L["lang"]})
        self.assertIs(claude_pet.RUNTIME.get("show_gemini"), False)
        self.assertEqual(claude_pet.RUNTIME.get("gemini_gauges"), ["limits", "group"])

    def test_the_settings_plan_validates_gemini_like_codex(self):
        """plan_settings_save 가 show_gemini 를 bool 로, gemini_gauges 를 GEMINI_GAUGES 순서로 거른다.
        폼에 두 키가 없으면 base_cfg 의 값을 그대로 둔다(다른 키와 같은 규칙).
        Rivals: 폼 값을 그대로 저장(모르는 이름·순서 그대로); CODEX_GAUGES 로 거름(전부 사라짐);
        빈 선택을 기본값으로 되돌림(빈 목록은 '표시 꺼짐'으로 유효하다)."""
        _require("GEMINI_GAUGES")
        form = {"pet": "dog", "lang": "en", "mode": "sub", "admin_key": "", "api_budget": "0",
                "spike_mult": 1.0, "greet": True, "show_claude": True,
                "claude_gauges": ["session"], "show_codex": True, "codex_mode": "sub",
                "codex_gauges": ["weekly"], "openai_admin_key": "", "codex_budget": "0"}
        cases = (
            ("filtered", {"show_gemini": 1,
                          "gemini_gauges": ["group", "bogus", "limits", "models", "gemini"]},
             True, ["gemini", "limits", "group"]),
            ("empty", {"show_gemini": 0, "gemini_gauges": []}, False, []),
        )
        for name, extra, show, gauges in cases:
            with self.subTest(case=name):
                plan, err = claude_pet.plan_settings_save({}, dict(form, **extra))
                self.assertIsNone(err)
                self.assertIs(plan["updates"].get("show_gemini"), show)
                self.assertEqual(plan["updates"].get("gemini_gauges"), gauges)
        base = {"show_gemini": False, "gemini_gauges": ["limits"]}
        plan, err = claude_pet.plan_settings_save(base, form)
        self.assertIsNone(err)
        self.assertIs(plan["updates"].get("show_gemini"), False)
        self.assertEqual(plan["updates"].get("gemini_gauges"), ["limits"])

    def test_provider_shown_honours_show_gemini_and_its_gauges(self):
        """Rivals: provider_gauges 가 claude 가 아니면 CODEX_GAUGES 로 거름(그러면 "limits"·"group"
        만 고른 사용자는 Gemini 가 통째로 숨는다); show_gemini 를 안 봄; 문자열 "false" 를 참으로;
        90fd32b("limits" 를 모르는 이름으로 버려 숨김)."""
        _require("GEMINI_GAUGES")
        shown = claude_pet.provider_shown
        self.assertTrue(shown(_rt(), "gemini"))
        self.assertTrue(shown(_rt(gemini_gauges=["limits"]), "gemini"))
        self.assertTrue(shown(_rt(gemini_gauges=["group"]), "gemini"))
        self.assertFalse(shown(_rt(show_gemini=False), "gemini"))
        self.assertFalse(shown(_rt(show_gemini="false"), "gemini"))
        self.assertFalse(shown(_rt(gemini_gauges=[]), "gemini"))
        self.assertTrue(shown(_rt(gemini_gauges="broken"), "gemini"),
                        "목록이 아닌 값은 기본값으로 — 숨기지 않는다(provider_gauges 규칙)")
        self.assertEqual(claude_pet.provider_gauges(_rt(gemini_gauges="broken"), "gemini"),
                         ["gemini"], "망가진 gemini_gauges 는 기본값 [\"gemini\"] 로(Coordinator 결정 6)")
        claude_pet.apply_config({"gemini_gauges": {"x": 1}, "lang": claude_pet.L["lang"]})
        self.assertEqual(claude_pet.RUNTIME.get("gemini_gauges"), ["gemini"])


# ═════════════════════════════ 3·4·8. 구간 ═════════════════════════════


class GeminiSegmentTests(_Guard):
    """`gemini_summary_segment(runtime, rows, …, auth_error=…)`."""

    def test_the_headline_gauge_shows_only_row_zero(self):
        """"gemini" 게이지는 0행만, 라벨 "Gemini". 묶음 행·모르는 라벨·v1 모델 행은 내지 않는다.
        Rivals: 묶음 행까지 냄; 모르는 라벨(gemini_other)을 살림; v1 모델 행을 살림."""
        rows = [HEAD, STALE_MODEL, ("gemini_group:gemini-5h", 75.0, R_HEAD, None),
                ("gemini_group:3p-5h", 10.0, R_5H, None), ("gemini_other", 5.0, None, None)]
        for gauges in (["gemini"], "broken"):
            with self.subTest(gauges=gauges):
                seg = _segment(self, _rt(gemini_gauges=gauges), list(rows))
                self.assertIsNotNone(seg)
                self.assertEqual(seg[0], "exact")
                self.assertEqual(_labels(seg), ["Gemini"])

    def test_there_is_no_per_model_line_any_more(self):
        """v2: 모델별 줄은 없다. v1 의 `gemini:<modelId>` 행이 남아 있어도 어느 게이지에서도 보이지 않고,
        "models" 만 고른 옛 설정은 블록이 없다.
        Rival: 90fd32b("models" 게이지가 `gemini:` 행을 "2.5 Flash" 로 보임)."""
        _require("GEMINI_GAUGES")
        self.assertNotIn("models", claude_pet.GEMINI_GAUGES)
        for gauges in (["models"], ["gemini", "limits", "group"], ["gemini", "models", "group"]):
            with self.subTest(gauges=gauges):
                seg = _segment(self, _rt(gemini_gauges=gauges), [STALE_MODEL])
                self.assertIsNone(seg)

    def test_values_resets_and_no_spike_mark(self):
        """pct 는 float 그대로, 리셋은 지금 기준 카운트다운(fmt_countdown 과 같은 문자열), 리셋이
        없으면 None, ▲ 표식(세 번째 칸)은 언제나 False — Gemini 에는 급증 감지가 없다(계약 8).
        Rivals: reset_text(None)를 그대로 써서 카운트다운이 사라짐; 리셋 없음에 "-";
        Claude/Codex 의 급증을 옮겨 닮; pct 를 정수로 반올림."""
        _require("parse_agy_usage")
        seg = _segment(self, _rt(gemini_gauges=["gemini"]), [HEAD])
        self.assertIsNotNone(seg)
        payload = seg[1]
        now = datetime.now(UTC)
        want = [(75.0, claude_pet.fmt_countdown(R_HEAD, now))]
        seg2 = _segment(self, _rt(gemini_gauges=["gemini"]), [("gemini", 33.5, None, None)])
        payload = payload + seg2[1]
        want.append((33.5, None))
        self.assertEqual(len(payload), len(want))
        for row, (pct, shown) in zip(payload, want):
            self.assertIsInstance(row[1], float)
            self.assertAlmostEqual(row[1], pct)
            self.assertIs(row[2], False, "Gemini 행에 급증 표식")
            self.assertEqual(row[3], shown)
        self.assertNotIn("gemini", claude_pet._PROVIDER_LANES, "Gemini 급증 레인이 생겼다")

    def test_no_rows_is_no_block_never_zero(self):
        """보일 행이 없으면 None — 0% 블록도 '조회 중'도 아니다(상태가 없을 때).
        Rivals: [] 를 그대로 ("exact", []); 0% 행을 지어냄; 고른 게이지에 해당하는 행이 없을 때
        다른 게이지 행으로 채움; 일시 실패(timeout·agy_failed·parse)나 agy 없음(not_installed)을
        로그인 필요로 보임."""
        _require("parse_agy_usage")
        cases = (("None", None, ["gemini"], None),
                 ("empty", [], ["gemini"], None),
                 ("filtered away", [HEAD], ["limits", "group"], None),
                 ("unknown labels", [("gemini_other", 5.0, None, None)], ["gemini"], None),
                 ("timeout", None, ["gemini"], "timeout"),
                 ("agy failed", None, ["gemini"], "agy_failed"),
                 ("parse", None, ["gemini"], "parse"),
                 ("not installed", None, ["gemini"], "not_installed"))
        for name, rows, gauges, last in cases:
            with self.subTest(case=name):
                self.assertIsNone(_segment(self, _rt(gemini_gauges=gauges), rows,
                                           auth_error=False, last_error=last))

    def test_needing_login_shows_nothing_in_the_pill(self):
        """v4: 행이 없고 auth_error(로그인 안 됨)면 **None** — 필에는 아무것도 없다(로그인은 우클릭 메뉴가
        안내한다). 행이 있으면 행을 보인다.
        Rivals: 63d5420(("status", "gemini_login") — 대표님: "로그인 안 하면 표시 안 하면 되는 거야");
        다른 상태 구간(gemini_expired 등)을 냄; auth_error 면 행도 숨김."""
        _require("parse_agy_usage")
        self.assertIsNone(_segment(self, _rt(), None, auth_error=True, last_error="login"))
        self.assertIsNone(_segment(self, _rt(), [], auth_error=True, last_error="login"))
        seg = _segment(self, _rt(), [HEAD], auth_error=True, last_error="login")
        self.assertIsNotNone(seg)
        self.assertEqual(seg[0], "exact")

    def test_hidden_gemini_has_no_block_at_all(self):
        """꺼 두었거나 게이지가 없으면 행이 있어도, 로그인이 필요해도 None.
        Rival: 로그인 상태를 표시 설정보다 먼저 봄(끈 제공자의 경고가 뜸)."""
        for name, rt in (("off", _rt(show_gemini=False)), ("no gauges", _rt(gemini_gauges=[]))):
            for auth in (False, True):
                with self.subTest(case=name, auth_error=auth):
                    self.assertIsNone(_segment(self, rt, [HEAD] if not auth else None,
                                               auth_error=auth,
                                               last_error="login" if auth else None))


# ═════════════════════════════ 3. limits / group — 조회 경로 전체 ═════════════════════════════


from test_gemini_usage import AgyCase, agy_payload, app_hook, reset_gemini_state  # noqa: E402


class GeminiLimitsAndGroupTests(AgyCase):
    """가짜 agy 응답 → fetch_gemini_usage() → state["gemini"] → 앱의 state["gemini_summary"] 훅.
    Gemini 묶음 소속과 버킷 window 가 구간까지 가는 길(모듈 표·인자·그 밖)은 정하지 않는다."""

    def setUp(self):
        super().setUp()
        saved = dict(claude_pet.RUNTIME)
        self.addCleanup(lambda: (claude_pet.RUNTIME.clear(), claude_pet.RUNTIME.update(saved)))
        lang = claude_pet.L.get("lang")
        self.addCleanup(lambda: claude_pet.L.__setitem__("lang", lang))

    def labels(self, groups, gauges, lang="en"):
        _require("parse_agy_usage")
        reset_gemini_state()
        self.fake.calls.clear()
        self.fake.payload = agy_payload(groups)
        claude_pet.RUNTIME.update({"show_gemini": True, "gemini_gauges": list(gauges)})
        claude_pet.L["lang"] = lang
        rows = claude_pet.fetch_gemini_usage()
        self.assertEqual(len(self.fake.calls), 1, "agy 를 정확히 한 번 띄워야 한다")
        self.assertIsInstance(rows, list, "가짜 agy 응답에서 행이 나오지 않았다")
        seg = app_hook(self, {"gemini": rows})()
        if seg is None:
            return None
        self.assertEqual(seg[0], "exact")
        return seg[1]

    def test_limits_are_the_gemini_group_rows_labelled_by_their_window(self):
        """"limits" → Gemini 묶음의 버킷만, 서버 순서, 라벨은 버킷의 window 로: 5h → t("gemini_5h"),
        weekly → t("weekly"). ko 는 "주간"/"5시간". 값은 쓴 비율. Gemini 묶음은 응답의 **둘째** 묶음이다.
        Rivals: 첫 묶음을 Gemini 로(Claude·GPT 행이 나옴); 모든 묶음 행; id 접미사로 window 를 읽음
        (gemini-a 를 모름, gemini-weekly 를 주간으로); 서버 순서로 라벨(첫째 = 5h); "Claude·GPT …" 라벨을
        Gemini 묶음에도; 0행을 섞음; 남은 비율을 그대로."""
        for lang in ("ko", "en"):
            with self.subTest(lang=lang):
                got = self.labels([G_OTHER, G_GEMINI], ["limits"], lang)
                self.assertIsNotNone(got, "limits 게이지에 보일 줄이 없다")
                self.assertEqual([r[0] for r in got],
                                 [_limit_label(lang, "weekly"), _limit_label(lang, "5h"),
                                  _limit_label(lang, "weekly")])
                self.assertEqual([round(r[1], 6) for r in got], [40.0, 75.0, 50.0])
                self.assertTrue(all(r[2] is False for r in got), "Gemini 행에 급증 표식")
        self.assertEqual((_limit_label("ko", "weekly"), _limit_label("ko", "5h")), ("주간", "5시간"))

    def test_group_is_the_other_groups_rows_with_the_claude_gpt_labels(self):
        """"group" → Gemini 묶음이 **아닌** 묶음의 버킷만, 서버 순서. 라벨은 window 로 "Claude·GPT 주간"/
        "Claude·GPT 5시간", window 가 없거나 모르는 값이면 "Claude·GPT". en 주간은 t("weekly") 표기 그대로.
        Rivals: 90fd32b(모든 gemini_group: 행 — Gemini 묶음까지); id 접미사 파싱(3p-a 를 모름, x-weekly 를
        주간으로, y-5h 를 5h 로); 서버 순서로 라벨; en 소문자 "weekly"."""
        for lang in ("ko", "en"):
            with self.subTest(lang=lang):
                got = self.labels([G_OTHER, G_GEMINI], ["group"], lang)
                self.assertIsNotNone(got, "group 게이지에 보일 줄이 없다")
                self.assertEqual([r[0] for r in got],
                                 [_group_label(lang, "weekly"), _group_label(lang, "5h"),
                                  _group_label(lang, None), _group_label(lang, None)])
                self.assertEqual([round(r[1], 6) for r in got], [10.0, 90.0, 20.0, 30.0])
        self.assertEqual((_group_label("ko", "weekly"), _group_label("ko", "5h")),
                         ("Claude·GPT 주간", "Claude·GPT 5시간"))

    def test_every_gauge_together_keeps_row_order(self):
        """셋 다 고르면 0행, 이어 버킷 행이 **서버 순서**로(여기서는 나머지 묶음이 먼저). 0행은 Gemini 묶음의
        가장 낮은 남은 비율(가운데 버킷 0.25 → 75%)이고 나머지 묶음의 더 낮은 0.1 이 아니다.
        Rivals: 게이지 순서로 재배열(limits 가 group 앞); 0행에 모든 묶음을 섞음(90%); 한 버킷을 두 번."""
        got = self.labels([G_OTHER, G_GEMINI], ["group", "limits", "gemini"], "en")
        self.assertIsNotNone(got)
        self.assertEqual([r[0] for r in got],
                         ["Gemini",
                          _group_label("en", "weekly"), _group_label("en", "5h"),
                          _group_label("en", None), _group_label("en", None),
                          _limit_label("en", "weekly"), _limit_label("en", "5h"),
                          _limit_label("en", "weekly")])
        self.assertAlmostEqual(got[0][1], 75.0)
        now = datetime.now(UTC)
        self.assertEqual(got[0][3], claude_pet.fmt_countdown(R_HEAD, now))
        self.assertEqual(got[6][3], claude_pet.fmt_countdown(R_HEAD, now))
        self.assertIsNone(got[3][3], "리셋이 없는 버킷에 카운트다운을 지어냈다")

    def test_a_gemini_group_known_only_by_its_name_still_splits_limits_from_group(self):
        """버킷 id 에 "gemini-" 가 없으면 Gemini 묶음은 이름으로 찾는다 — 필의 limits/group 도 그 소속을
        따른다. Rival: 구간이 라벨의 id 접두사("gemini_group:gemini-")만 보고 가름(limits 가 비고 group 에
        Gemini 묶음이 섞임)."""
        groups = [G_OTHER_SMALL, G_GEMINI_BY_NAME]
        got = self.labels(groups, ["limits"], "ko")
        self.assertIsNotNone(got, "이름으로 찾은 Gemini 묶음의 limits 줄이 없다")
        self.assertEqual([(r[0], round(r[1], 6)) for r in got], [("5시간", 60.0), ("주간", 30.0)])
        got = self.labels(groups, ["group"], "ko")
        self.assertIsNotNone(got)
        self.assertEqual([(r[0], round(r[1], 6)) for r in got], [("Claude·GPT 주간", 10.0)])
        got = self.labels(groups, ["gemini"], "ko")
        self.assertEqual([(r[0], round(r[1], 6)) for r in got], [("Gemini", 60.0)])

    def test_a_logged_out_agy_shows_nothing_in_the_pill(self):
        """v4: 로그인 안 됨의 세 모양(키체인 항목 없음; 항목은 있는데 agy 가 로그인을 요구 — 끝나지 않는
        쪽과 바로 실패하는 쪽) → 조회는 None, 상태는 "login"/auth_error True, 앱의 훅은 구간을 내지 않는다.
        Rivals: 63d5420(항목 없음에 agy 를 띄움; 로그인 요구를 "timeout"/"agy_failed" 로 봄; 필에
        gemini_login 상태 줄)."""
        _require("parse_agy_usage")
        claude_pet.RUNTIME.update({"show_gemini": True, "gemini_gauges": ["gemini"]})
        for keychain, mode in (("absent", "ok"), ("present", "login_wait"), ("present", "login_exit")):
            with self.subTest(keychain=keychain, mode=mode):
                reset_gemini_state()
                self.fake.calls.clear()
                self.fake.keychain = keychain
                if mode == "login_wait":
                    self.never_exits(mode)
                else:
                    self.fake.mode = mode
                rows = claude_pet.fetch_gemini_usage()
                self.assertIsNone(rows)
                self.assertEqual(len(self.fake.calls), 0 if keychain == "absent" else 1)
                self.assertEqual(claude_pet.GEMINI_STATUS.get("last_error"), "login")
                self.assertIs(claude_pet.GEMINI_STATUS.get("auth_error"), True)
                self.assertIsNone(app_hook(self, {"gemini": rows})())

    def test_a_gauge_with_no_rows_of_its_own_shows_nothing(self):
        """Gemini 묶음만 온 응답에서 "group" 만 고르면 블록 없음, 나머지 묶음만 온 응답에서 "limits"·"gemini"
        만 고르면 블록 없음. Rival: 빈 게이지를 다른 게이지의 행으로 채움; 0% 를 지어냄."""
        self.assertIsNone(self.labels([G_GEMINI], ["group"]))
        self.assertIsNone(self.labels([G_OTHER], ["limits", "gemini"]))


# ═════════════════════════════ 4·6. 번역 ═════════════════════════════


def _run_gui_tree():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_gui")


def _nested(tree, name):
    found = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    return found[0] if len(found) == 1 else None


def _t_keys(node):
    out = set()
    for c in ast.walk(node):
        if (isinstance(c, ast.Call) and c.args and isinstance(c.args[0], ast.Constant)
                and isinstance(c.args[0].value, str)):
            f = c.func
            if (isinstance(f, ast.Name) and f.id == "t") or (
                    isinstance(f, ast.Attribute) and f.attr == "t"):
                out.add(c.args[0].value)
    return out


def _str_consts(node):
    return {n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _called_names(node):
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            if isinstance(c.func, ast.Name):
                out.add(c.func.id)
            elif isinstance(c.func, ast.Attribute):
                out.add(c.func.attr)
    return out


def _reachable_module_calls(node, depth=2):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    module_fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    seen, frontier = set(), _called_names(node)
    for _ in range(depth + 1):
        seen |= frontier
        nxt = set()
        for name in frontier:
            if name in module_fns:
                nxt |= _called_names(module_fns[name]) - seen
        frontier = nxt
    return seen


class GeminiTranslationTests(unittest.TestCase):

    def test_the_pill_keys_exist_in_every_locale(self):
        """`gemini` 은 모든 로케일에서 "Gemini"; `gemini_5h`(새 키 — Gemini 묶음의 5시간 줄)는 모든 로케일에
        있고 그 로케일의 t("weekly") 와 다르다, ko 는 "5시간"; `gemini_group` 은 "Claude·GPT" 로 시작하고 두
        window 라벨이 그것으로 시작한다; 주간 라벨은 그 로케일의 t("weekly") 를 그대로 품는다(대소문자
        포함); ko 는 계약 문구; v4: 메뉴 항목 `menu_gemini_login` 은 모든 로케일에 있고 "Gemini" 와 `agy` 를
        말한다(ko 는 "로그인"도) — 필의 상태 줄 `gemini_login`·`gemini_expired` 는 없다.
        Rivals: en 에만 넣음(t() 가 en 으로 떨어져 ko 필에 영어); "Gemini" 를 번역함; 5h/weekly 를 같은
        문구로; 63d5420(menu_gemini_login 없음, 필 상태 줄 gemini_login 이 남음)."""
        tr = claude_pet.TR
        for lang in LANGS:
            with self.subTest(lang=lang):
                table = tr[lang]
                self.assertEqual(table.get("gemini"), "Gemini")
                five = table.get("gemini_5h")
                self.assertTrue(isinstance(five, str) and five.strip(), "gemini_5h 가 없다")
                self.assertNotEqual(five, table["weekly"])
                self.assertNotIn("Claude", five)
                base = table.get("gemini_group")
                h5, wk = table.get("gemini_group_5h"), table.get("gemini_group_weekly")
                self.assertTrue(base and h5 and wk, "그룹 라벨(gemini_group/_5h/_weekly)이 없다")
                self.assertTrue(base.startswith("Claude·GPT"))
                self.assertTrue(h5.startswith(base + " ") and wk.startswith(base + " "))
                self.assertNotEqual(h5, wk)
                self.assertIn(table["weekly"], wk,
                              "주간 그룹 라벨이 이 로케일의 t('weekly') 표기를 쓰지 않는다")
                login = table.get("menu_gemini_login")
                self.assertTrue(isinstance(login, str) and "Gemini" in login and "agy" in login,
                                "menu_gemini_login 이 없거나 Gemini·agy 를 말하지 않는다: %r" % login)
                for gone in ("gemini_login", "gemini_expired"):
                    self.assertNotIn(gone, table, "필의 Gemini 상태 줄 TR 이 남아 있다: %s" % gone)
                self.assertTrue(str(table.get("s_sec_gemini", "")).strip(),
                                "설정 구역 제목 s_sec_gemini 가 없다")
        self.assertEqual(tr["ko"].get("gemini_5h"), "5시간")
        self.assertIn("로그인", str(tr["ko"].get("menu_gemini_login")))
        self.assertEqual((tr["ko"].get("gemini_group_5h"), tr["ko"].get("gemini_group_weekly")),
                         ("Claude·GPT 5시간", "Claude·GPT 주간"))
        self.assertEqual(tr["en"].get("gemini_group_weekly"), "Claude·GPT " + tr["en"]["weekly"])

    def test_every_gemini_key_the_settings_panel_uses_exists_in_every_locale(self):
        """open_settings 가 부르는 `t("…")` 중 Gemini 것(이름에 gemini 가 든 키, 그리고
        Gemini 게이지 제목)이 네 로케일에 모두 있고 비어 있지 않다. 패널에 Gemini 키가 하나도
        없으면 그 자체로 실패다. Rival: en 에만 키를 넣음."""
        open_settings = _nested(_run_gui_tree(), "open_settings")
        self.assertIsNotNone(open_settings)
        keys = sorted(k for k in _t_keys(open_settings) if "gemini" in k)
        self.assertTrue(keys, "설정 창이 Gemini TR 키를 하나도 쓰지 않는다")
        for key in keys:
            for lang in LANGS:
                with self.subTest(key=key, lang=lang):
                    self.assertTrue(str(claude_pet.TR[lang].get(key, "")).strip())


# ═════════════════════════════ 5. 필 어댑터 (macOS) ═════════════════════════════


class _Text:
    def __init__(self, v):
        self.v = str(v)

    def size(self):
        return SimpleNamespace(width=7.0 * len(self.v), height=14.0)


class GeminiPillAdapterTests(_Guard):
    """생산 `roam_summary_text` 클로저를 run_gui 에서 AST 로 꺼내 손으로 만든 state 로 돌린다
    (tests/test_summary_layout.py 와 같은 방식). 각 제공자 구간은 훅이 주는 고정 값이다 —
    여기서 보는 것은 **어댑터**: 순서, 블록, 상태 처리, 메모."""

    def run_adapter(self, claude=None, codex=None, gemini=None, show=("claude", "codex", "gemini"),
                    status=None, gemini_rows=None, calls=1, between=None):
        from test_companion_motion import gui_functions

        claude_pet.L["lang"] = "en"          # t() 는 모듈의 L 을 읽는다(_Guard 가 되돌린다)
        runtime = dict(claude_pet.RUNTIME)
        runtime.update(_rt(show_claude="claude" in show, show_codex="codex" in show,
                           show_gemini="gemini" in show, mode="sub",
                           claude_gauges=list(claude_pet.CLAUDE_GAUGES)))
        gstatus = status if status is not None else {"auth_error": False, "last_error": None}
        state = {"stats": {"spikes": {}}, "oauth": None, "cost": None, "cost_month": None,
                 "onboard": None, "credit_text": None, "codex": None, "gemini": gemini_rows,
                 "api_error": False, "api_stale": False, "summary_lines_n": 2,
                 "codex_summary": lambda: codex,
                 "gemini_summary": (gemini if callable(gemini) else (lambda: gemini))}
        scope = dict(vars(claude_pet))
        scope.update(
            state=state, RUNTIME=runtime, L={"lang": "en"},
            OAUTH_STATUS={"auth_error": False, "last_error": None},
            CODEX_STATUS={"auth_error": False, "last_error": None},
            GEMINI_STATUS=gstatus,
            _summary_memo={"key": None, "value": None},
            _time=SimpleNamespace(time=lambda: 0.0),
            F_SUMMARY="F", F_SUMMARY_SUB="FS",
            astr=lambda v, font=None: _Text(v),
            _stable_w=lambda v, font=None: 7.0 * len(str(v)),
            roam_summary=lambda *_a, **_k: claude)
        gui_functions(self, ("roam_summary_text",), scope)
        self.last_state = state
        out = [scope["roam_summary_text"]()]
        for _ in range(calls - 1):
            if between:
                between(state, gstatus)
            out.append(scope["roam_summary_text"]())
        return out if calls > 1 else out[0]

    CLAUDE = ("exact", [("Session", 10.0, False, None)])
    CODEX = ("exact", [("Weekly", 20.0, False, None)])
    GEM = ("exact", [("Gemini", 75.0, False, "2h 30m")])

    def test_provider_order_is_claude_codex_gemini(self):
        """Rivals: Gemini 를 루프에 안 넣음(블록 없음); Gemini 를 맨 앞에; 훅을 부르지 않음."""
        blocks, _w, _h = self.run_adapter(claude=self.CLAUDE, codex=self.CODEX, gemini=self.GEM)
        self.assertEqual([pid for pid, _lines in blocks], ["claude", "codex", "gemini"])

    def test_a_gemini_only_user_sees_only_the_gemini_block(self):
        """Claude·Codex 를 끄고 Gemini 만. Rival: 'no_providers'(설정에서 켜라는 문구)를 띄움."""
        blocks, _w, _h = self.run_adapter(gemini=self.GEM, show=("gemini",))
        self.assertEqual([pid for pid, _lines in blocks], ["gemini"])

    def test_a_shown_gemini_with_nothing_yet_is_not_no_providers(self):
        """Claude·Codex 를 끄고 Gemini 만 켰는데 아직 행이 없다 → 'scanning'(받은 뒤)이지
        'no_providers' 가 아니다. 셋 다 끄면 'no_providers'.
        Rival: no_providers 조건이 show_claude·show_codex 만 봄."""
        blocks, _w, _h = self.run_adapter(gemini=None, show=("gemini",))
        texts = [txt for _pid, lines in blocks for line in lines for txt, _k in line]
        self.assertNotIn(claude_pet.t("no_providers"), texts)
        blocks, _w, _h = self.run_adapter(gemini=None, show=())
        texts = [txt for _pid, lines in blocks for line in lines for txt, _k in line]
        self.assertIn(claude_pet.t("no_providers"), texts)

    def test_new_gemini_rows_or_status_refresh_the_memo(self):
        """같은 5초 창 안에서도 Gemini 행(`state["gemini"]`)이 바뀌면 다시 만든다(Codex 의
        id(state["codex"]) 와 같은 규칙). v4: Gemini 에는 상태 구간이 없으므로 GEMINI_STATUS 는 메모에
        들 필요가 없다 — 그 절반은 뺐다.
        Rival: 메모 키에 Gemini 를 넣지 않음(최대 5초 동안 옛 값)."""
        holder = {"pct": 75.0}

        def gem():
            return ("exact", [("Gemini", holder["pct"], False, None)])

        def change_rows(state, _status):
            holder["pct"] = 33.0
            state["gemini"] = [("gemini", 33.0, None, None)]

        first, second = self.run_adapter(gemini=gem, show=("gemini",), calls=2,
                                         gemini_rows=[("gemini", 75.0, None, None)],
                                         between=change_rows)
        self.assertNotEqual(first[0], second[0], "Gemini 행이 바뀌었는데 메모가 옛 값을 줬다")

    # ── v3: Claude 온보딩 안내를 Gemini 수치가 누른다 (Codex 와 같은 규칙) ──

    def _global_keys(self, blocks):
        """마크 없는 전역 줄(pid None)의 글자들."""
        return [txt for pid, lines in blocks if pid is None for line in lines for txt, _k in line]

    def _click(self):
        return claude_pet.summary_click_action(status_key=self.last_state.get("summary_status"),
                                               in_pill=True, click_count=1, moved=False)

    def test_gemini_numbers_suppress_the_claude_onboarding_line_and_its_click(self):
        """Claude Code 없이 agy 만 쓰는 사용자: Gemini 구간이 수치로 떠 있으면 Claude 온보딩 안내
        (onb_install / onb_login)는 전역 줄로 나오지 않고, 필 클릭은 Claude 설치·로그인으로 가지 않는다
        (state["summary_status"] 가 None).
        Rivals: 63d5420(Codex 만 봄 — "Gemini 82%" 위에 "Claude Code 설치…" 가 붙고 필을 누르면 설치
        터미널이 열림); 줄은 숨기고 클릭 뜻은 남김(안 보이는 문구의 유령 클릭); 클릭 뜻만 지움."""
        for key, act in (("onb_install", "install"), ("onb_login", "login")):
            with self.subTest(status=key):
                blocks, _w, _h = self.run_adapter(claude=("status", key), gemini=self.GEM)
                self.assertEqual([pid for pid, _lines in blocks], ["gemini"])
                self.assertNotIn(claude_pet.t(key), self._global_keys(blocks))
                self.assertIsNone(self.last_state.get("summary_status"))
                self.assertIsNone(self._click())
                # 대조: Gemini 수치가 없으면 안내와 클릭 뜻이 그대로 있다.
                blocks, _w, _h = self.run_adapter(claude=("status", key), gemini=None)
                self.assertIn(claude_pet.t(key), self._global_keys(blocks))
                self.assertEqual(self._click(), act)

    def test_a_gemini_status_or_other_claude_statuses_are_not_suppressed(self):
        """넘치지 않는다(v3 계약 2: "Gemini 구간이 status 가 아닌 수치로 떠 있으면"): Gemini 구간이 **상태**면
        — 수치가 아니다 — 온보딩 안내는 그대로다. 여기서는 훅이 주는 합성 상태 구간으로 본다(Gemini 가
        실제로 어떤 상태 구간을 내는지는 로그인 계약이 정한다 — 그 계약은 협의 중이고, 이 규칙은 그것과
        무관하다). 온보딩이 아닌 Claude 상태(token_expired)는 Gemini 수치가 있어도 그대로 보이고 클릭 뜻도
        남는다. Codex 수치로 누르던 것은 그대로 누른다.
        **63d5420 에서도 초록이다** — 억제를 Gemini 로 넓히는 구현을 가르는 가드다. Rivals: Gemini 구간이
        참이기만 하면 누름(수치 없는 Gemini 사용자에게서 Claude 안내까지 사라짐); Gemini 수치가 있으면
        Claude 의 모든 상태를 누름(토큰 만료가 안 보임); Codex 조건을 Gemini 로 바꿔치움."""
        blocks, _w, _h = self.run_adapter(claude=("status", "onb_install"),
                                          gemini=("status", "gemini_synthetic_status"))
        self.assertIn(claude_pet.t("onb_install"), self._global_keys(blocks))
        self.assertEqual(self._click(), "install")
        blocks, _w, _h = self.run_adapter(claude=("status", "token_expired"), gemini=self.GEM)
        self.assertIn(claude_pet.t("token_expired"), self._global_keys(blocks))
        self.assertEqual(self._click(), "recover")
        blocks, _w, _h = self.run_adapter(claude=("status", "onb_install"), codex=self.CODEX,
                                          gemini=None)
        self.assertEqual([pid for pid, _lines in blocks], ["codex"])
        self.assertIsNone(self._click())

    def test_the_mac_hook_and_refresh_are_wired(self):
        """run_gui 의 `state["gemini_summary"]` 는 gemini_summary_segment 를 RUNTIME·state["gemini"]·
        GEMINI_STATUS 로 부르고 provider_spiking 을 부르지 않는다(급증 없음). 새로고침 워커는
        fetch_gemini_usage 에 닿는다.
        Rivals: 훅 없음; 훅이 Codex 행을 넘김; 워커가 Gemini 를 가져오지 않음(행이 영영 None)."""
        run_gui = _run_gui_tree()
        hooks = [n.value for n in ast.walk(run_gui)
                 if isinstance(n, ast.Assign) and len(n.targets) == 1
                 and isinstance(n.targets[0], ast.Subscript)
                 and isinstance(n.targets[0].slice, ast.Constant)
                 and n.targets[0].slice.value == "gemini_summary"]
        self.assertEqual(len(hooks), 1, 'state["gemini_summary"] 훅이 정확히 하나여야 한다')
        hook = hooks[0]
        self.assertIn("gemini_summary_segment", _called_names(hook))
        self.assertNotIn("provider_spiking", _called_names(hook))
        self.assertIn("gemini", _str_consts(hook))
        self.assertIn("GEMINI_STATUS", _names(hook))
        refresh = _nested(run_gui, "refresh_")
        self.assertIsNotNone(refresh)
        self.assertIn("fetch_gemini_usage", _reachable_module_calls(refresh))


# ═════════════════════════════ 5. 마크 ═════════════════════════════


class GeminiLogoTests(unittest.TestCase):

    def test_the_gemini_mark_is_declared_and_is_a_real_svg_in_logos(self):
        """`SUMMARY_LOGO_FILES["gemini"] == "gemini.svg"` 이고 그 파일이 logos/ 의 일반 SVG 다.
        번들·릴리즈 게이트(setup.py 의 logos 리소스, build_app.sh copy_logos, verify_release_artifact
        의 SUMMARY_LOGO_FILES 순회)는 이 표를 그대로 돌므로 따로 손댈 곳이 없다 — 여기서는 표와
        파일만 고정한다. Rivals: 표에 안 넣음(마크 없는 블록); 파일을 안 넣음(번들에서 조용히 빠짐);
        PNG 등 다른 형식."""
        mapping = claude_pet.SUMMARY_LOGO_FILES
        self.assertEqual(mapping.get("gemini"), "gemini.svg")
        path = ROOT / claude_pet.SUMMARY_LOGO_DIR / "gemini.svg"
        self.assertTrue(path.is_file() and not path.is_symlink(), f"{path} 가 없다")
        head = path.read_bytes()[:512].lstrip()
        self.assertTrue(head.startswith(b"<?xml") or head.startswith(b"<svg"))


# ═════════════════════════════ 7. 설정 창 (AST) ═════════════════════════════


class GeminiSettingsPanelTests(unittest.TestCase):

    def test_the_panel_has_a_gemini_section_with_three_gauge_boxes(self):
        """open_settings: 구역 제목 `s_sec_gemini`, 표시 토글이 `show_gemini` 를 쓰고, 게이지 체크박스는
        GEMINI_GAUGES 를 돈다(셋 — 이름을 따로 적지 않는다). ui 에 둘을 남긴다.
        Rivals: 구역 없음; 체크박스를 CODEX_GAUGES 로; 게이지 이름을 손으로 적어 GEMINI_GAUGES 와
        어긋남."""
        open_settings = _nested(_run_gui_tree(), "open_settings")
        self.assertIsNotNone(open_settings)
        self.assertIn("s_sec_gemini", _t_keys(open_settings))
        self.assertIn("show_gemini", _str_consts(open_settings))
        self.assertIn("GEMINI_GAUGES", _names(open_settings))
        self.assertNotIn("s_gauge_models", _t_keys(open_settings),
                         "설정 창에 v1 의 모델별 체크박스 제목이 남아 있다")
        self.assertEqual(_require("GEMINI_GAUGES"), ("gemini", "limits", "group"))

    def test_save_settings_sends_show_gemini_and_gemini_gauges(self):
        """save_settings 의 폼이 두 키를 싣는다(그래야 plan_settings_save 가 저장한다).
        Rival: 패널은 그렸지만 저장 폼에 안 실음(체크해도 저장 안 됨)."""
        save = _nested(_run_gui_tree(), "save_settings")
        self.assertIsNotNone(save)
        consts = _str_consts(save)
        for key in ("show_gemini", "gemini_gauges"):
            with self.subTest(key=key):
                self.assertIn(key, consts)


# ═════════════════════════════ v4: 우클릭 메뉴 "Gemini 로그인(agy)" ═════════════════════════════


class GeminiLoginMenuTests(_Guard):
    """Codex 의 설치·로그인 항목과 같은 방식(state 깃발 → rightMouseDown_ → Handler → Terminal 도우미).
    이 파일이 거는 이름: TR `menu_gemini_login`, state["gemini_onboard"], 액션 "loginGemini:",
    Handler.loginGemini_, 모듈 함수 `start_gemini_login`. 깃발이 실제로 오르는 것은
    tests/test_gemini_agy_cadence.py(RefreshPathTests)가 본다."""

    def test_the_context_menu_offers_the_gemini_login_item_from_its_flag(self):
        """rightMouseDown_ 이 state["gemini_onboard"] 를 읽어 t("menu_gemini_login") 항목을 "loginGemini:"
        로 달고, Handler.loginGemini_ 가 설치·로그인 흐름(start_ai_connect 또는 run_ai_connect, "gemini")으로
        간다. v7-I1: 우클릭의 로그인 안내도 터미널 대신 이 흐름을 쓴다 — start_gemini_login(Terminal)을 부르지
        않는다(자세한 것은 tests/test_cli_install_login.py).
        Rivals: 항목 없음(로그인하라는 말이 어디에도 없다); 깃발 없이 늘 보임; 핸들러가 Codex 도우미를 부름;
        여전히 Terminal 을 엶."""
        run_gui = _run_gui_tree()
        menu = _nested(run_gui, "rightMouseDown_")
        self.assertIsNotNone(menu)
        self.assertIn("menu_gemini_login", _t_keys(menu))
        self.assertLessEqual({"loginGemini:", "gemini_onboard"}, _str_consts(menu))
        fn = _nested(run_gui, "loginGemini_")
        self.assertIsNotNone(fn, "Handler.loginGemini_ 가 없다")
        called = _called_names(fn)
        self.assertTrue({"start_ai_connect", "run_ai_connect"} & set(called),
                        "loginGemini_ 가 설치·로그인 흐름으로 가지 않는다")
        self.assertNotIn("start_gemini_login", called)
        self.assertIn("gemini", _str_consts(fn))

    def test_the_login_helper_opens_agy_itself_in_terminal(self):
        """start_gemini_login 은 Terminal 에서 agy 를 연다(사용자가 직접 로그인한다). 아무것도 실행하지
        않는다: `_run_in_terminal` 은 기록기다.
        v8-G1(2026-11-19): 창에서 실행하는 것은 `agy -p "/usage" --output-format json` 이다 — 인자 없는
        `agy`(TUI)는 대체 화면으로 바뀌어 맨 위 안내를 가린다. 자세한 것은 tests/test_v8_fixes.py.
        Rivals: 인자 없는 agy; `agy login`(그런 명령은 없다); 앱이 직접 agy 를 띄움(숨은 프로세스로 OAuth)."""
        login = _require("start_gemini_login")
        seen = []
        path_before = os.environ.get("PATH")
        with mock.patch.object(claude_pet, "_run_in_terminal", side_effect=seen.append), \
                mock.patch.object(claude_pet.subprocess, "run",
                                  side_effect=AssertionError("프로세스를 띄웠다")), \
                mock.patch.object(claude_pet.subprocess, "Popen",
                                  side_effect=AssertionError("프로세스를 띄웠다")):
            login()
        self.assertEqual(len(seen), 1)
        lines = [ln.strip().strip("\"'") for ln in str(seen[0]).splitlines()]
        del lines
        self.assertRegex(seen[0], r"agy\S*\s+-p\s+\S*/usage", "Terminal 명령이 `agy -p /usage` 를 실행하지 않는다")
        self.assertNotIn("agy login", seen[0])
        # v5-1: 가짜 open 은 백그라운드 실행에만 둔다 — 사용자가 고른 로그인에서는 브라우저가 열려야 한다.
        # Terminal 명령에 나오는 어느 폴더에도 `open` 이 없고(PATH 에 가짜 open 폴더를 넣지 않았다),
        # `open` 을 가리거나 다시 정의하지도 않는다. 앱의 PATH 도 그대로다.
        self.assertEqual(os.environ.get("PATH"), path_before, "앱 자신의 PATH 를 바꿨다")
        import re as _re
        for folder in set(_re.findall(r"/[^\s\"':;$]+", seen[0])):
            self.assertFalse(os.path.lexists(os.path.join(folder, "open")),
                             "로그인 명령의 PATH 에 `open` 을 가진 폴더가 있다: %r" % folder)
        self.assertIsNone(_re.search(r"(alias\s+open\b|\bopen\s*\(\)|function\s+open\b)", seen[0]),
                          "로그인 명령이 open 을 가렸다: %r" % seen[0])


# ═════════════════════════════ 9. Windows 포트 ═════════════════════════════


def _port_tree():
    return ast.parse(PORT.read_text(encoding="utf-8"))


def _port_method(name):
    cls = next(n for n in _port_tree().body if isinstance(n, ast.ClassDef) and n.name == "PetWindow")
    found = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[0] if found else None


class GeminiWindowsPortTests(_Guard):

    def test_the_port_adapter_survives_and_shows_no_gemini_block_without_rows(self):
        """**회귀 가드 — 게이트가 아니다.** Coordinator 결정(2차): Windows 에는 아직 Gemini 리더가
        없으니 고정하는 것은 '포트가 죽지 않고, 행이 None 이면 Gemini 블록이 없다' 뿐이다. 그래서
        이 테스트는 구현 전에도 초록이다(AGENTS.md §3 — 빨강을 본 적 없는 테스트는 아무것도
        증명하지 않는다; 여기서는 앞으로 포트에 훅을 붙이다 None 에서 죽는 회귀만 잡는다).
        포트의 PetWindow.roam_summary_text 를 가짜 self 로 돌린다(PySide6 없이). state 에는
        Gemini 행 None 과, None 을 주는 gemini_summary 훅이 있다.
        Rival(잡는 것): 포트가 훅 결과나 state["gemini"] 를 None 검사 없이 풀다 죽음; None 에서
        빈 Gemini 블록·'조회 중' 블록을 만듦."""
        fn_node = _port_method("roam_summary_text")
        self.assertIsNotNone(fn_node)
        scope = {"cp": claude_pet, "datetime": datetime, "timezone": timezone,
                 "time": SimpleNamespace(time=lambda: 0.0)}
        exec(compile(ast.Module(body=[fn_node], type_ignores=[]), str(PORT), "exec"), scope)
        method = scope["roam_summary_text"]
        claude_pet.RUNTIME.update(_rt(show_claude=False, show_codex=True, show_gemini=True,
                                      mode="sub"))
        claude_pet.L["lang"] = "en"
        codex = ("exact", [("Weekly", 20.0, False, None)])
        for name, seg, want in (("none", None, ["codex"]),):
            with self.subTest(gemini=name):
                state = {"stats": {"spikes": {}}, "oauth": None, "cost": None,
                         "cost_month": None, "onboard": None, "credit_text": None,
                         "codex": None, "gemini": None, "api_error": False,
                         "api_stale": False, "summary_lines_n": 2,
                         "codex_summary": lambda: codex,
                         "gemini_summary": (lambda s=seg: s)}
                fake = SimpleNamespace(
                    state=state, F_SUMMARY="F", F_SUMMARY_SUB="FS",
                    _text_w=lambda v, font=None: 7.0 * len(str(v)),
                    _stable_w=lambda v, font=None: 7.0 * len(str(v)),
                    _pill_budget_for=lambda need: 10000.0)
                with mock.patch.object(claude_pet, "GEMINI_STATUS",
                                       {"auth_error": False, "last_error": None}, create=True):
                    blocks, _w, _h = method(fake)
                self.assertEqual([pid for pid, _lines in blocks], want)


if __name__ == "__main__":
    unittest.main()
