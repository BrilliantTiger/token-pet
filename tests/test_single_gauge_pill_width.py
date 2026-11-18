"""게이지 하나짜리 요약 필의 폭 게이트 — Verifier 작성, **수정 전**(AGENTS.md §3).

── 무엇이 보고됐나 ────────────────────────────────────────────────────────────

한국어 UI, Claude 게이지는 주간 하나만 켜져 있다. 필에는 `주간 34% · 3d 10h` 한 줄이 뜨고
(게이지가 하나라 리셋이 같은 줄에 인라인된다), 오른쪽 끝 글자가 필 밖으로 나가 창에 잘려
사라진다. 접히지도 않고 말줄임표도 없다. 펫은 작은 크기였다(기본 배율 0.5).

── 이 파일이 지키는 불변식(저장소가 스스로 적은 것) ──────────────────────────

  I1  어댑터가 낸 모든 줄은 **그 줄이 그려질 필**의 글자 자리 안에 들어간다.
      필은 생산 `geom()` 의 W 로 생산 `roam_frame` / `roam_pill_rect` 가 낸 것,
      글자 자리는 필 폭 − 2·PILL_PAD − SUMMARY_LOGO_W(제공자 줄).
  I2  어댑터가 접는 데 쓴 예산은 같은 W 에서 필이 실제로 내주는 글자 자리와 같다.
  I3  필은 내용에 맞춰 넓어진다(화면이 끝) — 게이지 하나짜리 줄은 접히지 않고 한 줄이며,
      라벨·수치·남은시간을 한 글자도 잃지 않는다.
  I4  필과 글자는 창 안에 있다. 실제 NSWindow 는 논리 창의 crop(roam_frame)이라 그 밖은
      말 없이 잘린다 — 보고된 증상이 정확히 이것이다.

── 왜 기존 게이트가 못 잡았나 ────────────────────────────────────────────────

`tests/test_summary_layout.py` 의 `FoldBudgetMatchesTheActualPillTests` 는 게이지 **셋**,
`PW0=120` 에 배율 **1.0** 으로만 돈다. 그 기하에서는 W ≥ 120+2·13+16 = 162 라 글자 자리가
최소 110pt 이고, 사용자가 본 ko 주간 줄(88.84pt)이나 en 주간 줄(107.72pt)은 펫 폭 덕에
그냥 들어간다. 게다가 그 클래스의 `settle()` 은 어댑터의 `need` 계산을 **다시 적어서** 쓴다 —
인라인 **전** 첫 줄과 리셋 줄을 따로 재는 생산의 방식 그대로(그 스텁 `astr` 은 글꼴을 무시해
리셋 줄도 11pt 로 잰다) 적었으므로 생산의 측정 결함을 복제하고, 생산을 고쳐도 그 테스트의
`need` 는 따라 바뀌지 않는다.

그래서 이 파일은 **실제 `roam_summary_text` 클로저**를 `run_gui` 에서 AST 로 꺼내
(`gui_functions`) 생산의 `geom` / `_pill_text_budget` / `_apply_pill_width` /
`_pill_budget_for` / `_stable_w` 와 같은 scope 에서 돌린다. `need` → `_pill_budget_for` →
`summary_lines` → `text_w` 순서는 전부 생산 자신의 것이고, 여기서 다시 적는 식은 없다.
모듈 수준 함수(`roam_summary`, `summary_lines`, `fmt_countdown`, `t` …)는 `claude_pet`
그 자체다. 바꿔 끼운 것은 창·글꼴·시계뿐이다:

  · 글꼴: `astr` 은 번들 Pretendard SemiBold 의 실측 advance 표(test_summary_pill)로 잰다.
    11pt 는 `pretendard_width`, 9.5pt 는 `pretendard_width_sub`. macOS 동행 테스트가 이
    표를 실제 글꼴과 대조한다. 그래서 macOS·Windows CI 어디서나 같은 숫자다.
  · 펫: 내장 펫 `frames/idle/00.png` 의 IHDR 에서 읽은 192×208(번들 펫 시트 1536×2288 을
    8×11 로 나눈 셀도 같다). 손으로 적은 크기가 아니다.
  · 시계: 고정된 `datetime.now()` — 남은시간은 생산 `fmt_countdown` 이 만든다.

테스트 정책(CLAUDE.md): 실제 `~/.claude`·`~/.codex`·키체인을 읽지 않는다. 행은 전부 합성이다.

── 경쟁 구현(AGENTS.md §3) — 각 테스트 docstring 이 자기가 가르는 것을 다시 적는다 ───

  R0  지금 코드: `need` 를 인라인 **전** 줄(첫 줄 11pt, 리셋 줄 9.5pt)로 재고,
      `_pill_text_budget()` 이 예산을 SUMMARY_MIN_W(120) 로 바닥을 깐다.
  R1  예산 바닥만 없앤다(예산 = 필 글자 자리) — 필은 그대로 좁고, 줄이 접힌다.
  R2  `need` 만 고친다(인라인된 줄을 그 줄의 글꼴로 잰다 — Windows 포트가 이미 하는 방식),
      바닥은 남긴다.
  R3  리셋 줄을 11pt 로 재기만 한다(인라인은 여전히 무시).
  R4  `need` = 첫 줄 + 구분자 + 남은시간, 단 남은시간을 9.5pt 로 잰다(인라인 run 의
      kind 가 "sub" 라 run 단위로 글꼴을 고른 경우).
  R5  `roam_pill_rect` 가 화면 상한(room)을 넘어서까지 필을 키운다.
  R6  `geom()` 의 W 에 SUMMARY_MIN_W + 2·EDGE 바닥만 깐다.
  R7  넘치는 남은시간을 버리거나 말줄임한다.
"""

import math
import os
import struct
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claude_pet  # noqa: E402

# 문자 advance 표는 한 벌만 존재한다(test_summary_layout 과 같은 이유로 import 한다).
from test_summary_pill import pretendard_width, pretendard_width_sub  # noqa: E402
from test_companion_motion import gui_functions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

LOCALES = ("ko", "en", "ja", "es")
# 0.5 는 기본 배율(run_gui: cfg.get("scale", 0.5)), 0.3 은 run_gui 가 허용하는 최소 배율.
SMALL_SCALES = (0.5, 0.3)
# 1.0 은 대조군 — 펫 폭이 W 를 넓혀 결함을 가리는 기하이고, 기존 게이트가 쓰던 배율이다.
ALL_SCALES = (1.0,) + SMALL_SCALES

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)

# 사용자가 본 것: 주간 34%, 남은시간 3d 10h. 세션·모델 행도 같은 모양으로 만든다.
# 남은시간은 생산 fmt_countdown 이 이 reset 시각에서 만든다(cd_days / cd_hm).
WEEKLY_RESET = NOW + timedelta(days=3, hours=10, minutes=30)
SESSION_RESET = NOW + timedelta(hours=3, minutes=43, seconds=30)
# Codex 행은 생산 roam_summary_codex 가 datetime.now() 로 다시 세므로 시각 대신 문구로 준다
# (reset_dt=None 이면 reset_text 를 그대로 쓴다) — 실제 시계에 기대지 않기 위해서다.
CODEX_ROWS = [("codex_session", 12.0, None, "3h 43m"),
              ("codex_weekly", 68.0, None, "5d 21h")]


def builtin_pet_base():
    """내장 펫의 기본 크기(PW0, PH0) — run_gui 가 `frames["idle"][0].size()` 에서 얻는 값.

    PNG IHDR 에서 읽는다(AppKit 없이). run_gui 와 같은 PET_SCALE_DOWN 으로 나눈다.
    """
    data = (ROOT / "frames" / "idle" / "00.png").read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError("frames/idle/00.png 가 PNG 가 아니다 — 펫 크기를 못 읽는다")
    w, h = struct.unpack(">II", data[16:24])
    return int(w // claude_pet.PET_SCALE_DOWN), int(h // claude_pet.PET_SCALE_DOWN)


def claude_rows():
    """서버 행 (label, pct, reset_dt, reset_text) — fetch_exact_usage 의 모양. 라벨은 지금 로케일."""
    t = claude_pet.t
    return [(t("session"), 42.0, SESSION_RESET, None),
            (t("weekly"), 34.0, WEEKLY_RESET, None),
            ("Fable", 12.0, WEEKLY_RESET, None)]


# 모양: (이름, Claude 게이지 선택 또는 None(Claude 숨김), Codex 게이지 선택 또는 None,
#        이 모양에서 기대하는 블록별 한 줄 — None 이면 게이지가 여럿이라 한 줄 단언 없음)
# 기대 줄은 **여기서 독립적으로** 적는다: 라벨(그 로케일의 TR) + " " + 정수% + " · " + 남은시간.
# 남은시간 형식은 네 로케일 모두 cd_days "{d}d {h}h" / cd_hm "{h}h {m}m" 이다.
def single_shapes():
    t = claude_pet.t
    sep = claude_pet.SUMMARY_SEP
    return [
        ("claude weekly", ["weekly"], None,
         {"claude": f"{t('weekly')} 34%{sep}3d 10h"}),
        ("claude session", ["session"], None,
         {"claude": f"{t('session')} 42%{sep}3h 43m"}),
        ("claude model", ["model"], None,
         {"claude": f"Fable 12%{sep}3d 10h"}),
        ("codex weekly only", None, ["weekly"],
         {"codex": f"{t('codex_weekly')} 68%{sep}5d 21h"}),
        ("claude weekly + codex weekly", ["weekly"], ["weekly"],
         {"claude": f"{t('weekly')} 34%{sep}3d 10h",
          "codex": f"{t('codex_weekly')} 68%{sep}5d 21h"}),
    ]


CONTROL_SHAPES = [
    # 게이지 셋 — 기존 게이트가 보던 내용. 고치기 전에도 후에도 초록이어야 한다.
    ("claude three gauges", ["session", "weekly", "model"], None, None),
]


# 게이지 하나가 **아닌** 내용 종류. 기본 서버 행 대신 넣을 state/RUNTIME 조각을 돌려준다
# (로케일에 따라 라벨이 바뀌므로 호출 시점에 만든다). 상태 줄은 제공자 없는 **전역 줄**이라
# 로고 들여쓰기가 없다 — summary_lines 가 예산에서 로고 폭을 빼지 않는 유일한 경우다.
CONTENT = {
    "rows": lambda: {},
    "credit": lambda: {"state": {
        "oauth": claude_rows() + [(claude_pet.t("credit"), 66.0, None, "Sep 30")],
        "credit_text": "$100.66"}},
    "loading": lambda: {"state": {"oauth": None, "stats": None}},
    "token_expired": lambda: {"state": {"oauth": None}, "auth_error": True},
    "onb_install": lambda: {"state": {"oauth": None, "onboard": "install"}},
    "api_cost": lambda: {"state": {"oauth": None, "cost": 12.375, "cost_month": 27.5},
                         "runtime": {"mode": "api", "admin_key": "k", "api_budget": 50.0}},
    # 짧은 내용(라운드 2, Reviewer F1): 게이지 하나에 한 자리 % 와 분 단위 남은시간.
    # 남은시간은 생산 fmt_countdown 이 cd_m 으로 만든다(5분 30초 → "5m").
    "short_weekly": lambda: {"state": {"oauth": [
        (claude_pet.t("weekly"), 8.0, NOW + timedelta(minutes=5, seconds=30), None)]}},
    "short_codex": lambda: {"state": {"codex": [("codex_weekly", 8.0, None, "5m")]}},
}

# (이름, Claude 게이지 또는 None, Codex 게이지 또는 None, CONTENT 이름)
OTHER_CONTENT_SHAPES = [
    ("claude session + weekly", ["session", "weekly"], None, "rows"),
    ("claude weekly + model", ["weekly", "model"], None, "rows"),
    ("claude weekly + credit", ["weekly", "credit"], None, "credit"),
    ("codex two rows only", None, ["session", "weekly"], "rows"),
    ("claude three gauges + codex two rows", ["session", "weekly", "model"],
     ["session", "weekly"], "rows"),
    ("status loading (global line)", ["session", "weekly", "model"], None, "loading"),
    ("status token_expired (global line)", ["session", "weekly", "model"], None,
     "token_expired"),
    ("status onb_install (global line)", ["session", "weekly", "model"], None, "onb_install"),
    ("token_expired (global) + codex weekly", ["session", "weekly", "model"], ["weekly"],
     "token_expired"),
    ("claude api cost", ["session", "weekly", "model"], None, "api_cost"),
]


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


class _Screen:
    """`_screen_w()` 가 보는 화면 — 1440pt 짜리 노트북 한 대."""

    def mainScreen(self):
        return self

    def visibleFrame(self):
        return SimpleNamespace(size=SimpleNamespace(width=1440.0, height=900.0))


_F11 = object()        # F_SUMMARY  — 11pt
_F95 = object()        # F_SUMMARY_SUB — 9.5pt


def _astr(text, font=None):
    width = (pretendard_width_sub if font is _F95 else pretendard_width)(text)
    return SimpleNamespace(size=lambda: SimpleNamespace(width=width))


def drawn_width(line):
    """draw_summary_pill 이 이 줄을 그릴 때의 폭. 줄 전체가 "sub" 면 9.5pt, 아니면 11pt."""
    measure = (pretendard_width_sub if all(k == "sub" for _t, k in line)
               else pretendard_width)
    return sum(measure(text) for text, _k in line)


def text_of(line):
    return "".join(text for text, _k in line)


class Settled:
    """한 모양·한 배율에서 생산 어댑터를 안정될 때까지 돌린 결과."""


_SETTLED = {}


def settle(test, lang, scale, claude_gauges, codex_gauges, content=None):
    """생산 `roam_summary_text` 를 생산 기하와 한 scope 에서 돌린다 → Settled.

    틱이 하는 일을 그대로 흉내 낸다: 어댑터를 부르고(폭을 기록), `_regeom()` 처럼 줄 수를
    g 로 옮기고 dirty 를 내린 뒤, 5초 메모 창을 넘겨 다시 부른다. 기록된 폭과 줄 수가 더
    움직이지 않을 때의 W 가 roam_apply_display 가 쓰는 roam_env 의 W 다.

    결과는 입력별로 한 번만 만든다(결정적이고, 매번 claude_pet.py 를 AST 로 다시 읽는
    비용을 아낀다). 캐시는 결과만 담는다 — 실패한 정착은 저장되지 않는다.
    """
    key = (lang, scale, tuple(claude_gauges) if claude_gauges is not None else None,
           tuple(codex_gauges) if codex_gauges is not None else None, content)
    if key not in _SETTLED:
        _SETTLED[key] = _settle(test, lang, scale, claude_gauges, codex_gauges, content)
    claude_pet.set_lang(lang)
    return _SETTLED[key]


def _settle(test, lang, scale, claude_gauges, codex_gauges, content=None):
    """content 는 CONTENT 표의 이름(None 이면 기본 서버 행). 상태 줄·크레딧·API 비용 같은
    다른 내용 종류를 같은 생산 경로로 돌리기 위한 것이다."""
    claude_pet.set_lang(lang)
    extra = CONTENT[content]() if content is not None else {}
    pw0, ph0 = builtin_pet_base()
    runtime = dict(claude_pet.RUNTIME)
    runtime.update(mode="sub", admin_key="", api_budget=0.0,
                   show_claude=claude_gauges is not None,
                   claude_gauges=list(claude_gauges or ["session"]),
                   show_codex=codex_gauges is not None,
                   codex_gauges=list(codex_gauges or ["weekly"]),
                   codex_mode="sub", openai_admin_key="", codex_budget=0.0)
    runtime.update(extra.get("runtime", {}))
    state = {"stats": {"spikes": {}}, "oauth": claude_rows(), "cost": None,
             "cost_month": None, "onboard": None, "credit_text": None,
             "codex": list(CODEX_ROWS), "api_error": False, "api_stale": False,
             "codex_cost": None, "codex_cost_month": None,
             "codex_api_error": False, "codex_api_stale": False,
             "summary_lines_n": 2}
    state.update(extra.get("state", {}))
    state["codex_summary"] = lambda: claude_pet.codex_summary_segment(
        runtime, state.get("codex"), False, None, None, False, False, auth_error=False)
    g = {"scale": scale}
    clock = {"now": 1_000_000.0}
    calls = []

    def summary_lines_spy(groups, measure, budget, measure_sub=None):
        out = claude_pet.summary_lines(groups, measure, budget, measure_sub)
        calls.append((budget, out))
        return out

    scope = dict(vars(claude_pet))
    scope.update(
        state=state, RUNTIME=runtime, g=g, PW0=pw0, PH0=ph0, win=None,
        NSScreen=_Screen(), astr=_astr, F_SUMMARY=_F11, F_SUMMARY_SUB=_F95,
        F_SUMMARY_BY_KIND={k: _F11 for k in claude_pet.SUMMARY_COLORS},
        F_SUMMARY_SUB_BY_KIND={k: _F95 for k in claude_pet.SUMMARY_COLORS},
        OAUTH_STATUS={"auth_error": bool(extra.get("auth_error")), "last_error": None},
        CODEX_STATUS={"auth_error": False, "last_error": None},
        _summary_memo={"key": None, "value": None},
        _time=SimpleNamespace(time=lambda: clock["now"],
                              monotonic=lambda: clock["now"]),
        datetime=_FixedDatetime, timezone=timezone,
        summary_lines=summary_lines_spy)
    gui_functions(test, ("roam_summary_text", "geom", "pill_band", "_pill_text_budget",
                         "_apply_pill_width", "_pill_width_step", "_widest_digit",
                         "_screen_w", "_stable_w", "_pill_budget_for"), scope)
    state["pill_budget"] = scope["_pill_budget_for"]

    result = None
    for _round in range(8):
        before = (g.get("pill_w"), g.get("lines"))
        calls.clear()
        result = scope["roam_summary_text"]()
        # _regeom(): 줄 수를 g 로 옮기고 dirty 를 내린다(창 크기는 geom() 이 g 에서 읽는다).
        g["lines"] = state.get("summary_lines_n") or 2
        g.pop("pill_w_dirty", None)
        clock["now"] += 5.0                     # 다음 5초 창 — 메모가 풀린다
        if (g.get("pill_w"), g.get("lines")) == before:
            break
    else:
        test.fail(f"[{lang} scale={scale}] 필 폭이 8 라운드 안에 안정되지 않았다: "
                  f"pill_w={g.get('pill_w')} lines={g.get('lines')}")

    blocks, text_w, text_h = result
    s = Settled()
    s.lang, s.scale = lang, scale
    s.blocks, s.text_w, s.text_h = blocks, float(text_w), float(text_h)
    s.PW, s.PH, s.W, s.H = scope["geom"]()
    s.band = scope["pill_band"]()
    s.pill_w_recorded = g.get("pill_w")
    # 접는 데 쓴 예산 = 어댑터가 돌려준 blocks 를 만든 그 summary_lines 호출의 예산.
    fold = [b for b, out in calls if out is blocks]
    if not fold:
        fold = [b for b, _out in calls if math.isfinite(b)]
    test.assertTrue(fold, f"[{lang} scale={scale}] 어댑터가 summary_lines 를 부르지 않았다")
    s.fold_budget = float(fold[-1])
    return s


def frames_for(s):
    """roam_apply_display 가 하는 그대로: 펫이 왼쪽/오른쪽일 때의 roam_frame (실제 창 좌표)."""
    out = []
    for right in (False, True):
        lay = claude_pet.roam_frame((0.0, 0.0), claude_pet.DISPLAY_FULL, right, False,
                                    s.W, s.H, s.PW, s.PH, s.band, s.scale,
                                    s.text_w, s.text_h)
        out.append((right, lay))
    return out


def lines_of(s):
    return [(pid, line) for pid, lines in s.blocks for line in lines]


def case_tag(s, name):
    return f"[{s.lang} {name} scale={s.scale} W={s.W:.0f} pill_w(기록)={s.pill_w_recorded}]"


class _Base(unittest.TestCase):
    def setUp(self):
        self.addCleanup(claude_pet.set_lang, claude_pet.L.get("lang"))

    def assert_none(self, problems, message):
        """문제 목록이 비어 있어야 한다. 실패 메시지에는 숫자가 든 목록이 한 번만 나온다."""
        if problems:
            self.fail(f"{len(problems)} 건 — {message}")

    def run_shapes(self, shapes_fn, scales):
        for lang in LOCALES:
            claude_pet.set_lang(lang)
            for name, cg, xg, expect in shapes_fn():
                for scale in scales:
                    yield name, expect, settle(self, lang, scale, cg, xg)

    # I1 ---------------------------------------------------------------------------------
    def line_overflows(self, s, name):
        problems = []
        for right, lay in frames_for(s):
            _px, _py, pill_w, _ph = lay["pill"]
            for pid, line in lines_of(s):
                area = pill_w - 2 * claude_pet.PILL_PAD - (
                    claude_pet.SUMMARY_LOGO_W if pid is not None else 0)
                width = drawn_width(line)
                if width > area + 0.5:
                    problems.append(
                        f"{case_tag(s, name)} right={right}: {text_of(line)!r} "
                        f"{width:.2f}pt > 필 글자 자리 {area:.2f}pt "
                        f"(필 폭 {pill_w:.2f}, 넘침 {width - area:.2f}pt)")
        return problems

    # I2 ---------------------------------------------------------------------------------
    def budget_mismatch(self, s, name):
        rect = claude_pet.roam_pill_rect(claude_pet.DISPLAY_FULL, False, False, s.W,
                                         s.PW, s.PH, s.band, text_w=10 ** 6,
                                         text_h=s.text_h)
        widest = rect[2] - 2 * claude_pet.PILL_PAD - claude_pet.SUMMARY_LOGO_W
        used = s.fold_budget - claude_pet.SUMMARY_LOGO_W
        if abs(used - widest) > 1.0:
            return [f"{case_tag(s, name)}: 접힘 예산 {used:.2f}pt vs 같은 W 에서 필이 줄 수 "
                    f"있는 최대 글자 자리 {widest:.2f}pt (차이 {used - widest:+.2f}pt)"]
        return []

    # I4 ---------------------------------------------------------------------------------
    def window_clips(self, s, name):
        problems = []
        for right, lay in frames_for(s):
            px, _py, pill_w, _ph = lay["pill"]
            win_w = lay["size"][0]
            if px < -0.5 or px + pill_w > win_w + 0.5:
                problems.append(
                    f"{case_tag(s, name)} right={right}: 필 [{px:.2f}, {px + pill_w:.2f}] 이 "
                    f"창 [0, {win_w:.2f}] 밖으로 나간다")
            for pid, line in lines_of(s):
                x0 = px + claude_pet.PILL_PAD + (
                    claude_pet.SUMMARY_LOGO_W if pid is not None else 0)
                x1 = x0 + drawn_width(line)
                if x0 < -0.5 or x1 > win_w + 0.5:
                    problems.append(
                        f"{case_tag(s, name)} right={right}: {text_of(line)!r} 글자 "
                        f"[{x0:.2f}, {x1:.2f}] 이 창 [0, {win_w:.2f}] 밖 — "
                        f"{max(x1 - win_w, -x0):.2f}pt 가 창에 잘린다")
        return problems


class SingleGaugeLineFitsItsPillTests(_Base):
    """I1 — 게이지 하나짜리 줄이 **그려질 필**의 글자 자리 안에 들어간다.

    지금 코드(R0)에서 ko 주간 0.5배: 줄 `주간 34% · 3d 10h` 는 11pt 로 88.84pt 인데,
    어댑터는 인라인 전 두 줄을 따로 재서 need = max(46.03, 69.32) = 69.32pt 를 기록하고,
    W = max(96+42, int(113.61)+8) = 138, 필 폭 = min(138−8, 88.84+18+26) = 130, 글자 자리
    = 130 − 26 − 18 = 86pt. 2.84pt 가 넘친다. 0.3배에선 W=121, 필 120, 자리 76 → 12.84pt.

    Rivals 가르기: R0 빨강(ko·en 의 주간·세션·모델, es 의 주간·세션, ko·en·es 의 Codex
    모양 — ja 는 접히거나(세션) 딱 맞아 여기선 안 걸린다); R3 빨강(need 가 리셋 줄
    11pt 80.27 이라 ko 0.5 의 W 가 그대로 138, 자리 86 < 88.84); R4 빨강(en 주간: need
    105.10 → 기록 149.11 → W 157 → 자리 105 < 107.72); R6 빨강(W 바닥 128 은 자리 76 그대로).
    R1 은 여기서 초록이다(줄을 접어서 맞춘다) — 그건 SingleGaugeStaysOneLineTests 가 가른다.
    R5 도 여기서 초록이다(필이 상한 없이 커진다) — WindowDoesNotClipTests 가 가른다.
    """

    def test_every_single_gauge_line_fits_the_text_area_of_its_pill(self):
        problems = []
        for name, _expect, s in self.run_shapes(single_shapes, ALL_SCALES):
            problems += self.line_overflows(s, name)
        self.assert_none(
            problems,
            "게이지 하나짜리 줄이 필의 글자 자리를 넘는다 — 접히지도 잘리지도 않으므로 "
            "오른쪽 패딩을 먹고, 더 넘치면 창 밖으로 나가 글자가 사라진다:\n  "
            + "\n  ".join(problems))


class FoldBudgetIsThePillTextAreaTests(_Base):
    """I2 — 어댑터가 `summary_lines` 에 넘긴 예산(−로고) == 같은 W 의 필 최대 글자 자리.

    예산은 spy 로 **어댑터가 실제로 넘긴 값**을 잡는다(어댑터가 돌려준 blocks 를 만든 그
    호출). 비교 대상은 `tests/test_summary_layout.py` 의 같은 이름 불변식과 같다:
    `roam_pill_rect(..., text_w=10**6)` 의 글자 자리.

    지금 코드: `_pill_text_budget()` 이 `max(SUMMARY_MIN_W, room − 2·PILL_PAD − LOGO)` 라
    W < 172 이면 예산이 120 으로 바닥에 붙는다. 필은 `max(SUMMARY_MIN_W, …)` 를 **필 폭**에
    걸기 때문에 같은 W 에서 글자 자리는 76~119 다. 그래서 접힘은 120 이 있다고 믿고 안 접고,
    필은 그보다 좁다 — I1 넘침이 접힘으로 구조되지 않는 이유가 이것이다.

    Rivals 가르기: R0 빨강(ko 0.5: 120 vs 86); R2 빨강 — need 만 고치면 이번 줄은 들어가지만
    (W 150, 자리 98) 예산은 여전히 120 이라, 다음에 무엇이든 need 를 덜 재면 다시 접힘 없이
    넘친다; R5 빨강(필이 상한을 무시하면 최대 자리가 예산과 갈라진다). R1 은 초록.
    배율 1.0 과 게이지 셋은 W ≥ 172 라 지금도 초록이다(대조).
    """

    def test_fold_budget_equals_the_pill_text_area_for_single_gauge_content(self):
        problems = []
        for name, _expect, s in self.run_shapes(single_shapes, ALL_SCALES):
            problems += self.budget_mismatch(s, name)
        self.assert_none(
            problems,
            "접힘이 믿는 예산과 필이 실제로 주는 글자 자리가 다르다:\n  "
            + "\n  ".join(problems))


class SingleGaugeStaysOneLineTests(_Base):
    """I3 — 게이지 하나짜리 블록은 **한 줄**이고, 그 줄은 라벨·수치·남은시간 전부다.

    기대 줄은 이 파일이 로케일 TR 에서 독립적으로 만든다(라벨 + " NN%" + " · " + 남은시간).
    화면이 1440pt 이므로 필이 못 넓어질 이유가 없다 — 접히면 그것은 W 가 내용을 안 따라간
    것이다.

    지금 코드: ja `セッション 42% · 3h 43m`(121.91pt)이 0.5/0.3배에서 두 줄로 접힌다.
    need 가 인라인 전 값이라 W=171, 예산은 바닥 120 → 121.91 > 120.

    Rivals 가르기: R0 빨강(ja 세션); R1 빨강(바닥을 없애 예산이 자리와 같아지면 필이 여전히
    좁아 모든 로케일이 접힌다 — ko 0.5 예산 86 < 88.84); R7 빨강(남은시간을 버리거나 "…"
    로 줄이면 기대 줄과 글자가 다르다); R6 빨강(W 바닥만 올리면 예산은 그대로 바닥 120 이라
    ja 세션이 그대로 접힌다).
    """

    def test_a_single_gauge_block_is_one_complete_line(self):
        problems = []
        for name, expect, s in self.run_shapes(single_shapes, ALL_SCALES):
            got = {pid: [text_of(line) for line in lines] for pid, lines in s.blocks}
            for pid, want in expect.items():
                if got.get(pid) != [want]:
                    problems.append(f"{case_tag(s, name)} {pid}: {got.get(pid)!r} "
                                    f"(기대 [{want!r}])")
        self.assert_none(
            problems,
            "게이지 하나짜리 블록이 한 줄 그대로가 아니다 — 필이 넓어지지 않고 접혔거나 "
            "글자를 잃었다:\n  " + "\n  ".join(problems))


class WindowDoesNotClipTests(_Base):
    """I4 — 필과 모든 글자가 실제 창(roam_frame 의 crop) 안에 있다. **보고된 증상 그 자체.**

    실제 NSWindow 는 논리 창을 펫 ∪ 버튼 ∪ 필(+2pt)로 자른 것이고 (0, 0, W, H) 밖은 없다.
    지금 코드 ko 주간 0.3배: W=121 인데 필은 SUMMARY_MIN_W=120 이라 W−2·EDGE=113 을 넘고,
    펫이 왼쪽이면 필이 [2, 122], 창은 [0, 119] — `…10h` 의 끝 2.84pt 가 창에 잘린다.
    펫이 오른쪽이면 필이 x=−3 에서 시작해 왼쪽 가장자리가 잘린다. 기본 배율 0.5 에서도
    en `Session 42% · 3h 43m`(114.47pt)은 W=150 창에서 끝 1.47pt 가 잘린다.
    (좌표는 전부 실제 창 좌표 — roam_frame 이 돌려주는 crop 기준.)

    Rivals 가르기: R0 빨강; R5 빨강(필이 상한을 넘어 커지면 글자는 필 안이지만 창 밖 —
    0.3배 W=121 에서 필 [2, 134.84], 글자 끝 121.84 > 창 119); R1 빨강(접어서 글자는
    들어가도 120pt 필이 W=121 창보다 넓다). I1 이 초록이어도 이 테스트가 빨간 구현이 R5 다.
    """

    def test_no_pill_edge_or_glyph_falls_outside_the_window(self):
        problems = []
        for name, _expect, s in self.run_shapes(single_shapes, ALL_SCALES):
            problems += self.window_clips(s, name)
        self.assert_none(
            problems,
            "필이나 글자가 창 밖으로 나가 말 없이 잘린다:\n  " + "\n  ".join(problems))


class FoldBudgetIsThePillTextAreaForEveryContentTests(_Base):
    """I2 를 게이지 하나짜리 **밖의** 내용 전부로 넓힌다 — 수정이 바꾼 동작 중 위 테스트들이
    안 잡는 유일한 것이라서다(라운드 2, 수정 diff 를 보고 추가).

    수정 전후를 14개 내용 × 4 로케일 × 3 배율로 비교하면, 게이지 하나짜리가 아닌 내용에서는
    줄·W·기록 폭·text_w 가 **한 톨도** 안 바뀌고 접힘 예산 값만 바뀐다(W < 172 일 때 바닥
    120 이 사라진다). 그 예산은 줄을 바꾸지 않으므로 화면에선 안 보이지만, 저장소 불변식
    (접힘이 믿는 폭 == 필이 주는 폭)은 내용 종류를 가리지 않는다. 특히 상태 줄은 로고가
    없는 **전역 줄**이라 summary_lines 가 예산에서 로고를 빼지 않는다 — 산술이 다른 유일한
    길이므로 따로 고정한다. 등식 하나가 두 경우를 다 덮는다:
    예산 − LOGO == 필 폭 − 2·PAD − LOGO  ⇔  예산 == 필 폭 − 2·PAD(전역 줄의 글자 자리).

    지금 코드(75a7ddd): 빨강 — 예: ko weekly + model 0.5배 W=164 에서 예산 120 vs 자리 112,
    loading 상태 0.3배 W=99 에서 120 vs 76. 수정 후 초록.

    Rivals 가르기(스크래치 사본에서 실행해 확인한 것):
      · 수정에서 바닥만 되살린 구현(R2) — 여기와 위 I2 가 빨강.
      · `_pill_text_budget` 이 로고를 안 빼는 구현(room − 2·PAD) — 여기, 위 I2, 대조군,
        test_summary_layout 의 FoldBudgetMatchesTheActualPillTests 가 빨강.
    구성상(실행하지 않은 추론): 바닥을 게이지 하나짜리 내용에서만 없애는 구현은 위 I2 를
    통과하고 여기서만 빨갛다 — 이 테스트가 따로 있는 이유다.
    """

    def test_fold_budget_equals_the_pill_text_area_for_every_content_kind(self):
        problems = []
        for lang in LOCALES:
            claude_pet.set_lang(lang)
            for name, cg, xg, content in OTHER_CONTENT_SHAPES:
                for scale in ALL_SCALES:
                    s = settle(self, lang, scale, cg, xg, content)
                    problems += self.budget_mismatch(s, name)
        self.assert_none(
            problems,
            "게이지 하나짜리가 아닌 내용에서도 접힘 예산과 필 글자 자리가 달라선 안 된다:\n  "
            + "\n  ".join(problems))


# 짧은 내용 — 필이 SUMMARY_MIN_W(120) 바닥에 붙는 내용. (이름, Claude 게이지, Codex 게이지, CONTENT)
SHORT_CONTENT_SHAPES = [
    ("claude weekly 8% · 5m", ["weekly"], None, "short_weekly"),
    ("codex weekly 8% · 5m only", None, ["weekly"], "short_codex"),
    ("status loading (global line, no logo)", ["session", "weekly", "model"], None, "loading"),
    ("status token_expired (global line, no logo)", ["session", "weekly", "model"], None,
     "token_expired"),
    ("status no_providers (global line, no logo)", None, None, "rows"),
]


class ShortContentStaysInTheWindowTests(_Base):
    """I4 를 **짧은 내용**으로 넓힌다 — 필이 SUMMARY_MIN_W 바닥에 붙는 경우(라운드 2, Reviewer F1).

    위 WindowDoesNotClipTests 는 게이지 하나짜리 줄(88pt 이상)만 봐서, `need` 를 고치면 W 가
    줄을 따라 128 이상이 되고 초록이 된다. 그런데 `geom()` 의 W 는
    `max(pw + 2·BTN_R + 16, int(pill_w) + 2·EDGE)` 라 **SUMMARY_MIN_W + 2·EDGE(128) 바닥이
    없고**, `roam_pill_rect` 는 필을 `max(SUMMARY_MIN_W, W − 2·EDGE)` 의 방에 120 이상으로
    그린다. 내용이 짧고 펫이 작으면(0.3배: 펫 쪽 바닥 57+42 = 99) W < 128 이 되어 120pt
    필이 창보다 넓다. 실제 창은 crop 이라 (0, W) 밖은 없다 — 필 테두리가 잘리고, 펫이
    오른쪽이면 필이 음수 x 에서 시작해 **전역 줄의 첫 글자까지** 잘린다(로고 들여쓰기가 없는
    pid None 줄은 필 왼쪽 + PILL_PAD 에서 시작한다).

    need/예산 수정만 들어간 작업 트리에서: ko `주간 8% · 5m` 0.3배 W=121 → 필 [2, 122] /
    [−3, 117] (창 [0, 119]); `조회 중…` 0.3배 W=99 → 필 [2, 122] / [−25, 95] (창 [0, 97]),
    글자 [−12, 28.1] — 12pt 가 잘린다.

    Rivals 가르기: 바닥 없음(지금) 빨강; W 바닥을 SUMMARY_MIN_W(120) 로만 거는 구현(2·EDGE
    누락 — 방이 112 라 필 120 이 여전히 x=−4) 빨강; R5(필 상한 해제) 빨강. 이 테스트를
    초록으로 만드는 것은 W ≥ SUMMARY_MIN_W + 2·SUMMARY_EDGE 가 되게 하는 구현이다.
    """

    def test_short_content_pill_and_glyphs_stay_inside_the_window(self):
        problems = []
        for lang in LOCALES:
            claude_pet.set_lang(lang)
            for name, cg, xg, content in SHORT_CONTENT_SHAPES:
                for scale in ALL_SCALES:
                    s = settle(self, lang, scale, cg, xg, content)
                    problems += self.window_clips(s, name)
        self.assert_none(
            problems,
            "짧은 내용에서 필이나 글자가 창 밖으로 나가 말 없이 잘린다:\n  "
            + "\n  ".join(problems))


class ThreeGaugeControlTests(_Base):
    """대조군 — 게이지 셋(기존 게이트가 보던 내용)은 지금도 I1·I2·I4 를 지킨다.

    고치기 **전에** 초록이어야 하고(그래야 위 빨강이 하네스 탓이 아니라 게이지 하나짜리
    내용 탓이라는 게 선다), 고친 **뒤에도** 초록이어야 한다(인라인을 고치다 게이지 여럿의
    폭을 깨는 구현을 막는다). 배율 1.0·0.5·0.3, 네 로케일.
    """

    def test_three_gauges_fit_match_and_stay_in_the_window(self):
        problems = []
        for name, _expect, s in self.run_shapes(lambda: CONTROL_SHAPES, ALL_SCALES):
            problems += self.line_overflows(s, name)
            problems += self.budget_mismatch(s, name)
            problems += self.window_clips(s, name)
        self.assert_none(problems, "대조군이 빨갛다 — 하네스나 기하가 틀렸다:\n  "
                         + "\n  ".join(problems))


class HarnessIsProductionTests(_Base):
    """하네스가 생산을 돌리고 있다는 것 자체를 확인한다(이 파일의 빨강이 하네스 탓이 아님).

    · 펫 기본 크기가 내장 펫 프레임에서 왔다(192×208).
    · 사용자가 본 바로 그 줄을 어댑터가 낸다(ko 주간 → `주간 34% · 3d 10h`, 11pt 88.84pt).
    · 배율 1.0 에서는 펫 폭(192+2·13+16 = 234)이 W 를 정한다 — 기존 게이트가 결함을 못 본
      기하가 실제로 재현된다.

    결함과 무관한 사실만 단언한다: 배율 1.0 은 펫이 W 를 정하는 기하라 고치기 전에도 후에도
    한 줄이 나온다. 그래서 이 테스트는 어떤 경쟁 구현에서도 하네스 자체가 틀렸을 때만 빨갛다.
    """

    def test_the_harness_reproduces_the_reported_line_and_the_pet_size(self):
        self.assertEqual(builtin_pet_base(), (192, 208))
        wide = settle(self, "ko", 1.0, ["weekly"], None)
        self.assertEqual(wide.W, 192 + 2 * claude_pet.BTN_R + 16)
        self.assertEqual([text_of(l) for _p, l in lines_of(wide)], ["주간 34% · 3d 10h"])
        self.assertAlmostEqual(drawn_width(lines_of(wide)[0][1]), 88.84, delta=0.05)


if __name__ == "__main__":
    unittest.main()
