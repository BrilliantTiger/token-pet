"""TOK-59 — the app is shown as "Token Pet"; a 1.2.0 copy must still update to it.

Two halves, and they pull in opposite directions on purpose.

**What the user reads says Token Pet.**  The bundle's display name, the Windows version
resource, the installer, the menus, alerts and settings title in all four languages, the
READMEs and the site.

**What the 1.2.0 updater looks for does not move.**  A 1.2.0 copy in the field cannot be
taught anything: it asks GitHub for the latest release and accepts only the asset names,
archive layout and bundle identity it was built with.  Those rules are written out below as
literals and small functions *copied from the v1.2.0 tag* (``FROZEN_*`` / ``frozen_*``) —
never imported from this tree, because a rule read from the tree agrees with whatever the
tree was changed to.  Each test builds what this tree would publish (names read out of
``release.sh``, ``setup.py``, ``windows/win_update.py``, ``windows/installer.iss``) and
hands it to the frozen rule.

So the decision this file pins: asset names (``ClaudePet.zip``, ``ClaudePet-universal.zip``,
``ClaudePet.dmg``, ``ClaudePet-universal.dmg``, ``claude-pet-win.zip``,
``claude-pet-win-setup.exe``), the ``ClaudePet.app`` / ``ClaudePet\\ClaudePet.exe`` names on
disk, the bundle ID, the Inno AppId, the install folder, the Run value and the settings and
cache locations stay exactly as 1.2.0 knows them.  Only names shown to a person change.

Stdlib only, and nothing from the app is imported — sources are read as text or by AST — so
the same file runs on the Windows CI runner.
"""
import ast
import os
import plistlib
import re
import tempfile
import unittest
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = ROOT / "claude_pet.py"
WIN_SOURCE = ROOT / "windows" / "claude_pet_win.py"
WIN_UPDATE = ROOT / "windows" / "win_update.py"
WIN_BUILD = ROOT / "windows" / "build_win.py"
INSTALLER = ROOT / "windows" / "installer.iss"
RELEASE_SH = ROOT / "release.sh"
BUILD_APP_SH = ROOT / "build_app.sh"
SETUP_PY = ROOT / "setup.py"

NEW_NAME = "Token Pet"
OLD_NAME = "Claude Pet"
LANGS = ("en", "ko", "ja", "es")

# ───────────────────────── what a 1.2.0 copy does (copied from tag v1.2.0) ─────────────────────────
FROZEN_MAC_ASSET_NAMES = {
    "arm64": ("claudepet.zip", "claudepet-universal.zip"),
    "x86_64": ("claudepet-universal.zip",),
}
FROZEN_MAC_APP_IN_ZIP = "ClaudePet.app"          # install_update: os.path.join(d, "ClaudePet.app")
FROZEN_MAC_INSTALLED_NAME = "ClaudePet.app"      # app_bundle_path(): basename must equal this
FROZEN_BUNDLE_ID = "me.yeongyu.claudepet"

FROZEN_WIN_SETUP_ASSET = "claude-pet-win-setup.exe"
FROZEN_WIN_ZIP_ASSET = "claude-pet-win.zip"
FROZEN_WIN_APP_DIR = "ClaudePet"
FROZEN_WIN_EXE = "ClaudePet.exe"
FROZEN_WIN_MARKER = os.path.join("_internal", "claudepet-release.json")
FROZEN_WIN_REQUIRED = (
    FROZEN_WIN_EXE,
    os.path.join("_internal", "frames"),
    os.path.join("_internal", "fonts", "Pretendard-SemiBold.ttf"),
    os.path.join("_internal", "fonts", "LICENSE-Pretendard.txt"),
    os.path.join("_internal", ".claude_pet", "pets"),
    os.path.join("_internal", "claudepet.ico"),
    os.path.join("_internal", "logos", "claude.svg"),
    os.path.join("_internal", "logos", "openai.svg"),
    os.path.join("_internal", "logos", "gemini.svg"),
    FROZEN_WIN_MARKER,
)
FROZEN_WIN_ASSET_NAMES = {
    ("AMD64", "inno"): (FROZEN_WIN_SETUP_ASSET,),
    ("AMD64", "portable"): (FROZEN_WIN_ZIP_ASSET,),
}
FROZEN_WIN_ASSET_HOST = "github.com"
FROZEN_INNO_APP_ID = "{{me.yeongyu.claudepet}}"
FROZEN_INNO_UNINSTALL_SUBKEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{me.yeongyu.claudepet}}_is1")
FROZEN_RUN_VALUE_NAME = "ClaudePet"
FROZEN_MUTEX = r"Local\me.yeongyu.claudepet"
FROZEN_INSTALL_DIR = r"{localappdata}\Programs\ClaudePet"


def frozen_select_update_asset(assets, machine):
    """v1.2.0 ``select_update_asset`` → (url, name, arch) or None."""
    allowed = FROZEN_MAC_ASSET_NAMES.get(str(machine))
    if not allowed:
        return None
    by_name = {}
    for a in assets or ():
        name = (a.get("name") or "").strip().lower()
        if name not in allowed:
            continue
        if name in by_name:
            return None
        by_name[name] = a.get("browser_download_url") or ""
    for name in allowed:
        url = by_name.get(name)
        if not url:
            continue
        parts = urllib.parse.urlparse(url)
        if parts.scheme != "https" or not parts.netloc:
            return None
        return (url, name, str(machine))
    return None


def frozen_select_update_asset_win(assets, machine, kind):
    """v1.2.0 ``select_update_asset_win`` → the asset's lower-cased name, or (None, status)."""
    allowed = FROZEN_WIN_ASSET_NAMES.get((machine, kind), ())
    if not allowed:
        return (None, "no-asset")
    by_name = {}
    for a in assets or ():
        name = a.get("name")
        if not isinstance(name, str):
            continue
        name = name.strip().lower()
        if name not in allowed:
            continue
        if name in by_name:
            return (None, "ambiguous-asset")
        by_name[name] = a
    for name in allowed:
        a = by_name.get(name)
        if a is None:
            continue
        parts = urllib.parse.urlparse(a.get("browser_download_url") or "")
        if parts.scheme != "https" or parts.netloc.lower() != FROZEN_WIN_ASSET_HOST:
            return (None, "bad-url")
        return name
    return (None, "missing-asset")


def frozen_validate_portable_layout(extract_dir, expected_tag):
    """v1.2.0 ``validate_portable_layout`` → (ok, reason)."""
    import json
    tag = str(expected_tag or "").strip().lstrip("vV")
    entries = sorted(os.listdir(extract_dir))
    if entries != [FROZEN_WIN_APP_DIR]:
        return (False, f"top-level entries: {entries}")
    app = os.path.join(extract_dir, FROZEN_WIN_APP_DIR)
    if not os.path.isfile(os.path.join(app, FROZEN_WIN_EXE)):
        return (False, "exe missing")
    for rel in FROZEN_WIN_REQUIRED:
        if not os.path.exists(os.path.join(app, rel)):
            return (False, f"required entry missing: {rel}")
    with open(os.path.join(app, FROZEN_WIN_MARKER), encoding="utf-8") as f:
        marker = json.load(f)
    if marker.get("version") != tag:
        return (False, "marker version mismatch")
    return (True, "ok")


# ───────────────────────── reading this tree ─────────────────────────
def _text(path):
    return Path(path).read_text(encoding="utf-8")


def _tree(path):
    return ast.parse(_text(path))


def _module_namespace(path):
    """Module-level ``NAME = <expr>`` assignments that evaluate with only ``os`` and earlier names."""
    ns = {"os": os}
    for node in _tree(path).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        try:
            ns[node.targets[0].id] = eval(  # our own source, names and os.path.join only
                compile(ast.Expression(node.value), str(path), "eval"), {"__builtins__": {}}, ns)
        except Exception:
            continue
    return ns


def _docstring_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _code_strings(path):
    """Every string the program can show: constants and f-string pieces, docstrings excluded."""
    tree = _tree(path)
    skip = _docstring_ids(tree)
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip]


def _sh_var(path, name):
    m = re.search(rf'^{name}="?([^"\s#]+)"?', _text(path), re.M)
    if not m:
        raise AssertionError(f"{Path(path).name}: no {name}= assignment")
    return m.group(1)


def _release_upload_names():
    """Basenames of the four files ``release.sh publish`` uploads."""
    text = _text(RELEASE_SH)
    m = re.search(r'local -a files=\(([^)]*)\)', text)
    if not m:
        raise AssertionError("release.sh: publish()'s files=(…) list not found")
    names = []
    for var in re.findall(r'\$(\w+)', m.group(1)):
        names.append(os.path.basename(_sh_var(RELEASE_SH, var)))
    return names


def _iss_define(name):
    m = re.search(rf'^#define {name} "([^"]*)"', _text(INSTALLER), re.M)
    if not m:
        raise AssertionError(f"installer.iss: no #define {name}")
    return m.group(1)


def _iss_setup(key):
    m = re.search(rf'^{key}=(.*)$', _text(INSTALLER), re.M)
    if not m:
        raise AssertionError(f"installer.iss: no {key}=")
    return m.group(1).strip()


def _setup_plist():
    for node in ast.walk(_tree(SETUP_PY)):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "CFBundleIdentifier" in keys:
                return {k.value: (v.value if isinstance(v, ast.Constant) else None)
                        for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
    raise AssertionError("setup.py: plist dict not found")


def _github_assets(names, tag="v1.2.1"):
    return [{"name": n,
             "browser_download_url":
                 f"https://github.com/BrilliantTiger/token-pet/releases/download/{tag}/{n}"}
            for n in names]


# ═════════════════════════ 1.2.0 → this tree: the update still lands ═════════════════════════
class V120MacUpdaterStillFindsTheReleaseTests(unittest.TestCase):
    def test_the_upload_list_is_the_four_names_v120_knows(self):
        self.assertEqual(
            sorted(_release_upload_names()),
            sorted(["ClaudePet.zip", "ClaudePet-universal.zip",
                    "ClaudePet.dmg", "ClaudePet-universal.dmg"]))

    def test_v120_selects_a_zip_for_each_architecture(self):
        assets = _github_assets(_release_upload_names()
                                + [FROZEN_WIN_ZIP_ASSET, FROZEN_WIN_SETUP_ASSET])
        arm = frozen_select_update_asset(assets, "arm64")
        intel = frozen_select_update_asset(assets, "x86_64")
        self.assertIsNotNone(arm, "a 1.2.0 Apple Silicon copy finds no asset in this release")
        self.assertIsNotNone(intel, "a 1.2.0 Intel copy finds no asset in this release")
        self.assertEqual(arm[1], "claudepet.zip")
        self.assertEqual(intel[1], "claudepet-universal.zip")

    def test_v120_finds_nothing_when_only_new_names_are_published(self):
        # The instrument: the frozen selector really does refuse a renamed-only release.
        assets = _github_assets(["TokenPet.zip", "TokenPet-universal.zip"])
        self.assertIsNone(frozen_select_update_asset(assets, "arm64"))
        self.assertIsNone(frozen_select_update_asset(assets, "x86_64"))

    def test_the_zip_this_tree_builds_has_the_app_where_v120_looks(self):
        for var in ("APP", "UAPP"):
            self.assertEqual(os.path.basename(_sh_var(RELEASE_SH, var).replace("$UDIST/", "")),
                             FROZEN_MAC_APP_IN_ZIP, f"release.sh {var}")
        self.assertEqual(_sh_var(BUILD_APP_SH, "APP"), FROZEN_MAC_APP_IN_ZIP)
        plist = _setup_plist()
        # py2app names dist/<CFBundleName>.app and its executable after this key; the name
        # people see is CFBundleDisplayName and the CFBundleName release.sh writes at signing.
        self.assertEqual(plist["CFBundleName"] + ".app", FROZEN_MAC_APP_IN_ZIP)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src" / (plist["CFBundleName"] + ".app") / "Contents"
            src.mkdir(parents=True)
            with open(src / "Info.plist", "wb") as f:
                plistlib.dump({"CFBundleIdentifier": plist["CFBundleIdentifier"],
                               "CFBundleDisplayName": plist["CFBundleDisplayName"]}, f)
            zp = Path(tmp) / "u.zip"
            with zipfile.ZipFile(zp, "w") as z:
                for p in sorted((Path(tmp) / "src").rglob("*")):
                    z.write(p, p.relative_to(Path(tmp) / "src").as_posix())
            out = Path(tmp) / "out"
            with zipfile.ZipFile(zp) as z:
                z.extractall(out)
            newapp = out / FROZEN_MAC_APP_IN_ZIP
            self.assertTrue(newapp.is_dir(), "1.2.0 looks for ClaudePet.app at the zip root")
            with open(newapp / "Contents" / "Info.plist", "rb") as f:
                got = plistlib.load(f)
            self.assertEqual(got["CFBundleIdentifier"], FROZEN_BUNDLE_ID)

    def test_the_updated_copy_still_recognises_its_own_bundle(self):
        # 1.2.0 swaps the new bundle in at the installed path, so the new code wakes up
        # inside /Applications/ClaudePet.app and must accept that name and that bundle ID.
        ns = _module_namespace(APP_SOURCE)
        self.assertEqual(ns["INSTALLED_BUNDLE_NAME"], FROZEN_MAC_INSTALLED_NAME)
        self.assertEqual(ns["BUNDLE_ID"], FROZEN_BUNDLE_ID)
        self.assertEqual(_setup_plist()["CFBundleIdentifier"], FROZEN_BUNDLE_ID)
        self.assertIn(f"<key>CFBundleIdentifier</key><string>{FROZEN_BUNDLE_ID}</string>",
                      _text(BUILD_APP_SH))
        self.assertIn("<key>CFBundleExecutable</key><string>ClaudePet</string>",
                      _text(BUILD_APP_SH))

    def test_this_trees_own_updater_keeps_the_same_table(self):
        self.assertEqual(_module_namespace(APP_SOURCE)["UPDATE_ASSET_NAMES"],
                         FROZEN_MAC_ASSET_NAMES)


class V120WindowsUpdaterStillFindsTheReleaseTests(unittest.TestCase):
    def setUp(self):
        self.ns = _module_namespace(WIN_UPDATE)

    def test_asset_names_are_the_two_v120_knows(self):
        self.assertEqual(self.ns["SETUP_ASSET"], FROZEN_WIN_SETUP_ASSET)
        self.assertEqual(self.ns["ZIP_ASSET"], FROZEN_WIN_ZIP_ASSET)
        self.assertEqual(_iss_setup("OutputBaseFilename") + ".exe", FROZEN_WIN_SETUP_ASSET)

    def test_v120_selects_the_installer_and_the_portable_zip(self):
        assets = _github_assets(_release_upload_names()
                                + [self.ns["ZIP_ASSET"], self.ns["SETUP_ASSET"]])
        self.assertEqual(frozen_select_update_asset_win(assets, "AMD64", "inno"),
                         FROZEN_WIN_SETUP_ASSET)
        self.assertEqual(frozen_select_update_asset_win(assets, "AMD64", "portable"),
                         FROZEN_WIN_ZIP_ASSET)
        renamed = _github_assets(["token-pet-win.zip", "token-pet-win-setup.exe"])
        self.assertEqual(frozen_select_update_asset_win(renamed, "AMD64", "portable"),
                         (None, "missing-asset"))

    def test_the_portable_tree_this_tree_ships_passes_v120s_layout_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / self.ns["APP_DIR_NAME"]
            for rel in self.ns["PORTABLE_REQUIRED"]:
                p = app / rel
                if p.suffix:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text('{"version": "1.2.1"}' if p.name.endswith(".json") else "x",
                                 encoding="utf-8")
                else:
                    p.mkdir(parents=True, exist_ok=True)
            self.assertEqual(frozen_validate_portable_layout(tmp, "v1.2.1"), (True, "ok"))

    def test_v120s_layout_check_refuses_a_renamed_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "TokenPet").mkdir()
            self.assertFalse(frozen_validate_portable_layout(tmp, "v1.2.1")[0])

    def test_names_on_disk_and_in_the_registry_are_unchanged(self):
        self.assertEqual(self.ns["APP_DIR_NAME"], FROZEN_WIN_APP_DIR)
        self.assertEqual(self.ns["EXE_NAME"], FROZEN_WIN_EXE)
        self.assertEqual(self.ns["RELEASE_MARKER"], FROZEN_WIN_MARKER)
        self.assertEqual(self.ns["RUN_VALUE_NAME"], FROZEN_RUN_VALUE_NAME)
        self.assertEqual(self.ns["MUTEX_NAME"], FROZEN_MUTEX)
        self.assertEqual(self.ns["INNO_UNINSTALL_SUBKEY"], FROZEN_INNO_UNINSTALL_SUBKEY)
        self.assertEqual(self.ns["CACHE_DIR_NAME"], FROZEN_BUNDLE_ID)

    def test_the_installer_upgrades_the_same_installation(self):
        # A silent re-run of the installer is how an installed 1.2.0 updates: same AppId,
        # same folder, same exe — otherwise it installs a second app beside the first.
        self.assertEqual(_iss_setup("AppId"), FROZEN_INNO_APP_ID)
        self.assertEqual(_iss_setup("DefaultDirName"), FROZEN_INSTALL_DIR)
        self.assertEqual(_iss_define("MyAppExeName"), FROZEN_WIN_EXE)
        self.assertIn(f'ValueName: "{FROZEN_RUN_VALUE_NAME}"', _text(INSTALLER))
        self.assertIn('"--name", "ClaudePet"', _text(WIN_BUILD))

    def test_the_installer_removes_the_old_names_shortcuts(self):
        # The shortcut file is named after the app, so an upgrade would leave "Claude Pet"
        # next to "Token Pet" in the Start menu.
        text = _text(INSTALLER)
        m = re.search(r'^\[InstallDelete\]\s*$(.*?)(?=^\[)', text, re.M | re.S)
        self.assertIsNotNone(m, "installer.iss has no [InstallDelete] section")
        body = m.group(1)
        self.assertIn(r'{autoprograms}\Claude Pet.lnk', body)
        self.assertIn(r'{autodesktop}\Claude Pet.lnk', body)


# ═════════════════════════ what the user reads says Token Pet ═════════════════════════
class DisplayNameTests(unittest.TestCase):
    def test_core_strings_in_all_four_languages(self):
        tr = _module_namespace(APP_SOURCE)["TR"]
        self.assertEqual(sorted(tr), sorted(LANGS))
        for lang in LANGS:
            for key, value in tr[lang].items():
                self.assertNotIn(OLD_NAME, value, f"TR[{lang}][{key}]")
                self.assertNotIn("ClaudePet", value, f"TR[{lang}][{key}]")
            for key in ("menu_quit", "settings_title", "upd_title", "unin_title", "r_title"):
                self.assertIn(NEW_NAME, tr[lang][key], f"TR[{lang}][{key}]")

    def test_windows_strings_in_all_four_languages(self):
        tr = _module_namespace(WIN_SOURCE)["TR_WIN"]
        for lang in LANGS:
            for key, value in tr[lang].items():
                self.assertNotIn(OLD_NAME, value, f"TR_WIN[{lang}][{key}]")
            self.assertIn(NEW_NAME, tr[lang]["upd_installing"])

    def test_no_shown_string_carries_the_old_name(self):
        for path in (APP_SOURCE, WIN_SOURCE):
            for s in _code_strings(path):
                self.assertNotIn(OLD_NAME, s, f"{path.name}: {s[:60]!r}")
                # the version line of the menu, the settings window and the tray tooltip
                self.assertFalse(s.startswith("ClaudePet v"), f"{path.name}: {s!r}")

    def test_version_lines_and_window_names_say_token_pet(self):
        core = _code_strings(APP_SOURCE)
        self.assertGreaterEqual(core.count("Token Pet v"), 2)   # menu + settings window
        win = _code_strings(WIN_SOURCE)
        self.assertGreaterEqual(win.count("Token Pet v"), 3)    # menu + settings + tray
        self.assertIn('setApplicationName("Token Pet")', _text(WIN_SOURCE))

    def test_mac_bundle_display_name(self):
        self.assertEqual(_setup_plist()["CFBundleDisplayName"], NEW_NAME)
        self.assertIn(f"<key>CFBundleDisplayName</key><string>{NEW_NAME}</string>",
                      _text(BUILD_APP_SH))
        rel = _text(RELEASE_SH)
        # the name in the keychain prompt (Python.framework) and of the signed bundle itself
        self.assertIn("Set :CFBundleName 'Token Pet'", rel)
        self.assertIn("Add :CFBundleName string 'Token Pet'", rel)
        self.assertIn('"$app/Contents/Info.plist"', rel)
        self.assertNotIn(":CFBundleName ClaudePet", rel)
        self.assertIn(f'-volname "{NEW_NAME}"', rel)
        self.assertIn(f'--title "{NEW_NAME} $TAG"', rel)

    def test_windows_installer_and_version_resource(self):
        self.assertEqual(_iss_define("MyAppName"), NEW_NAME)
        strings = _module_namespace(WIN_BUILD)["VERSION_STRINGS"]
        self.assertEqual(strings["FileDescription"], NEW_NAME)
        self.assertEqual(strings["ProductName"], NEW_NAME)
        self.assertEqual(strings["OriginalFilename"], FROZEN_WIN_EXE)

    def test_readmes_and_site(self):
        for name in ("README.md", "README.ko.md", "README.ja.md", "README.es.md"):
            text = _text(ROOT / name)
            self.assertNotIn(OLD_NAME, text, name)
            self.assertIn(NEW_NAME, text.splitlines()[0], f"{name}: title line")
        for name in ("index.html", "privacy.html"):
            text = _text(ROOT / "docs" / name)
            self.assertNotIn(OLD_NAME, text, f"docs/{name}")
            self.assertIn(NEW_NAME, text, f"docs/{name}")

    def test_release_notes_install_header(self):
        text = _text(ROOT / "RELEASE_NOTES.md")
        head = text[:text.index("**v")]
        self.assertIn(NEW_NAME, head.splitlines()[0])
        self.assertNotIn("BrilliantTiger/claude-pet", head)
        # the files to download keep the names the updater knows
        self.assertIn("**ClaudePet.zip**", head)
        self.assertIn("`ClaudePet.app`", head)


if __name__ == "__main__":
    unittest.main()
