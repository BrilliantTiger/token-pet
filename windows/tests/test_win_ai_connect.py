"""계약 v7-I — Windows 포트의 "AI 연결" 배선. Verifier(gemini-tests-v2) 작성, 구현 전.

계약: briefs/v7-contract.md I1·I7. 동작(받기·검증·로그인·상태)은 코어에 있고 `tests/test_cli_install_login.py`
가 가른다. 여기서는 포트가 그 코어를 쓰는지만 AST 로 본다(PySide6 가 없는 곳에서는 포트를 임포트할 수 없다).

    python3 -m unittest discover -s windows/tests -t . -v

Developer 는 이 파일의 단언·기대값을 고치지 않는다(AGENTS.md §2).
"""

import ast
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PORT = os.path.join(ROOT, "windows", "claude_pet_win.py")


def _tree():
    with open(PORT, encoding="utf-8") as f:
        return ast.parse(f.read())


def _class(tree, name):
    found = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    return found[0] if found else None


def _called(node):
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            out.add(c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", None))
    return out


def _t_keys(node):
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call) and c.args and isinstance(c.args[0], ast.Constant) \
                and isinstance(c.args[0].value, str):
            f = c.func
            if (isinstance(f, ast.Name) and f.id in ("t", "tw")) or \
                    (isinstance(f, ast.Attribute) and f.attr == "t"):
                out.add(c.args[0].value)
    return out


class WinAiConnectTests(unittest.TestCase):

    def setUp(self):
        self.tree = _tree()
        self.win = _class(self.tree, "PetWindow")
        self.methods = {n.name: n for n in self.win.body if isinstance(n, ast.FunctionDef)}

    def reach(self, name):
        seen, frontier = set(), [self.methods[name]]
        while frontier:
            for called in _called(frontier.pop()):
                if called in self.methods and called not in seen:
                    frontier.append(self.methods[called])
                seen.add(called)
        return seen

    def test_the_settings_dialog_has_the_ai_connection_section(self):
        """I1: 설정 창에 "AI 연결" 구역 — 줄은 `cp.ai_connect_row` 가 정하고, 버튼은 `cp.run_ai_connect` 로 간다
        (메인 스레드 밖에서). 높이는 656 을 넘지 않는다.
        Rival: 포트가 상태 문구를 직접 조립(macOS 와 문구·버튼 규칙이 갈라진다)."""
        dlg = _class(self.tree, "SettingsDialog")
        self.assertIsNotNone(dlg)
        self.assertIn("ai_sec", _t_keys(dlg))
        port_calls = _called(self.tree)
        self.assertIn("ai_connect_row", port_calls)
        self.assertTrue({"run_ai_connect", "start_ai_connect"} & port_calls)
        pht = [n.value.elts[1].value for n in dlg.body
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple)
               and [getattr(e, "id", None) for e in n.targets[0].elts] == ["PWID", "PHT"]]
        self.assertEqual(len(pht), 1)
        self.assertLessEqual(pht[0], 656)

    def test_the_menu_items_use_this_flow_instead_of_a_console(self):
        """I1: 우클릭의 설치·로그인 다섯 항목이 새 PowerShell 콘솔을 열지 않고 설치·로그인 흐름으로 간다.
        Rivals: 설정 창만 새 흐름; `npm install -g @openai/codex` 가 남음(공식 실행 파일을 받는 계약과 다르다)."""
        for name in ("_install_claude", "_login_claude", "_install_codex", "_login_codex", "_login_gemini"):
            with self.subTest(handler=name):
                self.assertIn(name, self.methods, "PetWindow.%s 가 없다" % name)
                reach = self.reach(name)
                self.assertNotIn("_run_in_console", reach, "%s 가 아직 콘솔을 연다" % name)
                self.assertTrue({"run_ai_connect", "start_ai_connect"} & reach,
                                "%s 가 설치·로그인 흐름으로 가지 않는다" % name)
        consts = {n.value for n in ast.walk(self.win) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertEqual(sorted(c for c in consts if "npm install" in c or "install.ps1" in c), [])

    def test_the_connect_job_runs_off_the_gui_thread(self):
        """I4: 받기는 메인 스레드 밖 — 포트가 `cp.run_ai_connect` 를 직접 부른다면 그곳은 `threading.Thread` 의
        target 안이다. `cp.start_ai_connect` 만 부른다면 스레드는 코어가 연다."""
        owners = [n for n in ast.walk(self.tree) if isinstance(n, (ast.FunctionDef, ast.Lambda))
                  and "run_ai_connect" in _called(n)]
        if not owners:
            # 포트가 코어의 start_ai_connect(스레드를 여는 도우미 — 코어 게이트가 본다)만 부르는 경우.
            self.assertIn("start_ai_connect", _called(self.tree), "설치·로그인 흐름을 부르는 곳이 없다")
            return
        threads = [c for c in ast.walk(self.tree) if isinstance(c, ast.Call)
                   and getattr(c.func, "attr", getattr(c.func, "id", None)) == "Thread"]
        targets = set()
        for c in threads:
            for kw in c.keywords:
                if kw.arg == "target":
                    targets.add(kw.value.id if isinstance(kw.value, ast.Name) else
                                getattr(kw.value, "attr", None) or ("<lambda>" if isinstance(kw.value, ast.Lambda)
                                                                    and "run_ai_connect" in _called(kw.value)
                                                                    else None))
        inner = {n.name for n in owners if isinstance(n, ast.FunctionDef)}
        self.assertTrue((inner & targets) or "<lambda>" in targets,
                        "run_ai_connect 를 스레드 target 이 아닌 곳에서 부른다(창이 멈춘다)")

    def test_complete_removal_still_takes_the_whole_app_folder(self):
        """I7: Windows 의 앱 전용 bin·fake-open·staging 은 %LOCALAPPDATA%\\me.yeongyu.claudepet 아래다 — "완전
        삭제"가 그 폴더(wu.cache_dir())를 지운다(회귀 가드 — 지금 초록)."""
        self.assertIn("cache_dir", _called(self.methods["_uninstall"]))


if __name__ == "__main__":
    unittest.main()
