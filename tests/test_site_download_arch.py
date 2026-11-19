"""Gates for the site's download links (TOK-58).

Two things, both about ``docs/`` only — nothing here imports ``claude_pet``.

1. **The macOS hero button follows the chip.**  The user (2026-11-19): "apple slicon은 arm 칩받고
   intel은 universial로 받게 해야지".  ``docs/index.html`` detects the OS from the user agent and
   the chip from Client Hints (Chromium) or the WebGL renderer name (Safari/Firefox).  The hero
   used to link ``ClaudePet-universal.dmg`` whatever was detected.  Now:

   ========================  =============================
   detected                  ``#heroMac`` href
   ========================  =============================
   macOS, Apple Silicon      ``…/ClaudePet.dmg``
   macOS, Intel              ``…/ClaudePet-universal.dmg``
   macOS, chip unknown       ``…/ClaudePet-universal.dmg``
   Windows / anything else   unchanged (Universal)
   ========================  =============================

   Unknown goes to Universal because that build runs on both chips; the arm64 build does not
   open on an Intel Mac.  The static href (no JavaScript, or detection not finished) is the
   Universal one for the same reason.

   **How it is run.**  The page's own code is executed, not re-implemented: the block between the
   two comment markers below is cut out of ``docs/index.html`` and run under ``node`` with
   stand-ins for ``navigator``, ``document``, ``$`` and ``t``.  Nothing is fetched and no browser
   is started.  ``t`` returns the key it was given, so the test reads which i18n key the button
   shows and then looks that key up in the page's four locale tables.

   Without ``node`` the behavioural tests skip **loudly** (stderr + ``skipTest``); a skip is not
   coverage.

2. **No link to the old repository name.**  The repository is ``BrilliantTiger/token-pet``; the
   user: "도메인도 token-pet으로 변경한지가 언젠데 / 아직도 claude-pet이냐".  Nothing under
   ``docs/`` may say ``BrilliantTiger/claude-pet``.  Asset file names (``ClaudePet.dmg`` …) are
   not renamed here — that is TOK-59.

Wrong implementations these are written against: the hero left on Universal for Apple Silicon;
arm64 offered to Intel or to an unknown chip; arm64 as the static href; the href set from the
user agent alone (every Mac says "Intel Mac OS X"); a hero link that differs from the list row
marked "this computer"; the link reverting when the language is switched; a Windows visitor's
Mac button changed; a button text that says Intel on Apple Silicon, or a new text key missing
from a locale; a search-and-replace that renamed the asset files too, or missed a file.
"""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
INDEX = DOCS / "index.html"

BLOCK_START = "// ── which download fits this computer"
BLOCK_END = "// ── sponsor"

MAC_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
WIN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/126.0.0.0 Safari/537.36")
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

ARM_DMG = "ClaudePet.dmg"
UNIVERSAL_DMG = "ClaudePet-universal.dmg"

# Runs the page's block.  argv[2] is a JSON file: {code, ua, uad, gl, hrefs:{heroMac, heroWin}}.
# uad: null | "arm" | "x86" | "throw" | "empty"   gl: null | "throw" | renderer string
HARNESS = r"""
const fs = require("fs");
const c = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const els = {}, picked = [];
function el(id){
  if (!els[id]) els[id] = {id, href: (c.hrefs[id] || ""), className: "", textContent: "", hidden: true,
    afterArg: null, after(x){ this.afterArg = x && x.id; },
    classList: {added: [], add(n){ this.added.push(n); }}};
  return els[id];
}
const $ = el;
const t = (key, vars) => key + (vars && vars.label ? "|" + vars.label : "");
const navigator = {userAgent: c.ua};
if (c.uad === "arm" || c.uad === "x86")
  navigator.userAgentData = {getHighEntropyValues: async () => ({architecture: c.uad, bitness: "64"})};
else if (c.uad === "empty")
  navigator.userAgentData = {getHighEntropyValues: async () => ({})};
else if (c.uad === "throw")
  navigator.userAgentData = {getHighEntropyValues: async () => { throw new Error("denied"); }};
const document = {
  createElement(){ return {getContext(){
    if (c.gl === "throw") throw new Error("no webgl");
    if (c.gl === null) return null;
    return {getExtension(){ return {UNMASKED_RENDERER_WEBGL: 37446}; }, getParameter(){ return c.gl; }};
  }}; },
  querySelector(sel){ const e = {sel, classList: {added: [], add(n){ this.added.push(n); }}}; picked.push(e); return e; },
  getElementById: el,
};
const requestAnimationFrame = () => 0, dispatchEvent = () => true;
class Event { constructor(n){ this.type = n; } }
const run = new Function("navigator", "document", "$", "t", "requestAnimationFrame", "dispatchEvent", "Event",
  c.code + "\nreturn typeof paintHero === 'function' ? paintHero : null;");
const paintHero = run(navigator, document, $, t, requestAnimationFrame, dispatchEvent, Event);
const snap = () => ({mac: el("heroMac").href, win: el("heroWin").href, text: el("heroMacTxt").textContent});
const first = snap();                      // before detection has answered (it is asynchronous)
setTimeout(() => {
  const settled = snap();
  let again = null;
  if (paintHero){ paintHero(); again = snap(); }   // what a language switch does
  process.stdout.write(JSON.stringify({first, settled, again,
    mine: picked.filter(e => e.classList.added.includes("mine")).map(e => e.sel),
    winClass: el("heroWin").className, macClass: el("heroMac").className, winAfter: el("heroWin").afterArg}));
}, 30);
"""


def _index() -> str:
    return INDEX.read_text(encoding="utf-8")


def _detection_block(text: str) -> str:
    if text.count(BLOCK_START) != 1 or BLOCK_END not in text:
        raise AssertionError("docs/index.html no longer has the detection block between "
                             f"{BLOCK_START!r} and {BLOCK_END!r}; this test cuts the page's own "
                             "code out by those two comments")
    start = text.index(BLOCK_START)
    return text[start:text.index(BLOCK_END, start)]


def _anchor_href(text: str, pattern: str) -> str:
    tags = [m.group(0) for m in re.finditer(r"<a\b[^>]*>", text) if re.search(pattern, m.group(0))]
    if len(tags) != 1:
        raise AssertionError(f"expected one <a> matching {pattern!r} in docs/index.html, found {len(tags)}")
    href = re.search(r'href="([^"]*)"', tags[0])
    if not href:
        raise AssertionError(f"the <a> matching {pattern!r} has no href")
    return href.group(1)


def _locale_values(text: str, key: str) -> list[str]:
    return [json.loads('"' + m.group(1) + '"')
            for m in re.finditer(r'^\s*"' + re.escape(key) + r'":\s*"((?:[^"\\]|\\.)*)"', text, re.M)]


class HeroDownloadFollowsTheChipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            sys.stderr.write("\nSKIP test_site_download_arch: `node` is not installed — the site's "
                             "download script was NOT run; this is not coverage.\n")
            raise unittest.SkipTest("node is not installed; the page script was not run")
        cls.text = _index()
        cls.block = _detection_block(cls.text)
        cls.static = {"heroMac": _anchor_href(cls.text, r'id="heroMac"'),
                      "heroWin": _anchor_href(cls.text, r'id="heroWin"')}
        cls.row = {"arm": _anchor_href(cls.text, r'data-arch="arm"'),
                   "x86": _anchor_href(cls.text, r'data-arch="x86"')}

    def run_page(self, ua, uad=None, gl=None):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case.json"
            case.write_text(json.dumps({"code": self.block, "ua": ua, "uad": uad, "gl": gl,
                                        "hrefs": self.static}), encoding="utf-8")
            harness = Path(tmp) / "harness.js"
            harness.write_text(HARNESS, encoding="utf-8")
            done = subprocess.run([self.node, str(harness), str(case)], capture_output=True,
                                  text=True, timeout=30, cwd=tmp)
        self.assertEqual(done.returncode, 0, "the page's detection block failed under node:\n" + done.stderr[-800:])
        return json.loads(done.stdout)

    def assert_file(self, href, name, msg):
        self.assertEqual(href.rsplit("/", 1)[-1], name, msg)
        self.assertRegex(href, r"^https://github\.com/BrilliantTiger/[^/]+/releases/latest/download/[^/]+$", msg)

    # ── the premises: what the page holds before any script runs ──

    def test_the_static_link_is_universal_and_the_two_list_rows_are_the_two_builds(self):
        """No JavaScript, or detection not finished: the button must work on every Mac."""
        self.assert_file(self.static["heroMac"], UNIVERSAL_DMG, "the static hero link must be the Universal DMG")
        self.assert_file(self.row["arm"], ARM_DMG, "the Apple Silicon list row")
        self.assert_file(self.row["x86"], UNIVERSAL_DMG, "the Intel list row")

    # ── Apple Silicon ──

    def test_apple_silicon_gets_the_arm_build(self):
        """Both ways the page learns the chip: Client Hints (Chromium) and the GPU name
        (Safari/Firefox, where the user agent says "Intel Mac OS X" on every Mac)."""
        for name, uad, gl in (("client hints", "arm", None),
                              ("gpu name, Apple M-series", None, "Apple M2"),
                              ("gpu name, ANGLE", None, "ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)"),
                              ("gpu name, Apple GPU", None, "Apple GPU"),
                              ("client hints empty, gpu name", "empty", "Apple M3"),
                              ("client hints refused, gpu name", "throw", "Apple M3")):
            with self.subTest(name):
                out = self.run_page(MAC_UA, uad, gl)
                self.assert_file(out["settled"]["mac"], ARM_DMG, "Apple Silicon must get the arm64 DMG")
                self.assertEqual(out["settled"]["mac"], self.row["arm"],
                                 "the hero link differs from the Apple Silicon row of the list")
                self.assertEqual(out["mine"], ["[data-os=mac] [data-arch=arm]"],
                                 "the list must mark the Apple Silicon row as this computer")
                self.assertEqual(out["settled"]["win"], self.static["heroWin"], "the Windows button changed")

    def test_the_arm_link_survives_a_language_switch(self):
        """Switching language repaints the hero.  Rival: the link set once, then put back."""
        out = self.run_page(MAC_UA, "arm", None)
        self.assertIsNotNone(out["again"], "paintHero is gone; the language switch repaints through it")
        self.assert_file(out["again"]["mac"], ARM_DMG, "after a repaint the link is no longer the arm64 DMG")
        self.assertEqual(out["again"]["text"], out["settled"]["text"])

    # ── Intel and unknown ──

    def test_intel_gets_universal(self):
        for name, uad, gl in (("client hints", "x86", None),
                              ("gpu name, Intel", None, "Intel(R) Iris(TM) Plus Graphics 655"),
                              ("gpu name, AMD", None, "AMD Radeon Pro 5500M OpenGL Engine")):
            with self.subTest(name):
                out = self.run_page(MAC_UA, uad, gl)
                self.assert_file(out["settled"]["mac"], UNIVERSAL_DMG, "Intel must get the Universal DMG")
                self.assertEqual(out["settled"]["mac"], self.row["x86"],
                                 "the hero link differs from the Intel row of the list")
                self.assertEqual(out["mine"], ["[data-os=mac] [data-arch=x86]"])
                if out["again"] is not None:
                    self.assert_file(out["again"]["mac"], UNIVERSAL_DMG, "after a repaint")

    def test_an_unknown_chip_gets_universal(self):
        """The arm64 build does not open on an Intel Mac, so a guess is not allowed.  The user
        agent alone never settles it — MAC_UA says "Intel" and is what Apple Silicon sends too."""
        for name, uad, gl in (("nothing to ask", None, None),
                              ("no renderer extension answer", None, ""),
                              ("an unrecognised renderer", None, "llvmpipe (LLVM 15.0.7, 256 bits)"),
                              ("client hints empty, no webgl", "empty", None),
                              ("both refuse", "throw", "throw")):
            with self.subTest(name):
                out = self.run_page(MAC_UA, uad, gl)
                self.assert_file(out["settled"]["mac"], UNIVERSAL_DMG, "an unknown chip must get the Universal DMG")
                self.assertEqual(out["mine"], [], "no list row may be marked when the chip is unknown")
                if out["again"] is not None:
                    self.assert_file(out["again"]["mac"], UNIVERSAL_DMG, "after a repaint")

    def test_before_detection_answers_the_link_is_universal(self):
        """Detection is asynchronous.  A click in that gap must not hand arm64 to an Intel Mac."""
        for uad, gl in (("arm", None), ("x86", None), (None, None)):
            with self.subTest(uad=uad):
                out = self.run_page(MAC_UA, uad, gl)
                self.assert_file(out["first"]["mac"], UNIVERSAL_DMG, "before detection the link must be Universal")

    # ── everything that is not a Mac ──

    def test_windows_and_other_devices_leave_the_mac_button_alone(self):
        """A Windows visitor still sees a Mac button (second); it is for another computer, whose
        chip nobody knows — Universal.  Windows ARM reports architecture "arm": that must not be
        read as an Apple Silicon Mac."""
        for name, ua, uad, gl in (("windows x64", WIN_UA, "x86", None),
                                  ("windows arm", WIN_UA, "arm", None),
                                  ("windows, apple-looking renderer", WIN_UA, None, "Apple M2"),
                                  ("iphone", IPHONE_UA, None, "Apple GPU"),
                                  ("iphone with arm hints", IPHONE_UA, "arm", None)):
            with self.subTest(name):
                out = self.run_page(ua, uad, gl)
                for when in ("first", "settled", "again"):
                    if out[when] is None:
                        continue
                    self.assertEqual(out[when]["mac"], self.static["heroMac"], f"{when}: the Mac button changed")
                    self.assertEqual(out[when]["win"], self.static["heroWin"], f"{when}: the Windows button changed")
                self.assertNotIn("[data-os=mac] [data-arch=arm]", out["mine"])
        out = self.run_page(WIN_UA, "x86", None)
        self.assertEqual((out["winClass"], out["macClass"], out["winAfter"]), ("btn primary", "btn ghost", "heroMac"),
                         "on Windows the Windows button is still the first, primary one")
        self.assertEqual(out["mine"], ["[data-os=win] [data-arch=x64]"])

    # ── the words on the button ──

    def test_the_button_text_matches_the_file_in_all_four_languages(self):
        """Whatever key the button shows must exist in en/ko/ja/es.  On Apple Silicon it must not
        say Intel; on Intel it says Intel, as before; with the chip unknown it names no chip."""
        shown = {}
        for chip, uad, gl in (("arm", "arm", None), ("x86", "x86", None), ("unknown", None, None)):
            key = self.run_page(MAC_UA, uad, gl)["settled"]["text"]
            values = _locale_values(self.text, key)
            self.assertEqual(len(values), 4, f"{chip}: the button shows {key!r}, which is in "
                                              f"{len(values)} of the four locale tables")
            self.assertTrue(all(v.strip() for v in values), f"{chip}: {key!r} is empty in a locale")
            shown[chip] = (key, values)
        for value in shown["arm"][1]:
            self.assertNotRegex(value, r"(?i)intel", f"on Apple Silicon the button says Intel: {value!r}")
            self.assertNotRegex(value, r"(?i)universal", f"on Apple Silicon the button says Universal: {value!r}")
        for value in shown["x86"][1]:
            self.assertRegex(value, r"(?i)intel", f"on Intel the button no longer says Intel: {value!r}")
        for value in shown["unknown"][1]:
            self.assertNotRegex(value, r"(?i)intel|apple\s*silicon|\barm", f"chip unknown, yet the button names one: {value!r}")
        self.assertNotEqual(shown["arm"][0], shown["x86"][0])

    def test_the_stale_comment_is_gone(self):
        """The two comments that said the hero never changes described the old behaviour."""
        for stale in ("the hero always links the Universal DMG", "the hero keeps the Universal DMG"):
            self.assertNotIn(stale, self.text, f"docs/index.html still says {stale!r}")


class NoOldRepositoryNameTests(unittest.TestCase):
    """``docs/`` links the repository by its current name.  Needs no node."""

    OLD = "BrilliantTiger/claude-pet"
    NEW = "BrilliantTiger/token-pet"
    # The four files the page links today (the macOS .zip pair is for the updater; the page
    # has never linked it).
    ASSETS = ("ClaudePet.dmg", "ClaudePet-universal.dmg", "claude-pet-win-setup.exe", "claude-pet-win.zip")

    def texts(self):
        out = {}
        for path in sorted(DOCS.rglob("*")):
            if not path.is_file():
                continue
            try:
                out[path.relative_to(REPO).as_posix()] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue                      # images and fonts
        return out

    def test_nothing_under_docs_names_the_old_repository(self):
        texts = self.texts()
        self.assertIn("docs/index.html", texts)
        hits = {name: len(re.findall(re.escape(self.OLD), text, re.I)) for name, text in texts.items()}
        hits = {name: n for name, n in hits.items() if n}
        self.assertEqual(hits, {}, "docs/ still links the old repository name (file: count)")

    def test_every_github_link_to_this_project_uses_the_current_name(self):
        """Rival to a blind replace: links that ended up at a third spelling.  Sponsor and author
        links (``uygnoey``) are not this repository and stay."""
        bad = {}
        seen = 0
        for name, text in self.texts().items():
            for owner, repo in re.findall(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text):
                if owner.lower() != "brillianttiger":
                    continue
                seen += 1
                if f"{owner}/{repo}".rstrip(".") != self.NEW:
                    bad.setdefault(name, set()).add(f"{owner}/{repo}")
        self.assertEqual(bad, {})
        self.assertGreaterEqual(seen, 30, "the pages lost their repository links altogether")

    def test_the_asset_file_names_are_not_renamed(self):
        """Renaming the files is TOK-59.  A release serves these exact names, and the updater's
        table lists them; a link to ``TokenPet.dmg`` would be a 404 today."""
        index = _index()
        for asset in self.ASSETS:
            self.assertIn(f"https://github.com/{self.NEW}/releases/latest/download/{asset}", index,
                          f"docs/index.html no longer links {asset} under the current repository name")
        linked = set(re.findall(r"releases/latest/download/([A-Za-z0-9._-]+)", index))
        self.assertEqual(linked, set(self.ASSETS), "the page links a download file other than the four")


if __name__ == "__main__":
    unittest.main()
