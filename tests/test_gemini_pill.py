"""Gemini 필·설정 게이팅 테스트 — TOK-47(릴리즈 1.2.0, macOS 먼저), Verifier 작성, 구현 전.

작성 시점에 전부 빨강이어야 한다(AGENTS.md §3). 빨강은 ImportError 가 아니라 `_require` 의
AssertionError 이거나 단언 실패여야 한다 — '무엇이 없는지'가 메시지에 남는다.

TOK-44 의 함수(`fetch_gemini_usage`, `parse_gemini_quota`, `GEMINI_STATUS`)는 있다고 가정한다.
여기서는 그 **행**을 직접 만들어 넣는다 — 행 모양은 TOK-44 계약 그대로
`(label, pct, reset_dt, reset_text)`, 라벨은 `gemini` / `gemini:<modelId>` /
`gemini_group:<bucketId>`. 네트워크·키체인·`~/.gemini` 에는 닿지 않는다(호출조차 하지 않는다).

── 계약 (Coordinator, TOK-47) ────────────────────────────────────────────────────────

1. 설정: RUNTIME 기본값 `"show_gemini": True`, `"gemini_gauges": ["gemini"]`;
   `GEMINI_GAUGES = ("gemini", "models", "group")`; codex_gauges 처럼 `_gauge_list` 로 검증·저장,
   다른 제공자 키처럼 병합.
2. `provider_shown(runtime, "gemini")` 는 `show_gemini` 를 따른다.
3. `gemini_summary_segment(runtime, rows, …)` (codex_summary_segment 의 짝): 게이지 "gemini" →
   0행, "models" → 모든 `gemini:` 행, "group" → 모든 `gemini_group:` 행. rows None → None(블록
   없음, 0% 금지). GEMINI_STATUS 의 auth_error/expired → 상태 구간 `gemini_expired`.
   (Coordinator 결정: 만료는 auth_error=True 도 올린다 — 그래서 이 파일은 Codex 처럼
   `auth_error=` 키워드로 넘기고, GEMINI_STATUS 도 같은 값으로 맞춰 둔다. 어느 쪽을 읽든 통과.)
4. 화면 라벨: 0행 "Gemini"(TR `gemini`, 모든 로케일 같음); 모델 행은 modelId 에서 `gemini-` 를
   떼고 `-` → 공백, 알파벳 단어만 첫 글자 대문자(`gemini-2.5-flash-lite` → `2.5 Flash Lite`);
   그룹 행은 summary 버킷의 window("5h"/"weekly")에 따라 TR `gemini_group_5h` /
   `gemini_group_weekly` — ko "Claude·GPT 5시간"/"Claude·GPT 주간". 리셋은 다른 제공자처럼
   카운트다운.
   (Coordinator 결정 2026-11-18, 2차) window 는 bucketId 에서 읽지 않는다: TOK-44 의
   `parse_gemini_quota` 가 서버의 window 를 모듈 표 `GEMINI_GROUP_WINDOWS = {bucketId: window}`
   (CODEX_WINDOWS 와 같은 꼴)에 적고, 구간은 그 표를 본다. 모르는 window 면 라벨은 그냥
   "Claude·GPT"(TR `gemini_group`). 주간 라벨의 대소문자는 그 로케일의 `t("weekly")` 와 같다
   (en "Claude·GPT Weekly" — 한 필 안에 "Weekly"/"weekly" 가 섞이지 않게). 잘못된 gemini_gauges
   (목록이 아님)는 ["gemini"] 로.
5. 필: 제공자 순서 claude, codex, gemini; Gemini 블록은 자기 마크
   `SUMMARY_LOGO_FILES["gemini"] = "gemini.svg"`; roam_summary_text 루프가 gemini 를 포함한다
   (codex_summary 같은 state 훅).
6. 설정 구역·게이지·상태의 TR 키가 네 로케일에 모두 있다.
7. 설정 창: Gemini 구역(표시 토글 + 게이지 체크박스 셋), 저장 트랜잭션이 show_gemini /
   gemini_gauges 를 저장한다.
8. Gemini 에는 급증 감지가 없다.
9. Windows 포트: Windows 에는 아직 리더가 없다(fetch → None). 고정하는 것은 포트가 죽지 않고
   행이 None 이면 Gemini 블록을 내지 않는다는 것뿐이다(Coordinator 결정, 2차) — 회귀 가드.

── 이 파일이 Developer 에게 거는 이름 (계약에 없던 것, Verifier 제안) ───────────────────────

  · Gemini 행은 `state["gemini"]` 에 둔다(Codex 의 `state["codex"]` 와 같은 자리). 훅은
    `state["gemini_summary"]`.
  · 설정 구역 제목 TR 키는 `s_sec_gemini`(Claude·Codex 의 `s_sec_claude`/`s_sec_codex` 와 같은 꼴).
  · 그룹 행의 window 는 `GEMINI_GROUP_WINDOWS` 에서 온다(위). 이 파일의 bucketId 는 일부러
    window 를 이름에 담지 않거나(`3p-a`) 반대로 담는다(`x-weekly` 인데 window 는 5h) —
    bucketId 접미사를 읽는 구현을 가른다.
"""

import ast
import contextlib
import os
import re
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
MODELS = [
    ("gemini:gemini-2.5-flash", 60.0, R_FLASH, None),
    ("gemini:gemini-2.5-flash-lite", 10.0, None, None),
    ("gemini:gemini-3-flash", 75.0, R_HEAD, None),
]
# 서버 순서 그대로: weekly 가 먼저다(2026-11-18 관측 응답도 그랬다). 순서로 라벨을 붙이는
# 구현(첫째 = 5h)을 가른다.
GROUPS = [
    ("gemini_group:3p-a", 10.0, R_WEEK, None),        # window weekly — 이름에 없다
    ("gemini_group:x-weekly", 90.0, R_5H, None),      # window 5h — 이름이 거짓말을 한다
]
GROUP_WINDOWS = {"3p-a": "weekly", "x-weekly": "5h"}

ALL_ROWS = [HEAD] + MODELS + GROUPS

MODEL_TEXT = {"gemini:gemini-2.5-flash": "2.5 Flash",
              "gemini:gemini-2.5-flash-lite": "2.5 Flash Lite",
              "gemini:gemini-3-flash": "3 Flash"}


def _rt(**over):
    rt = {"show_claude": True, "claude_gauges": ["session", "weekly"],
          "show_codex": True, "codex_mode": "sub", "codex_gauges": ["session", "weekly"],
          "show_gemini": True, "gemini_gauges": ["gemini"]}
    rt.update(over)
    return rt


def _segment(test, rt, rows, auth_error=False, last_error=None, lang="en", windows=None):
    """gemini_summary_segment 를 한 번. GEMINI_STATUS 도 같은 상태로 맞추고, 그룹 window 표를 이
    테스트의 값으로 준다. 표가 구간에 닿는 길은 정하지 않는다(리뷰 2차 R2-4 — 조회 경로가 나른다):
    모듈 표 GEMINI_GROUP_WINDOWS 로도 두고, 구간이 `windows` 인자를 받으면 그것으로도 넘긴다."""
    import inspect
    fn = _require("gemini_summary_segment")
    claude_pet.L["lang"] = lang
    status = {"auth_error": bool(auth_error), "last_error": last_error}
    table = dict(GROUP_WINDOWS if windows is None else windows)
    kw = {"auth_error": auth_error}
    try:
        if "windows" in inspect.signature(fn).parameters:
            kw["windows"] = dict(table)
    except (TypeError, ValueError):
        pass
    with mock.patch.object(claude_pet, "GEMINI_STATUS", status, create=True), \
            mock.patch.object(claude_pet, "GEMINI_GROUP_WINDOWS", table, create=True):
        return fn(rt, rows, **kw)


def _en_group(window):
    """en 그룹 라벨의 기대값 — 주간은 앱의 t("weekly") 표기를 그대로 쓴다(Coordinator 결정 2)."""
    tr = claude_pet.TR["en"]
    return {"5h": "Claude·GPT 5h", "weekly": "Claude·GPT " + tr["weekly"],
            None: "Claude·GPT"}[window]


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
        Rivals: 세 게이지를 다 켬(모델 행이 기본으로 쏟아짐); show_gemini 기본 False;
        GEMINI_GAUGES 순서·이름이 다름(체크박스와 필터가 같은 이름을 써야 한다)."""
        self.assertEqual(_require("GEMINI_GAUGES"), ("gemini", "models", "group"))
        d = _runtime_literal_defaults()
        self.assertIs(d.get("show_gemini"), True)
        self.assertEqual(d.get("gemini_gauges"), ["gemini"])

    def test_the_keys_are_loaded_owned_and_normalised_like_codex(self):
        """apply_config 가 두 키를 읽고, 손으로 고친 값을 Codex 처럼 정규화한다("false" → False,
        모르는 게이지는 버림). 설정 창이 소유하는 키이기도 하다.
        Rivals: _RUNTIME_CONFIG_KEYS 에 빠뜨림(저장해도 재시작하면 기본값); 정규화 루프가
        ("claude", "codex") 그대로라 문자열 "false" 가 참으로 남음."""
        _require("GEMINI_GAUGES")
        for key in ("show_gemini", "gemini_gauges"):
            with self.subTest(key=key):
                self.assertIn(key, claude_pet._RUNTIME_CONFIG_KEYS)
                self.assertIn(key, claude_pet.SETTINGS_OWNED_KEYS)
        claude_pet.apply_config({"show_gemini": "false", "gemini_gauges": ["group", "nope", "models"],
                                 "lang": claude_pet.L["lang"]})
        self.assertIs(claude_pet.RUNTIME.get("show_gemini"), False)
        self.assertEqual(claude_pet.RUNTIME.get("gemini_gauges"), ["models", "group"])

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
            ("filtered", {"show_gemini": 1, "gemini_gauges": ["group", "bogus", "gemini"]},
             True, ["gemini", "group"]),
            ("empty", {"show_gemini": 0, "gemini_gauges": []}, False, []),
        )
        for name, extra, show, gauges in cases:
            with self.subTest(case=name):
                plan, err = claude_pet.plan_settings_save({}, dict(form, **extra))
                self.assertIsNone(err)
                self.assertIs(plan["updates"].get("show_gemini"), show)
                self.assertEqual(plan["updates"].get("gemini_gauges"), gauges)
        base = {"show_gemini": False, "gemini_gauges": ["models"]}
        plan, err = claude_pet.plan_settings_save(base, form)
        self.assertIsNone(err)
        self.assertIs(plan["updates"].get("show_gemini"), False)
        self.assertEqual(plan["updates"].get("gemini_gauges"), ["models"])

    def test_provider_shown_honours_show_gemini_and_its_gauges(self):
        """Rivals: provider_gauges 가 claude 가 아니면 CODEX_GAUGES 로 거름(그러면 "models"·"group"
        만 고른 사용자는 Gemini 가 통째로 숨는다); show_gemini 를 안 봄; 문자열 "false" 를 참으로."""
        _require("GEMINI_GAUGES")
        shown = claude_pet.provider_shown
        self.assertTrue(shown(_rt(), "gemini"))
        self.assertTrue(shown(_rt(gemini_gauges=["models"]), "gemini"))
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

    def test_each_gauge_selects_its_own_rows_in_row_order(self):
        """게이지별 행. 라벨은 화면 문자열이다(en).
        Rivals: "gemini" 게이지가 모델 행까지 냄; "models" 가 0행을 포함; 그룹 행을 모델 게이지에;
        모르는 라벨(gemini_other)을 살림; 고른 게이지 순서로 행을 재배열."""
        groups = [_en_group("weekly"), _en_group("5h")]
        expect = {
            ("gemini",): ["Gemini"],
            ("models",): [MODEL_TEXT[r[0]] for r in MODELS],
            ("group",): groups,
            ("group", "gemini"): ["Gemini"] + groups,
            ("gemini", "models", "group"): ["Gemini"] + [MODEL_TEXT[r[0]] for r in MODELS] + groups,
        }
        rows = ALL_ROWS + [("gemini_other", 5.0, None, None)]
        for gauges, labels in expect.items():
            with self.subTest(gauges=gauges):
                seg = _segment(self, _rt(gemini_gauges=list(gauges)), list(rows))
                self.assertIsNotNone(seg)
                self.assertEqual(seg[0], "exact")
                self.assertEqual(_labels(seg), labels)
        seg = _segment(self, _rt(gemini_gauges="broken"), list(rows))
        self.assertEqual(_labels(seg), ["Gemini"], "망가진 게이지 값은 0행만(기본값)")

    def test_model_labels_drop_the_prefix_and_capitalise_alphabetic_words(self):
        """`gemini-` 를 떼고 `-` → 공백, **알파벳 단어만** 첫 글자 대문자. 숫자·혼합 토큰은 그대로.
        Rivals: 접두사 유지("Gemini 2.5 …"); 하이픈 유지; 첫 단어만 대문자(capitalize);
        전부 대문자; str.title()("1m" → "1M" — 알파벳 단어가 아니다); 행 라벨 원문."""
        cases = (("gemini-2.5-flash-lite", "2.5 Flash Lite"),
                 ("gemini-3-flash", "3 Flash"),
                 ("gemini-2.5-pro", "2.5 Pro"),
                 ("gemini-3.1-flash-image", "3.1 Flash Image"),
                 ("gemini-3.8-flash-tiered", "3.8 Flash Tiered"),
                 ("gemini-3-pro-1m", "3 Pro 1m"))
        for model, text in cases:
            with self.subTest(model=model):
                seg = _segment(self, _rt(gemini_gauges=["models"]),
                               [("gemini:" + model, 20.0, None, None)])
                self.assertIsNotNone(seg)
                self.assertEqual(_labels(seg), [text])

    def test_group_labels_follow_the_server_window_not_the_bucket_id(self):
        """그룹 라벨은 GEMINI_GROUP_WINDOWS[bucketId] 의 window 로 고른다 — bucketId 를 읽지 않는다.
        `3p-a`(이름에 window 없음, 실제 weekly), `x-weekly`(이름은 weekly, 실제 5h), 표에 없는
        `y-5h`·window 가 모르는 값인 `z` → "Claude·GPT"(TR `gemini_group`).
        ko 는 계약 문구 그대로, en 주간은 앱의 t("weekly") 표기("Weekly")를 그대로.
        Rivals: bucketId 접미사 파싱(3p-a 를 모름, x-weekly 를 주간으로, y-5h 를 5h 로); 서버
        순서로 붙임(첫째 = 5h); bucketId·displayName 원문; en 소문자 "weekly"(한 필 안에
        "Weekly 17%" 와 "…weekly 30%" 가 섞인다 — TR 의 codex_* 파생 주석이 버그로 적은 모양)."""
        rows = list(GROUPS) + [("gemini_group:y-5h", 20.0, None, None),
                               ("gemini_group:z", 30.0, None, None)]
        windows = dict(GROUP_WINDOWS, z="monthly")
        ko = _segment(self, _rt(gemini_gauges=["group"]), rows, lang="ko", windows=windows)
        self.assertIsNotNone(ko)
        self.assertEqual(_labels(ko), ["Claude·GPT 주간", "Claude·GPT 5시간",
                                       claude_pet.TR["ko"].get("gemini_group", "<gemini_group 없음>"),
                                       claude_pet.TR["ko"].get("gemini_group", "<gemini_group 없음>")])
        en = _segment(self, _rt(gemini_gauges=["group"]), rows, lang="en", windows=windows)
        self.assertEqual(_labels(en), [_en_group("weekly"), _en_group("5h"),
                                       _en_group(None), _en_group(None)])

    def test_parse_gemini_quota_is_pure(self):
        """리뷰 2차 R2-4: parse_gemini_quota(quota, summary) 는 모듈 상태를 바꾸지 않는다 —
        GEMINI_GROUP_WINDOWS 도, 그 밖의 어떤 모듈 수준 dict·list·set 도. 같은 입력이면 같은 출력이다.
        window 가 라벨까지 가는 길은 조회 경로다(tests/test_gemini_keychain_quiet.py 의
        test_group_labels_follow_the_server_window_through_the_fetch_path).
        Rival: 8eb4ccb — 파서가 GEMINI_GROUP_WINDOWS[bucketId] = window 를 적는다(같은 파서를 다른 곳에서
        부르면 필의 라벨이 바뀐다)."""
        parse = _require("parse_gemini_quota")
        summary = {"groups": [{"displayName": "Claude and GPT models", "buckets": [
            {"bucketId": "q-1", "window": "weekly", "resetTime": "2026-11-25T03:45:42Z",
             "remainingFraction": 0.9},
            {"bucketId": "q-2", "window": "5h", "resetTime": "2026-11-18T08:45:42Z",
             "remainingFraction": 0.1}]}]}
        quota = {"buckets": [{"modelId": "gemini-3-flash", "tokenType": "WTUS",
                              "remainingFraction": 0.25, "resetTime": "2026-11-18T08:45:41Z"}]}

        def snapshot():
            return {name: repr(value) for name, value in vars(claude_pet).items()
                    if isinstance(value, (dict, list, set)) and not name.startswith("__")}

        before = snapshot()
        first = parse(quota, summary)
        changed = sorted(k for k, v in snapshot().items() if before.get(k) != v)
        self.assertEqual(changed, [], "parse_gemini_quota 가 모듈 상태를 바꿨다: %r" % changed)
        self.assertEqual(parse(quota, summary), first)
        self.assertEqual([r[0] for r in first or ()][-2:], ["gemini_group:q-1", "gemini_group:q-2"])

    def test_values_resets_and_no_spike_mark(self):
        """pct 는 float 그대로, 리셋은 지금 기준 카운트다운(fmt_countdown 과 같은 문자열), 리셋이
        없으면 None, ▲ 표식(세 번째 칸)은 언제나 False — Gemini 에는 급증 감지가 없다(계약 8).
        Rivals: reset_text(None)를 그대로 써서 카운트다운이 사라짐; 리셋 없음에 "-";
        Claude/Codex 의 급증을 옮겨 닮; pct 를 정수로 반올림."""
        seg = _segment(self, _rt(gemini_gauges=["gemini", "models"]), [HEAD] + MODELS)
        self.assertIsNotNone(seg)
        payload = seg[1]
        now = datetime.now(UTC)
        want = [(75.0, claude_pet.fmt_countdown(R_HEAD, now)),
                (60.0, claude_pet.fmt_countdown(R_FLASH, now)),
                (10.0, None),
                (75.0, claude_pet.fmt_countdown(R_HEAD, now))]
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
        다른 게이지 행으로 채움; 일시 실패(http:500)를 만료로 보임."""
        cases = (("None", None, ["gemini"], None),
                 ("empty", [], ["gemini"], None),
                 ("filtered away", list(MODELS), ["group"], None),
                 ("unknown labels", [("gemini_other", 5.0, None, None)], ["gemini"], None),
                 ("transient failure", None, ["gemini"], "http:500"))
        for name, rows, gauges, last in cases:
            with self.subTest(case=name):
                self.assertIsNone(_segment(self, _rt(gemini_gauges=gauges), rows,
                                           auth_error=False, last_error=last))

    def test_a_rejected_or_expired_token_is_the_gemini_status_but_rows_win(self):
        """행이 없고 auth_error(401/403 또는 만료 — Coordinator 결정으로 만료도 auth_error)면
        ("status", "gemini_expired"). 행이 있으면 행이 이긴다(Codex 와 같은 규칙).
        Rivals: Codex 키 재사용(codex_token_expired); 일반 token_expired(Claude 의 문구);
        만료에서 None(사용자가 왜 안 보이는지 모름); 행이 있는데도 상태."""
        for last in ("http:401", "http:403", "expired"):
            with self.subTest(last_error=last):
                self.assertEqual(_segment(self, _rt(), None, auth_error=True, last_error=last),
                                 ("status", "gemini_expired"))
        seg = _segment(self, _rt(), [HEAD], auth_error=True, last_error="expired")
        self.assertIsNotNone(seg)
        self.assertEqual(seg[0], "exact")

    def test_hidden_gemini_has_no_block_at_all(self):
        """꺼 두었거나 게이지가 없으면 행이 있어도, 만료여도 None.
        Rival: 만료 상태를 표시 설정보다 먼저 봄(끈 제공자의 경고가 뜸)."""
        for name, rt in (("off", _rt(show_gemini=False)), ("no gauges", _rt(gemini_gauges=[]))):
            for auth in (False, True):
                with self.subTest(case=name, auth_error=auth):
                    self.assertIsNone(_segment(self, rt, list(ALL_ROWS) if not auth else None,
                                               auth_error=auth,
                                               last_error="expired" if auth else None))


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
        """`gemini` 은 모든 로케일에서 "Gemini"; `gemini_group` 은 "Claude·GPT" 로 시작하고 두 window
        라벨이 그것으로 시작한다; 주간 라벨은 그 로케일의 t("weekly") 를 그대로 품는다(대소문자
        포함); ko 는 계약 문구, en 은 "Claude·GPT 5h"/"Claude·GPT Weekly"; `gemini_expired` 는 모든
        로케일에 있고 "Gemini" 와 할 일(`agy`)을 말한다(codex_token_expired 가 `codex` 를 말하듯).
        Rivals: en 에만 넣음(t() 가 en 으로 떨어져 ko 필에 영어); "Gemini" 를 번역함;
        5h/weekly 를 같은 문구로."""
        tr = claude_pet.TR
        for lang in LANGS:
            with self.subTest(lang=lang):
                table = tr[lang]
                self.assertEqual(table.get("gemini"), "Gemini")
                base = table.get("gemini_group")
                h5, wk = table.get("gemini_group_5h"), table.get("gemini_group_weekly")
                self.assertTrue(base and h5 and wk, "그룹 라벨(gemini_group/_5h/_weekly)이 없다")
                self.assertTrue(base.startswith("Claude·GPT"))
                self.assertTrue(h5.startswith(base + " ") and wk.startswith(base + " "))
                self.assertNotEqual(h5, wk)
                self.assertIn(table["weekly"], wk,
                              "주간 그룹 라벨이 이 로케일의 t('weekly') 표기를 쓰지 않는다")
                exp = table.get("gemini_expired")
                self.assertTrue(exp and "Gemini" in exp and "agy" in exp,
                                "gemini_expired 가 없거나 Gemini·agy 를 말하지 않는다: %r" % exp)
                self.assertTrue(str(table.get("s_sec_gemini", "")).strip(),
                                "설정 구역 제목 s_sec_gemini 가 없다")
        self.assertEqual((tr["ko"].get("gemini_group_5h"), tr["ko"].get("gemini_group_weekly")),
                         ("Claude·GPT 5시간", "Claude·GPT 주간"))
        self.assertEqual((tr["en"].get("gemini_group_5h"), tr["en"].get("gemini_group_weekly")),
                         ("Claude·GPT 5h", "Claude·GPT " + tr["en"]["weekly"]))

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

    def test_gemini_expiry_is_a_gemini_block_not_dropped(self):
        """("status", "gemini_expired") 는 Gemini 블록(자기 마크)으로 보인다 — Codex 의
        codex_token_expired 와 같은 자리. Rival: 일반 status 로 보고 '없음'으로 버림(만료가 화면에
        안 보인다)."""
        blocks, _w, _h = self.run_adapter(codex=self.CODEX, gemini=("status", "gemini_expired"),
                                          show=("codex", "gemini"))
        self.assertEqual([pid for pid, _lines in blocks], ["codex", "gemini"])
        text = " ".join(txt for _pid, lines in blocks if _pid == "gemini"
                        for line in lines for txt, _k in line)
        self.assertIn("Gemini", text)

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
        """같은 5초 창 안에서도 Gemini 행(`state["gemini"]`)이나 GEMINI_STATUS 가 바뀌면 다시
        만든다(Codex 의 id(state["codex"]), CODEX_STATUS 와 같은 규칙).
        Rival: 메모 키에 Gemini 를 넣지 않음(최대 5초 동안 옛 값·옛 상태)."""
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

        status = {"auth_error": False, "last_error": None}   # 어댑터와 훅이 같은 dict 를 본다

        def gem_by_status():
            return ("status", "gemini_expired") if status["auth_error"] else None

        def expire(_state, g):
            g.update(auth_error=True, last_error="expired")

        first, second = self.run_adapter(gemini=gem_by_status, show=("codex", "gemini"),
                                         codex=self.CODEX, calls=2, status=status,
                                         between=expire)
        self.assertEqual([pid for pid, _l in first[0]], ["codex"])
        self.assertEqual([pid for pid, _l in second[0]], ["codex", "gemini"],
                         "만료로 바뀌었는데 메모가 옛 필을 줬다")

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

    def test_save_settings_sends_show_gemini_and_gemini_gauges(self):
        """save_settings 의 폼이 두 키를 싣는다(그래야 plan_settings_save 가 저장한다).
        Rival: 패널은 그렸지만 저장 폼에 안 실음(체크해도 저장 안 됨)."""
        save = _nested(_run_gui_tree(), "save_settings")
        self.assertIsNotNone(save)
        consts = _str_consts(save)
        for key in ("show_gemini", "gemini_gauges"):
            with self.subTest(key=key):
                self.assertIn(key, consts)


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
