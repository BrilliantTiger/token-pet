"""v8 수정 목록(briefs/v8-fixes.md)의 포트 게이트 — B3, M2. Verifier(gemini-tests-v2) 작성, 구현 전.

코어 쪽(B1 B2 B4 B5 F1 F3 G1 M1 M3)은 tests/test_v8_fixes.py 가 가른다. 여기서는 포트의 배선만 AST 로 본다
(PySide6 가 없는 곳에서는 포트를 임포트할 수 없다).

    python3 -m unittest discover -s windows/tests -t . -v

Developer 는 이 파일의 단언·기대값을 고치지 않는다(AGENTS.md §2).
"""

import ast
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PORT = os.path.join(ROOT, "windows", "claude_pet_win.py")


def _called(node):
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            out.add(c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", None))
    return out


_JOBISH = re.compile(r"phase|ai_jobs|busy|idle|running")


def unguarded_clears(fn, table):
    """fn 과 fn 이 부르는 table 안의 함수에서, **일이 도는지 보지 않고** 도는 `<…>.clear()` 호출의 수.
    본다 = 그 호출이 job 을 묻는 If(조건식에 phase·ai_jobs·busy·idle·running 이 나온다) 안에 있거나, 같은
    함수에서 그보다 앞줄에 그런 If 가 return 으로 빠진다."""
    seen, frontier, bad = set(), [fn], 0
    while frontier:
        cur = frontier.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        asks = [n for n in ast.walk(cur) if isinstance(n, ast.If) and _JOBISH.search(ast.unparse(n.test))]
        for node in ast.walk(cur):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", None))
            if name in table:
                frontier.append(table[name])
            if name != "clear" or not isinstance(node.func, ast.Attribute):
                continue
            inside = any(node in ast.walk(i) and node not in ast.walk(i.test) for i in asks)
            left_early = any(i.lineno < node.lineno and any(isinstance(r, ast.Return) for r in ast.walk(i))
                             for i in asks)
            if not (inside or left_early):
                bad += 1
    return bad


class WinV8Tests(unittest.TestCase):

    def setUp(self):
        with open(PORT, encoding="utf-8") as f:
            self.tree = ast.parse(f.read())
        self.win = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "PetWindow")
        self.methods = {n.name: n for n in self.win.body if isinstance(n, ast.FunctionDef)}

    def test_the_refresh_starts_the_daily_cli_update(self):
        """B3: `PetWindow.refresh()` 가 `cp.start_app_cli_updates()` 를 부른다(macOS 의 refresh_ 와 같이).
        전에는 Windows 에서 앱이 깐 CLI 가 영영 갱신되지 않았다.
        Rival: macOS 만 부름."""
        self.assertIn("refresh", self.methods)
        reach, frontier = set(), [self.methods["refresh"]]
        while frontier:
            for name in _called(frontier.pop()):
                if name in self.methods and name not in reach:
                    frontier.append(self.methods[name])
                reach.add(name)
        self.assertIn("start_app_cli_updates", reach)

    def test_the_menu_items_do_not_clear_a_running_jobs_cancel_flag(self):
        """M2: 일이 돌고 있을 때 우클릭 다섯 항목이 `ai_cancel[...].clear()` 를 하지 않는다 — idle 일 때만.
        Rival: 핸들러가 언제나 clear() 부터 함(방금 누른 [취소]가 지워진다)."""
        for name in ("_install_claude", "_login_claude", "_install_codex", "_login_codex", "_login_gemini"):
            with self.subTest(handler=name):
                self.assertIn(name, self.methods)
                self.assertEqual(unguarded_clears(self.methods[name], self.methods), 0,
                                 "%s 가 진행 중인지 보지 않고 취소 깃발을 지운다" % name)


if __name__ == "__main__":
    unittest.main()
