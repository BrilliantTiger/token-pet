"""TOK-60 — 릴리스는 CI 가 한다: 태그 push → release.yml 이 빌드·서명·공증·게시.

두 가지를 본다.

1. **워크플로 파일의 모양**(정적). 서명 인증서가 있는 러너에서 무엇이 돌 수 있는가는 YAML 몇 줄이
   정한다 — `pull_request` 한 줄이 들어가면 남의 코드가 대표님 인증서 옆에서 돈다. 그래서 그 줄들을
   글자로 고정한다. YAML 파서를 쓰지 않는다(이 스위트는 stdlib 만으로 돈다): 잡 블록은 `jobs:` 아래
   두 칸 들여쓴 키로 나눈다.
2. **`ci/release_ci.py` 의 판정**(순수 함수). 게시해도 되는가(태그·버전·main 의 CI), 올라간 자산이
   만든 것과 같은가. 서버·gh·서명 도구는 부르지 않는다.

각 검사는 그것이 막는 틀린 구현을 독스트링에 적었다.
"""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE_YML = WORKFLOWS / "release.yml"
TESTS_YML = WORKFLOWS / "tests.yml"
SAME_REPO_PR = "github.event.pull_request.head.repo.full_name == github.repository"
SIX_ASSETS = ("ClaudePet.zip", "ClaudePet-universal.zip", "ClaudePet.dmg", "ClaudePet-universal.dmg",
              "claude-pet-win.zip", "claude-pet-win-setup.exe")


def _load_release_ci():
    spec = importlib.util.spec_from_file_location("release_ci", ROOT / "ci" / "release_ci.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _code(text):
    """주석을 뺀 본문. 주석에 적힌 낱말(예: 'pull_request 로는 돌지 않는다')이 검사에 걸리면 안 된다."""
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())


def _on_block(text):
    m = re.search(r"^on:\n(.*?)(?=^\S)", _code(text), re.S | re.M)
    assert m, "워크플로에 on: 블록이 없다"
    return m.group(1)


def _jobs(text):
    """{잡 이름: 블록 본문} — jobs: 아래 두 칸 들여쓴 키로 나눈다."""
    body = _code(text).split("\njobs:\n", 1)[1]
    out, name = {}, None
    for line in body.splitlines():
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            name = m.group(1)
            out[name] = ""
        elif name:
            out[name] += line + "\n"
    return out


def _runs(block):
    """잡 블록의 run: 본문들(한 줄짜리와 `run: |` 블록)."""
    out = []
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", lines[i])
        if m:
            indent = len(m.group(1))
            if m.group(2) in ("|", ">", "|-", ">-"):
                chunk = []
                i += 1
                while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
                    chunk.append(lines[i].strip())
                    i += 1
                out.append("\n".join(chunk))
                continue
            out.append(m.group(2))
        i += 1
    return out


class ReleaseWorkflowShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = RELEASE_YML.read_text(encoding="utf-8")
        cls.jobs = _jobs(cls.text)

    def test_triggers_are_version_tags_and_manual_only(self):
        """pull_request(_target)·브랜치 push·schedule 로 서명 러너가 돌면 안 된다."""
        on = _on_block(self.text)
        keys = re.findall(r"^  ([a-z_]+):", on, re.M)
        self.assertEqual(sorted(keys), ["push", "workflow_dispatch"])
        self.assertIn("v*.*.*", on)
        self.assertNotIn("branches", on)
        self.assertNotIn("pull_request", _code(self.text).split("\njobs:\n")[0])

    def test_jobs(self):
        self.assertEqual(sorted(self.jobs), ["gate", "mac", "publish", "win"])

    def test_signing_jobs_wait_for_the_gate(self):
        """게이트가 거절했는데 서명·공증이 먼저 나가면 안 된다 — 두 빌드 잡 모두 gate 를 기다린다."""
        for name in ("mac", "win"):
            self.assertRegex(self.jobs[name], r"needs:\s*\[?\s*gate\b", name)
        needs = re.search(r"needs:\s*\[([^\]]*)\]", self.jobs["publish"]).group(1)
        self.assertEqual(sorted(x.strip() for x in needs.split(",")), ["gate", "mac", "win"])

    def test_runners(self):
        self.assertRegex(self.jobs["mac"], r"runs-on:\s*\[self-hosted,\s*macOS,\s*token-pet\]")
        self.assertRegex(self.jobs["win"], r"runs-on:\s*\[self-hosted,\s*Windows,\s*token-pet\]")
        for name in ("gate", "publish"):
            self.assertNotIn("self-hosted", self.jobs[name], name)

    def test_mac_job_runs_release_sh_step_by_step(self):
        """build → sign → notarize → universal → dmg, 한 단계에 하나씩. all·ship·인자 없는 호출과
        release.sh publish(초안 없이 바로 게시한다)는 부르지 않는다."""
        calls = []
        for run in _runs(self.jobs["mac"]):
            found = re.findall(r"\./release\.sh(?:[ \t]+(\S+))?", run)
            if found:
                self.assertEqual(len(found), 1, "release.sh 는 한 단계에 한 번")
                calls.append(found[0])
        self.assertEqual(calls, ["build", "sign", "notarize", "universal", "dmg"])

    def test_no_stored_secrets(self):
        """인증서·공증 프로필은 러너의 키체인에 있다. 저장소 시크릿으로 옮기지 않는다."""
        secrets = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", self.text))
        self.assertLessEqual(secrets, {"GITHUB_TOKEN"})
        for word in ("--password", "--apple-id", "CLAUDE_PET_WIN_PFX", "security unlock-keychain", "set -x"):
            self.assertNotIn(word, _code(self.text))

    def test_token_permissions(self):
        """쓰기 권한은 게시 잡에만. 빌드 잡의 토큰으로는 릴리스를 건드릴 수 없다."""
        top = _code(self.text).split("\njobs:\n")[0]
        self.assertRegex(top, r"permissions:\n  contents: read\n")
        self.assertNotIn("write", top)
        self.assertRegex(self.jobs["publish"], r"permissions:\n\s+contents: write")
        for name in ("gate", "mac", "win"):
            self.assertNotIn("write", self.jobs[name], name)

    def test_one_release_at_a_time(self):
        top = _code(self.text).split("\njobs:\n")[0]
        self.assertRegex(top, r"concurrency:\n  group: release\n  cancel-in-progress: false")

    def test_mode_comes_from_the_gate_only(self):
        """게시 여부는 gate 잡의 출력 하나로 정한다. 사람이 고르는 입력(dry_run=false 같은)이 있으면
        workflow_dispatch 로 게시가 나간다."""
        self.assertNotIn("inputs", _code(self.text))
        self.assertIn("needs.gate.outputs.mode", self.jobs["publish"])

    def test_six_assets_named(self):
        for name in SIX_ASSETS:
            self.assertIn(name, self.text)


class SelfHostedJobsNeverRunForForks(unittest.TestCase):
    def test_every_self_hosted_job_is_guarded(self):
        """pull_request 로 도는 워크플로의 self-hosted 잡은 전부 '같은 저장소의 PR' 조건을 단다.
        조건 없는 잡 하나가 생기면 포크의 코드가 서명 인증서가 있는 기기에서 돈다."""
        seen = 0
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            on = _on_block(text)
            self.assertNotIn("pull_request_target", on, path.name)
            if "pull_request" not in on:
                continue
            for name, block in _jobs(text).items():
                if "self-hosted" not in block:
                    continue
                seen += 1
                cond = re.search(r"if:(.*?)runs-on:", block, re.S)
                self.assertIsNotNone(cond, f"{path.name}:{name} 에 if: 가 없다")
                self.assertIn(SAME_REPO_PR, cond.group(1), f"{path.name}:{name}")
                self.assertNotRegex(cond.group(1), r"event_name == 'pull_request'\s*(\|\||\)?\s*$)",
                                    f"{path.name}:{name} — 조건 없는 pull_request")
        self.assertEqual(seen, 2, "tests.yml 의 실기기 잡 둘")

    def test_tests_yml_does_not_rerun_on_tags(self):
        """태그는 main 에서 이미 초록인 커밋에 붙는다. 같은 것을 다시 돌리면 릴리스 잡과 같은 러너를
        두고 줄을 선다."""
        self.assertNotIn("tags", _on_block(TESTS_YML.read_text(encoding="utf-8")))


class GateDecisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rc = _load_release_ci()

    def test_assets_match_the_updaters(self):
        """이름 표가 업데이터의 것과 갈리면 설치된 사본이 조용히 영원히 재시도한다."""
        self.assertEqual(tuple(self.rc.ASSETS), SIX_ASSETS)
        src = (ROOT / "claude_pet.py").read_text(encoding="utf-8")
        table = re.search(r"^UPDATE_ASSET_NAMES = \{(.*?)^\}", src, re.S | re.M).group(1)
        mac = set(re.findall(r'"(claudepet[a-z-]*\.zip)"', table))
        self.assertEqual(mac, {n.lower() for n in SIX_ASSETS[:2]})
        win = (ROOT / "windows" / "win_update.py").read_text(encoding="utf-8")
        self.assertEqual({re.search(r'^ZIP_ASSET = "([^"]+)"', win, re.M).group(1),
                          re.search(r'^SETUP_ASSET = "([^"]+)"', win, re.M).group(1)}, set(SIX_ASSETS[4:]))

    def test_mode(self):
        """게시는 push 된 vX.Y.Z 태그 하나뿐. 나머지는 전부 시험이다."""
        mode = self.rc.release_mode
        self.assertEqual(mode("push", "refs/tags/v1.2.2"), "publish")
        self.assertEqual(mode("push", "refs/tags/v10.0.13"), "publish")
        for event, ref in (("workflow_dispatch", "refs/tags/v1.2.2"), ("workflow_dispatch", "refs/heads/main"),
                           ("push", "refs/tags/v0.0.0-test"), ("push", "refs/tags/v1.2"),
                           ("push", "refs/tags/v1.2.2.1"), ("push", "refs/heads/v1.2.2"),
                           ("pull_request", "refs/tags/v1.2.2"), ("push", "refs/tags/v1.2.2\n")):
            self.assertEqual(mode(event, ref), "dry-run", (event, ref))

    def test_tag_must_be_the_app_version(self):
        p = self.rc.version_problems
        self.assertEqual(p("v1.2.2", "1.2.2"), [])
        self.assertTrue(p("v1.2.2", "1.2.1"))
        self.assertTrue(p("v1.2.2", "1.2.20"))
        self.assertTrue(p("1.2.2", "1.2.2"))
        self.assertTrue(p("v1.2.2", ""))

    def test_notes_must_have_the_section(self):
        p = self.rc.notes_problems
        notes = "### 변경 내역\n\n**v1.2.2**\n- a\n\n**v1.2.1**\n- b\n"
        self.assertEqual(p(notes, "1.2.2"), [])
        self.assertEqual(p(notes, "1.2.1"), [])
        self.assertTrue(p(notes, "1.2"))
        self.assertTrue(p(notes, "1.2.3"))

    # ── main 의 CI ──────────────────────────────────────────────────────────────────────
    SHA = "a" * 40

    def _run(self, **kw):
        run = {"id": 7, "event": "push", "head_branch": "main", "head_sha": self.SHA,
               "status": "completed", "conclusion": "success", "path": ".github/workflows/tests.yml"}
        run.update(kw)
        return run

    def _jobs(self, **override):
        jobs = {"macOS — full suite": "success", "Windows — gating contract": "success",
                "macOS — built .app (unsigned)": "success", "Windows — built exe (unsigned)": "success",
                "Real Mac — installed CLIs, real sign-in": "success",
                "Real Windows — installed CLIs, real sign-in": "success"}
        jobs.update(override)
        return [{"name": k, "status": "completed", "conclusion": v} for k, v in jobs.items() if v is not None]

    def test_green_main_run_passes(self):
        run = self.rc.pick_main_run([self._run()], self.SHA)
        self.assertEqual(run["id"], 7)
        self.assertEqual(self.rc.ci_problems(run, self._jobs()), [])

    def test_pick_ignores_runs_that_are_not_mains_push(self):
        """PR·수동 실행·다른 브랜치·다른 커밋의 초록은 main 의 초록이 아니다."""
        pick = self.rc.pick_main_run
        for other in (self._run(event="pull_request"), self._run(event="workflow_dispatch"),
                      self._run(head_branch="dev"), self._run(head_sha="b" * 40),
                      self._run(head_branch="v1.2.2")):
            self.assertIsNone(pick([other], self.SHA), other)
        self.assertEqual(pick([self._run(id=3, conclusion="failure"), self._run(id=9)], self.SHA)["id"], 9)
        # 다시 돌린 것이 빨갛다면 옛 초록으로 넘어가지 않는다 — 가장 최근 실행을 본다.
        self.assertEqual(pick([self._run(id=3), self._run(id=9, conclusion="failure")], self.SHA)["id"], 9)

    def test_no_run_or_unfinished_or_red_fails(self):
        p = self.rc.ci_problems
        self.assertTrue(p(None, []))
        self.assertTrue(p(self._run(status="in_progress", conclusion=None), self._jobs()))
        self.assertTrue(p(self._run(conclusion="failure"), self._jobs()))
        self.assertTrue(p(self._run(conclusion="cancelled"), self._jobs()))

    def test_every_job_must_be_success(self):
        """실행 전체가 success 로 보여도 잡 하나가 skipped·failure 면 통과가 아니다."""
        p = self.rc.ci_problems
        for bad in ("failure", "skipped", "cancelled", "neutral"):
            self.assertTrue(p(self._run(), self._jobs(**{"macOS — full suite": bad})), bad)

    def test_real_machine_jobs_must_have_run(self):
        """실기기 잡이 아예 없거나(조건에서 빠짐) 건너뛴 실행은 실기기에서 확인한 것이 아니다."""
        p = self.rc.ci_problems
        for name in ("Real Mac — installed CLIs, real sign-in", "Real Windows — installed CLIs, real sign-in"):
            self.assertTrue(p(self._run(), self._jobs(**{name: None})), name)
            self.assertTrue(p(self._run(), self._jobs(**{name: "skipped"})), name)

    def test_real_job_names_exist_in_tests_yml(self):
        """게이트가 찾는 이름이 tests.yml 의 잡 이름과 갈리면 게이트는 영원히 실패한다."""
        text = TESTS_YML.read_text(encoding="utf-8")
        for prefix in self.rc.REAL_JOB_PREFIXES:
            self.assertRegex(text, r"name: %s\b" % re.escape(prefix))

    # ── 올라간 자산 ─────────────────────────────────────────────────────────────────────
    def _assets(self):
        return [{"name": n, "size": 100 + i, "sha256": ("%02x" % i) * 32} for i, n in enumerate(SIX_ASSETS)]

    def test_uploaded_assets_equal_built_ones(self):
        p = self.rc.asset_problems
        self.assertEqual(p(self._assets(), self._assets()), [])
        self.assertEqual(p(self._assets(), list(reversed(self._assets()))), [])

    def test_asset_differences_are_refused(self):
        """빠짐·남음·크기·해시 — 넷 다 따로 잡는다. 해시가 비어 있는 것도 '같다'가 아니다."""
        p = self.rc.asset_problems
        self.assertTrue(p(self._assets(), self._assets()[:-1]))
        self.assertTrue(p(self._assets(), self._assets() + [{"name": "x.zip", "size": 1, "sha256": "0" * 64}]))
        for key, value in (("size", 1), ("sha256", "f" * 64), ("sha256", ""), ("sha256", None)):
            got = self._assets()
            got[2][key] = value
            self.assertTrue(p(self._assets(), got), (key, value))

    def test_expected_set_must_be_the_six(self):
        """만든 쪽 목록이 여섯이 아니면 비교할 것도 없이 거절한다(다섯 개가 서로 같다고 통과하면 안 된다)."""
        p = self.rc.asset_problems
        self.assertTrue(p(self._assets()[:5], self._assets()[:5]))
        dup = self._assets()[:5] + [self._assets()[0]]
        self.assertTrue(p(dup, dup))


if __name__ == "__main__":
    unittest.main()
