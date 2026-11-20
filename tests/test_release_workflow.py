"""TOK-60 — 릴리스는 CI 가 한다: release.yml 이 빌드·서명·공증·게시.
TOK-64 — 태그도 CI 가 단다: main 의 CI 가 초록이고 버전이 올라갔으면 auto-tag.yml 이 태그를 달고 release.yml 을
깨운다. 사람이 태그를 미는 단계는 없다.

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
AUTO_TAG_YML = WORKFLOWS / "auto-tag.yml"
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

    def test_workflow_run_workflows_have_no_self_hosted_job(self):
        """workflow_run 은 포크 PR 의 실행이 끝났을 때도 깨어난다. 그런 워크플로에 self-hosted 잡이 있으면
        조건 한 줄을 잘못 쓴 날 서명 러너가 돈다 — 아예 두지 않는다."""
        seen = 0
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            if "workflow_run" not in _on_block(text):
                continue
            seen += 1
            self.assertNotIn("self-hosted", _code(text), path.name)
        self.assertEqual(seen, 1, "auto-tag.yml 하나")

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
        """게시는 vX.Y.Z 태그 ref 에서 도는 실행뿐 — CI 가 단 태그(auto-tag.yml 이 workflow_dispatch 로 깨운다)와
        push 된 태그. 브랜치에서의 수동 실행과 그 밖의 모든 것은 시험이다."""
        mode = self.rc.release_mode
        self.assertEqual(mode("push", "refs/tags/v1.2.2"), "publish")
        self.assertEqual(mode("push", "refs/tags/v10.0.13"), "publish")
        self.assertEqual(mode("workflow_dispatch", "refs/tags/v1.2.3"), "publish")
        for event, ref in (("workflow_dispatch", "refs/heads/main"), ("workflow_dispatch", "refs/heads/v1.2.2"),
                           ("workflow_dispatch", "refs/tags/v0.0.0-test"), ("workflow_dispatch", "refs/tags/v1.2"),
                           ("push", "refs/tags/v0.0.0-test"), ("push", "refs/tags/v1.2"),
                           ("push", "refs/tags/v1.2.2.1"), ("push", "refs/heads/v1.2.2"),
                           ("pull_request", "refs/tags/v1.2.2"), ("workflow_run", "refs/tags/v1.2.2"),
                           ("schedule", "refs/tags/v1.2.2"), ("push", "refs/tags/v1.2.2\n"),
                           ("workflow_dispatch", "refs/tags/v1.2.2\n"), ("workflow_dispatch", None)):
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


class AutoTagWorkflowShape(unittest.TestCase):
    """auto-tag.yml — tests.yml 의 main push 실행이 끝나면 돌아, 버전이 올라갔을 때만 태그를 단다."""

    @classmethod
    def setUpClass(cls):
        cls.text = AUTO_TAG_YML.read_text(encoding="utf-8")
        cls.jobs = _jobs(cls.text)
        cls.top = _code(cls.text).split("\njobs:\n")[0]

    def test_only_trigger_is_the_tests_workflow_finishing_on_main(self):
        """push·pull_request·schedule·workflow_dispatch 로 태그가 달리면 안 된다 — main 의 CI 가 끝난 것만이
        이 워크플로를 깨운다."""
        on = _on_block(self.text)
        self.assertEqual(re.findall(r"^  ([a-z_]+):", on, re.M), ["workflow_run"])
        self.assertRegex(on, r'workflows:\s*\["tests"\]')
        self.assertRegex(on, r"types:\s*\[completed\]")
        self.assertRegex(on, r"branches:\s*\[main\]")
        self.assertRegex(TESTS_YML.read_text(encoding="utf-8"), r"(?m)^name: tests$")

    def test_one_job_on_a_hosted_runner(self):
        self.assertEqual(sorted(self.jobs), ["tag"])
        self.assertRegex(self.jobs["tag"], r"runs-on:\s*ubuntu-latest")

    def test_job_condition_is_mains_own_green_push(self):
        """`branches: [main]` 은 포크의 'main' 브랜치에서 온 PR 실행에도 맞는다. 그래서 잡 조건이 네 가지를
        모두 본다: push 실행, main, success, 이 저장소. 하나라도 빠지면 포크 PR 의 초록이 태그를 단다."""
        cond = re.search(r"if:(.*?)runs-on:", self.jobs["tag"], re.S)
        self.assertIsNotNone(cond, "tag 잡에 if: 가 없다")
        cond = cond.group(1)
        for need in ("github.event.workflow_run.event == 'push'",
                     "github.event.workflow_run.head_branch == 'main'",
                     "github.event.workflow_run.conclusion == 'success'",
                     "github.event.workflow_run.head_repository.full_name == github.repository"):
            self.assertIn(need, cond)
        self.assertNotIn("||", cond, "조건은 전부 && 로 묶는다")

    def test_checks_out_the_commit_that_was_tested(self):
        """workflow_run 의 기본 체크아웃은 그때의 main 끝이다 — 시험한 커밋이 아닐 수 있다."""
        self.assertRegex(self.jobs["tag"], r"ref:\s*\$\{\{\s*github\.event\.workflow_run\.head_sha\s*\}\}")

    def test_no_event_text_inside_a_shell_line(self):
        """이벤트에서 온 글자(브랜치 이름 등)를 run: 안에 그대로 끼우면 셸이 그것을 실행한다. env 로 넘긴다."""
        runs = _runs(self.jobs["tag"])
        self.assertTrue(runs)
        for run in runs:
            self.assertNotIn("${{", run)
        self.assertTrue(any("ci/release_ci.py auto-tag" in run for run in runs))

    def test_token_permissions(self):
        """태그를 달고(contents) release.yml 을 깨우는(actions) 권한은 그 잡에만. 그 밖의 쓰기 권한은 없다."""
        self.assertRegex(self.top, r"permissions:\n  contents: read\n")
        self.assertNotIn("write", self.top)
        perms = re.search(r"permissions:\n((?:\s+[a-z-]+: [a-z]+\n)+)", self.jobs["tag"]).group(1)
        self.assertEqual(sorted(x.strip() for x in perms.strip().splitlines()),
                         ["actions: write", "contents: write"])

    def test_no_stored_secrets_and_no_release_tools(self):
        """이 잡은 태그와 dispatch 만 한다. 서명·빌드·게시 도구는 여기서 부르지 않는다."""
        self.assertLessEqual(set(re.findall(r"secrets\.([A-Za-z0-9_]+)", self.text)), {"GITHUB_TOKEN"})
        for word in ("release.sh", "build_win", "gh release", "codesign", "notarytool"):
            self.assertNotIn(word, _code(self.text))

    def test_tests_yml_cannot_tag(self):
        """PR 로도 도는 tests.yml 에는 쓰기 권한도 태그·릴리스 명령도 없다."""
        code = _code(TESTS_YML.read_text(encoding="utf-8"))
        for word in ("write", "git tag", "git push", "gh release", "release_ci.py"):
            self.assertNotIn(word, code)


class AutoTagDecisions(unittest.TestCase):
    """ci/release_ci.py 의 auto_tag_decision — ('tag' | 'skip' | 'fail', 이유들).

    tag   태그를 달고 release.yml 을 깨운다.
    skip  아무것도 하지 않는다(초록). 버전을 올리지 않은 머지가 대부분 여기다.
    fail  버전은 올렸는데 릴리스할 수 없는 모양이다(빨강) — 태그는 달지 않는다.
    """
    SHA = "c" * 40
    NOTES = "### 변경 내역\n\n**v1.2.3**\n- a\n\n**v1.2.2**\n- b\n"

    @classmethod
    def setUpClass(cls):
        cls.rc = _load_release_ci()

    def _run(self, **kw):
        run = {"id": 7, "event": "push", "head_branch": "main", "head_sha": self.SHA,
               "status": "completed", "conclusion": "success"}
        run.update(kw)
        return run

    def _jobs(self, **override):
        jobs = {"macOS — full suite": "success", "Windows — gating contract": "success",
                "macOS — built .app (unsigned)": "success", "Windows — built exe (unsigned)": "success",
                "Real Mac — installed CLIs, real sign-in": "success",
                "Real Windows — installed CLIs, real sign-in": "success"}
        jobs.update(override)
        return [{"name": k, "status": "completed", "conclusion": v} for k, v in jobs.items() if v is not None]

    def _decide(self, **kw):
        args = {"app_version": "1.2.3", "latest": "1.2.2", "tag_exists": False, "run": self._run(),
                "jobs": self._jobs(), "notes_text": self.NOTES}
        args.update(kw)
        return self.rc.auto_tag_decision(**args)

    def test_bumped_and_green_is_tagged(self):
        self.assertEqual(self._decide()[0], "tag")
        self.assertEqual(self._decide(app_version="1.3.0", notes_text="**v1.3.0**\n- a\n")[0], "tag")
        self.assertEqual(self._decide(app_version="2.0.0", notes_text="**v2.0.0**\n- a\n")[0], "tag")

    def test_first_release_ever(self):
        self.assertEqual(self._decide(latest=None)[0], "tag")

    def test_unbumped_merge_does_nothing(self):
        """버전을 올리지 않은 머지 — 가장 흔한 경우. 빨갛지도 않다."""
        action, why = self._decide(app_version="1.2.2")
        self.assertEqual(action, "skip")
        self.assertTrue(why)

    def test_lower_version_does_nothing(self):
        for lower in ("1.2.1", "1.1.9", "0.9.9"):
            self.assertEqual(self._decide(app_version=lower, notes_text=f"**v{lower}**\n")[0], "skip", lower)

    def test_versions_compare_as_numbers(self):
        """글자로 비교하면 1.10.0 < 1.9.0 이 된다."""
        self.assertEqual(self._decide(app_version="1.10.0", latest="1.9.0", notes_text="**v1.10.0**\n")[0], "tag")
        self.assertEqual(self._decide(app_version="1.9.0", latest="1.10.0", notes_text="**v1.9.0**\n")[0], "skip")
        self.assertEqual(self._decide(app_version="1.2.10", latest="1.2.9", notes_text="**v1.2.10**\n")[0], "tag")

    def test_existing_tag_does_nothing(self):
        """이미 있는 태그는 옮기지도, 다시 게시하지도 않는다 — 버전이 최신 릴리스보다 크더라도."""
        self.assertEqual(self._decide(tag_exists=True)[0], "skip")

    def test_red_or_missing_main_ci_does_nothing(self):
        """워크플로의 if: 가 이미 거르지만, 판정은 그것에 기대지 않고 서버에 다시 물은 값으로 본다."""
        for run, jobs in ((None, []),
                          (self._run(conclusion="failure"), self._jobs()),
                          (self._run(conclusion="cancelled"), self._jobs()),
                          (self._run(status="in_progress", conclusion=None), self._jobs()),
                          (self._run(), self._jobs(**{"macOS — full suite": "failure"})),
                          (self._run(), self._jobs(**{"Windows — built exe (unsigned)": "skipped"})),
                          (self._run(), self._jobs(**{"Real Mac — installed CLIs, real sign-in": None})),
                          (self._run(), self._jobs(**{"Real Windows — installed CLIs, real sign-in": "skipped"}))):
            action, why = self._decide(run=run, jobs=jobs)
            self.assertEqual(action, "skip", (run, jobs))
            self.assertTrue(why)

    def test_red_ci_wins_over_everything(self):
        """CI 가 빨간데 버전 모양이 틀렸다고 'fail' 로 가지도, 'tag' 로 가지도 않는다."""
        self.assertEqual(self._decide(run=self._run(conclusion="failure"), app_version="banana")[0], "skip")

    def test_bumped_but_unreleasable_fails_without_tagging(self):
        """버전을 올렸는데 노트에 그 절이 없거나 버전 모양이 틀렸다 — 태그를 달면 release.yml 의 gate 에서
        죽고 태그만 남는다. 달기 전에 빨갛게 끝낸다."""
        self.assertEqual(self._decide(notes_text="**v1.2.2**\n- b\n")[0], "fail")
        for bad in ("1.3", "1.2.3.1", "v1.2.3", "1.2.3-rc1", "", None):
            self.assertEqual(self._decide(app_version=bad)[0], "fail", bad)

    def test_latest_release_version(self):
        """최신 릴리스 = 공개된 vX.Y.Z 릴리스 가운데 가장 큰 버전. 초안·프리릴리스·다른 모양의 태그는 세지
        않는다 — 시험이 남긴 초안 하나가 '최신'이 되면 다음 릴리스가 영원히 막힌다."""
        f = self.rc.latest_release_version
        rel = lambda tag, **kw: dict({"tag_name": tag, "draft": False, "prerelease": False}, **kw)
        self.assertEqual(f([rel("v1.2.2"), rel("v1.2.1"), rel("v1.2.0")]), "1.2.2")
        self.assertEqual(f([rel("v1.9.0"), rel("v1.10.0")]), "1.10.0")
        self.assertEqual(f([rel("v1.2.2"), rel("v9.0.0", draft=True), rel("v8.0.0", prerelease=True),
                            rel("dry-run-123", draft=True), rel("v7"), rel("nightly"), rel(None)]), "1.2.2")
        self.assertIsNone(f([]))
        self.assertIsNone(f([rel("v2.0.0", draft=True)]))


class AutoTagActs(unittest.TestCase):
    """tag_and_dispatch(repo, tag, sha, api) — api(method, path, fields) → (ok, text). 서버는 부르지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.rc = _load_release_ci()

    def _api(self, fail_on=()):
        calls = []

        def api(method, path, fields=None):
            calls.append((method, path, dict(fields or {})))
            return (not any(word in path and method == m for m, word in fail_on), "")
        return api, calls

    def test_creates_the_tag_on_that_commit_then_starts_the_release(self):
        api, calls = self._api()
        self.assertEqual(self.rc.tag_and_dispatch("o/r", "v1.2.3", "c" * 40, api), [])
        self.assertEqual(calls, [
            ("POST", "repos/o/r/git/refs", {"ref": "refs/tags/v1.2.3", "sha": "c" * 40}),
            ("POST", "repos/o/r/actions/workflows/release.yml/dispatches", {"ref": "v1.2.3"}),
        ])

    def test_no_dispatch_when_the_tag_could_not_be_made(self):
        api, calls = self._api(fail_on=[("POST", "git/refs")])
        self.assertTrue(self.rc.tag_and_dispatch("o/r", "v1.2.3", "c" * 40, api))
        self.assertEqual(len(calls), 1)

    def test_tag_is_removed_when_the_release_could_not_be_started(self):
        """태그만 남으면 다음 실행이 '이미 있는 태그'로 건너뛰어 그 버전이 영원히 나가지 않는다."""
        api, calls = self._api(fail_on=[("POST", "dispatches")])
        self.assertTrue(self.rc.tag_and_dispatch("o/r", "v1.2.3", "c" * 40, api))
        self.assertEqual(calls[-1], ("DELETE", "repos/o/r/git/refs/tags/v1.2.3", {}))


if __name__ == "__main__":
    unittest.main()
