"""계약 v7-W6 — Windows 포트의 Gemini 배선이 macOS 와 같다. Verifier(gemini-tests-v2) 작성, 구현 전.

계약: briefs/v7-contract.md W6 — "나머지(5분 주기·클릭 60초·지문 멈춤/복구·로그인 메뉴 조건·필·설정 Gemini
구역·펫 기분·온보딩 억제·disabled)는 macOS 와 같게. 코어 순수 함수는 공용."

저장소 루트에서:

    python3 -m unittest discover -s windows/tests -t . -v

다른 포트 게이트와 같은 방식이다: PySide6 가 없는 곳에서는 포트를 임포트할 수 없으므로
`windows/claude_pet_win.py` 를 AST 로 읽는다. GUI·레지스트리·네트워크·자격 증명 관리자를 건드리지 않는다.
Windows 의 **동작**(찾기 순서·프로브·fake-open·taskkill·지문)은 코어에 있고 `tests/test_gemini_windows.py`
가 가른다 — 여기서는 포트가 그 코어를 macOS 어댑터와 같은 자리에서 부르는지만 본다.

Developer 는 이 파일의 단언·기대값을 고치지 않는다(AGENTS.md §2).
"""

import ast
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PORT = os.path.join(ROOT, "windows", "claude_pet_win.py")
UPDATE = os.path.join(ROOT, "windows", "win_update.py")


def _tree(path=PORT):
    with open(path, encoding="utf-8") as f:
        return ast.parse(f.read())


def _class(tree, name):
    found = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    return found[0] if found else None


def _method(cls, name):
    if cls is None:
        return None
    found = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[0] if found else None


def _called(node):
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            if isinstance(c.func, ast.Name):
                out.add(c.func.id)
            elif isinstance(c.func, ast.Attribute):
                out.add(c.func.attr)
    return out


def _strs(node):
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _names(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _t_keys(node):
    out = set()
    for c in ast.walk(node):
        if not (isinstance(c, ast.Call) and c.args and isinstance(c.args[0], ast.Constant)
                and isinstance(c.args[0].value, str)):
            continue
        f = c.func
        if (isinstance(f, ast.Name) and f.id in ("t", "tw")) or \
                (isinstance(f, ast.Attribute) and f.attr == "t"):
            out.add(c.args[0].value)
    return out


class WinGeminiWiringTests(unittest.TestCase):

    def setUp(self):
        self.tree = _tree()
        self.win = _class(self.tree, "PetWindow")
        self.assertIsNotNone(self.win)

    def need(self, name):
        m = _method(self.win, name)
        self.assertIsNotNone(m, "PetWindow.%s 가 없다" % name)
        return m

    def test_the_state_carries_gemini_rows_the_login_flag_and_the_pill_hook(self):
        """macOS 의 state["gemini"]·state["gemini_onboard"]·state["gemini_summary"] 와 같은 모양. 훅은
        `cp.gemini_summary_segment` 를 GEMINI_STATUS·GEMINI_BUCKETS 와 함께 부른다.
        Rival: 필 구간을 포트가 직접 조립(게이지 선택·disabled·라벨 규칙이 갈라진다)."""
        init = self.need("__init__")
        consts = _strs(init)
        for key in ("gemini", "gemini_onboard", "gemini_summary"):
            self.assertIn(key, consts, 'state["%s"] 가 없다' % key)
        lambdas = [n for n in ast.walk(init) if isinstance(n, ast.Lambda)
                   and "gemini_summary_segment" in _called(n)]
        self.assertEqual(len(lambdas), 1, "gemini_summary 훅이 cp.gemini_summary_segment 를 부르는 람다가 아니다")
        names = _names(lambdas[0])
        for need in ("GEMINI_STATUS", "GEMINI_BUCKETS", "RUNTIME"):
            self.assertIn(need, names)

    def test_gemini_is_fetched_on_its_own_thread_by_the_core(self):
        """새로고침이 `cp.start_gemini_refresh` 를 부른다 — agy 가 느려도 Claude·Codex 값이 늦어지지 않고,
        Gemini 를 숨기면 아무것도 띄우지 않는다(그 함수가 맡는다). 주 워커 안에서 fetch_gemini_usage 를 직접
        기다리지 않는다.
        Rival: work() 안에서 cp.fetch_gemini_usage() 를 차례로 부름(agy 가 30초 멈추면 필 전체가 멈춘다)."""
        refresh = self.need("refresh")
        self.assertIn("start_gemini_refresh", _called(refresh),
                      "PetWindow.refresh 가 cp.start_gemini_refresh 를 부르지 않는다")
        self.assertNotIn("fetch_gemini_usage", _called(refresh),
                         "주 새로고침 워커가 fetch_gemini_usage 를 직접 기다린다")

    def test_the_pill_takes_the_gemini_segment_like_the_other_two(self):
        """roam_summary_text: gemini_summary 훅을 읽고, 제공자 차례에 "gemini" 가 있고, 메모 키에 Gemini 의
        표시·게이지가 들어가고, "no_providers" 는 세 제공자가 모두 꺼졌을 때다.
        Rivals: 훅은 있는데 블록에 안 붙임; 메모 키에 없어 설정을 바꿔도 5초 동안 옛 필; Claude·Codex 만
        끄면 "no_providers"(Gemini 만 쓰는 사용자에게 거짓)."""
        m = self.need("roam_summary_text")
        consts = _strs(m)
        self.assertIn("gemini_summary", consts)
        self.assertIn("gemini_gauges", consts, "메모 키에 gemini_gauges 가 없다")
        shown = [n.targets[0].id for n in ast.walk(m)
                 if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                 and isinstance(n.value, ast.Call) and "provider_shown" in _called(n.value)
                 and "gemini" in _strs(n.value)]
        self.assertEqual(len(shown), 1, 'provider_shown(R, "gemini") 를 한 번 받아 두지 않았다')
        gates = [n for n in ast.walk(m) if isinstance(n, ast.IfExp)
                 and isinstance(n.body, ast.Constant) and n.body.value == "no_providers"]
        self.assertEqual(len(gates), 1)
        self.assertIn(shown[0], _names(gates[0].test), '"no_providers" 가 Gemini 표시를 보지 않는다')
        orders = [tuple(e.elts[0].value for e in n.elts) for n in ast.walk(m)
                  if isinstance(n, ast.Tuple) and n.elts
                  and all(isinstance(e, ast.Tuple) and len(e.elts) == 2
                          and isinstance(e.elts[0], ast.Constant) for e in n.elts)]
        self.assertIn(("claude", "codex", "gemini"), orders, "제공자 차례에 gemini 구간이 없다")
        plain = [tuple(e.value for e in n.elts) for n in ast.walk(m)
                 if isinstance(n, ast.Tuple) and n.elts and all(isinstance(e, ast.Constant) for e in n.elts)]
        self.assertNotIn(("claude", "codex"), plain, "블록을 Claude·Codex 로만 묶는 차례가 남아 있다")

    def test_gemini_rows_also_quiet_the_claude_onboarding_line(self):
        """온보딩 억제: Gemini 숫자가 떠 있으면 "Claude Code 설치/로그인" 문구를 들이밀지 않는다(코어와 같은
        조건). Rival: Codex 만 봄 — Gemini 만 쓰는 Windows 사용자의 필에 Claude 온보딩이 붙는다."""
        m = self.need("roam_summary_text")
        rule = [n for n in ast.walk(m) if isinstance(n, ast.Assign)
                and {"onb_install", "onb_login"} <= _strs(n.value)]
        self.assertEqual(len(rule), 1, "온보딩 억제 식을 찾지 못했다")
        names = _names(rule[0].value)
        self.assertTrue(any("gemini" in n.lower() for n in names), "온보딩 억제가 Gemini 구간을 보지 않는다")
        self.assertTrue(any("codex" in n.lower() for n in names))

    def test_the_mood_counts_gemini_rows(self):
        """펫 기분: `cp.mood_for(..., gemini_rows=state["gemini"])`. Rival: 인자를 안 넘김 — Gemini 95% 에도
        펫이 태평하다."""
        m = self.need("current_mood")
        calls = [c for c in ast.walk(m) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Attribute) and c.func.attr == "mood_for"]
        self.assertTrue(calls)
        for c in calls:
            kw = {k.arg: k.value for k in c.keywords}
            self.assertIn("gemini_rows", kw, "mood_for 에 gemini_rows 를 넘기지 않는다")
            self.assertIn("gemini", _strs(kw["gemini_rows"]))

    def test_the_right_click_menu_offers_the_gemini_login_on_the_same_flag(self):
        """우클릭 메뉴: state["gemini_onboard"] == "login" 일 때 t("menu_gemini_login") 항목, 누르면
        PetWindow._login_gemini. Rival: 항목 없음(필에는 아무것도 안 보이는데 할 일을 알 길이 없다)."""
        m = self.need("_context_menu")
        self.assertIn("gemini_onboard", _strs(m))
        self.assertIn("menu_gemini_login", _t_keys(m))
        self.assertIn("_login_gemini", _names(m), "메뉴 항목이 _login_gemini 에 묶이지 않았다")
        self.need("_login_gemini")

    def test_a_double_click_also_asks_gemini_again(self):
        """클릭 60초: 더블클릭(수동 새로고침)이 `cp.request_gemini_refresh()` 를 부른다 — macOS 에서
        allow_keychain_prompt 가 올리는 것과 같은 깃발(_gemini_cache["click"])을 올리는 코어 함수다.
        포트는 `allow_keychain_prompt` 를 이름으로 쓰지 않는다(v1.1.1 계약 게이트가 Windows 포트에서 macOS
        키체인 함수 이름을 금지한다).
        Rival: Windows 의 더블클릭은 Claude·Codex 만 다시 받음."""
        m = self.need("mouseDoubleClickEvent")
        reach = set(_called(m))
        for name in list(reach):
            inner = _method(self.win, name)
            if inner is not None:
                reach |= _called(inner)
        self.assertIn("request_gemini_refresh", reach)
        self.assertNotIn("allow_keychain_prompt", _names(self.tree))


class WinGeminiSettingsTests(unittest.TestCase):

    def setUp(self):
        self.tree = _tree()

    def test_the_dialog_has_the_gemini_section_with_the_same_copy_and_still_fits(self):
        """설정: Gemini 구역(s_sec_gemini + 필에 표시 + 게이지 셋) — macOS 와 같은 TR 키. PHT ≤ 656."""
        dlg = _class(self.tree, "SettingsDialog")
        self.assertIsNotNone(dlg)
        keys = _t_keys(dlg)
        for key in ("s_sec_gemini", "s_gauge_session", "s_gauge_weekly", "s_gauge_group"):
            self.assertIn(key, keys)
        self.assertIn("show_gemini", _strs(dlg))
        self.assertTrue({"GEMINI_GAUGES"} & _names(dlg) or {"session", "weekly", "group"} <= _strs(dlg),
                        "게이지 체크박스가 cp.GEMINI_GAUGES 의 셋이 아니다")
        pht = [n.value.elts[1].value for n in dlg.body
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple)
               and [getattr(e, "id", None) for e in n.targets[0].elts] == ["PWID", "PHT"]]
        self.assertEqual(len(pht), 1)
        self.assertLessEqual(pht[0], 656)

    def test_saving_sends_the_gemini_choices(self):
        """save_settings 의 폼에 show_gemini·gemini_gauges. Rival: 화면에는 있는데 저장되지 않음."""
        save = _method(_class(self.tree, "PetWindow"), "save_settings")
        self.assertIsNotNone(save)
        keys = {k.value for d in ast.walk(save) if isinstance(d, ast.Dict)
                for k in d.keys if isinstance(k, ast.Constant)}
        keys |= {n.slice.value for n in ast.walk(save) if isinstance(n, ast.Subscript)
                 and isinstance(n.ctx, ast.Store) and isinstance(n.slice, ast.Constant)}
        for key in ("show_gemini", "gemini_gauges"):
            self.assertIn(key, keys)


class WinGeminiPackagingTests(unittest.TestCase):

    def test_the_gemini_mark_is_a_required_file_of_the_portable_tree(self):
        """필의 Gemini 마크(logos/gemini.svg)가 배포 트리의 필수 파일이다(회귀 가드 — 지금 초록)."""
        with open(UPDATE, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"gemini.svg"', src)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "logos", "gemini.svg")))


if __name__ == "__main__":
    unittest.main()
