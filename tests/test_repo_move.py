"""Gates for the repository move uygnoey/claude-pet -> BrilliantTiger/claude-pet -> BrilliantTiger/token-pet
(macOS half).

**Renamed 2026-11-12, pinned here 2026-11-19 (TOK-59).**  The repository is now
``BrilliantTiger/token-pet``.  ``BrilliantTiger/claude-pet`` 301-redirects, exactly as
``uygnoey/claude-pet`` did after the first move, and an update check that leans on that redirect
stops the day the old name is reused or the redirect is dropped — so the constant carries the
current name.  In the table below read "BrilliantTiger" as ``BrilliantTiger/token-pet``; the
two older names are both refused (``RenamedRepositoryTests``).

The user moved the GitHub repository to the organization ``BrilliantTiger`` on
2026-10-11; the old address 301-redirects, the personal account ``uygnoey`` stays.
Verifier: repo-verify (AGENTS.md §2 Condition A — the Developer must not touch the
assertions or fixtures here). The Windows half is ``windows/tests/test_win_repo_move.py``.

Every expected address is a literal, never rebuilt from ``GITHUB_REPO``: a check of
the form ``url == f".../{GITHUB_REPO}/..."`` is green for any value of the constant and
so tests nothing about the move (AGENTS.md §3).

Truth table (AGENTS.md §3) — rivals across, fixture rows down:

| fixture                                   | unchanged (old) | new only (correct) | owner pinned to GITHUB_REPO | owner pinned to old |
| ----------------------------------------- | --------------- | ------------------ | --------------------------- | ------------------- |
| GITHUB_REPO                                | uygnoey  RED    | BrilliantTiger     |  —                          |  —                  |
| check_github_update() request URL          | uygnoey  RED    | BrilliantTiger     |  —                          |  —                  |
| asset URL under .../uygnoey/...            | accepted        | accepted           | REJECTED                    | accepted            |
| asset URL under .../BrilliantTiger/...     | accepted        | accepted           | accepted                    | REJECTED            |

The last two rows are regression guards and are green on the unchanged code by design:
the asset picker matches on the asset *name* and on https, never on the owner segment.
They exist because installed v1.0.1 / v1.1.0 copies are served whatever
``browser_download_url`` GitHub writes, and a picker that started pinning the owner —
to either name — would strand one population. Both owners are in one test so that
neither "pin to old" nor "pin to new" can pass it.
"""

import json
import unittest
from unittest import mock

import claude_pet

NEW_REPO = "BrilliantTiger/token-pet"
NEW_API_LATEST = "https://api.github.com/repos/BrilliantTiger/token-pet/releases/latest"
FORMER_REPOS = ("uygnoey/claude-pet", "BrilliantTiger/claude-pet")
OLD_DL = "https://github.com/uygnoey/claude-pet/releases/download/v9.9/"
MID_DL = "https://github.com/BrilliantTiger/claude-pet/releases/download/v9.9/"
NEW_DL = "https://github.com/BrilliantTiger/token-pet/releases/download/v9.9/"


class _Response:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class RepoConstantTests(unittest.TestCase):
    def test_github_repo_is_the_organization(self):
        self.assertEqual(claude_pet.GITHUB_REPO, NEW_REPO)


class RenamedRepositoryTests(unittest.TestCase):
    """Neither former name is what the app asks for — not in the constant, and not in the URL
    the check actually requests (a URL written out by hand would pass the constant test)."""

    def test_the_constant_is_neither_former_name(self):
        self.assertNotIn(claude_pet.GITHUB_REPO, FORMER_REPOS)
        self.assertNotIn("claude-pet", claude_pet.GITHUB_REPO)

    def test_the_request_names_neither_former_repository(self):
        calls = []

        def urlopen(req, timeout=0):
            calls.append(req.full_url)
            return _Response({"tag_name": "v0.0.1", "assets": []})

        old = dict(claude_pet._upd_cache)
        self.addCleanup(lambda: (claude_pet._upd_cache.clear(), claude_pet._upd_cache.update(old)))
        with mock.patch.object(claude_pet.urllib.request, "urlopen", side_effect=urlopen):
            claude_pet.check_github_update()
        self.assertEqual(len(calls), 1)
        for former in FORMER_REPOS:
            self.assertNotIn(former, calls[0])
        self.assertTrue(calls[0].startswith("https://api.github.com/repos/BrilliantTiger/token-pet/"))


class MacUpdateCheckUrlTests(unittest.TestCase):
    def setUp(self):
        absent = object()
        old = claude_pet._upd_cache.get("choice", absent)

        def restore():
            if old is absent:
                claude_pet._upd_cache.pop("choice", None)
            else:
                claude_pet._upd_cache["choice"] = old
        self.addCleanup(restore)

    def test_update_check_queries_the_new_repository(self):
        calls = []

        def urlopen(req, timeout=0):
            calls.append(req.full_url)
            # An older tag: the check ends at "current" without touching assets.
            return _Response({"tag_name": "v0.0.1", "assets": []})

        with mock.patch.object(claude_pet.urllib.request, "urlopen", side_effect=urlopen):
            result = claude_pet.check_github_update()
        self.assertEqual(calls, [NEW_API_LATEST])
        self.assertEqual(result, ("current", None, None))


class MacAssetOwnerAgnosticTests(unittest.TestCase):
    """Regression guard: green before and after the move (see the module table)."""

    def _pick(self, base, machine, name):
        assets = [{"name": name, "browser_download_url": base + name}]
        with mock.patch("builtins.print"):
            return claude_pet.select_update_asset(assets, machine)

    def test_both_owner_paths_are_accepted(self):
        for base in (OLD_DL, MID_DL, NEW_DL):
            for machine, name in (("arm64", "ClaudePet.zip"),
                                  ("arm64", "ClaudePet-universal.zip"),
                                  ("x86_64", "ClaudePet-universal.zip")):
                with self.subTest(base=base, machine=machine, name=name):
                    self.assertEqual(self._pick(base, machine, name),
                                     (base + name, name.lower(), machine))


if __name__ == "__main__":
    unittest.main()
