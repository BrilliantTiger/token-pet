#!/usr/bin/env python3
"""릴리스 워크플로(.github/workflows/release.yml)의 판정과 게시 — stdlib 만 쓴다.

    python3 ci/release_ci.py gate    --event push --ref refs/tags/v1.2.2 --sha <sha> --repo <owner/name> --run-id <id>
    python3 ci/release_ci.py sums    <file>...
    python3 ci/release_ci.py publish --mode publish|dry-run --repo <owner/name> --sha <sha> --name <tag>
                                     --title <title> --notes <file> --dir <folder> --expect <json> [--expect <json>]

gate     게시해도 되는가. 게시(publish)는 **push 된 vX.Y.Z 태그** 하나뿐이고 나머지는 전부 시험(dry-run)이다.
         게시라면: 태그 == "v" + APP_VERSION, RELEASE_NOTES.md 에 그 버전 절이 있음, 태그 커밋이 origin/main 에
         있음, 그 커밋의 tests.yml **main push 실행**이 실기기 잡 둘을 포함해 전부 success. 하나라도 아니면 실패.
sums     만든 파일의 크기·SHA-256 을 잡 출력(sums)으로 낸다. 파일과 다른 길로 게시 잡에 간다.
publish  초안(draft) 릴리스를 만들어 여섯 파일을 올리고, GitHub 이 받은 것의 크기·SHA-256 이 만든 것과 같은지
         본 뒤에야 공개한다. 시험이면 공개하지 않고 초안을 지운다. 어디서 실패하든 초안은 남기지 않는다.

토큰·경로·자격 증명은 찍지 않는다. 서버는 `gh` 로만 부른다(GH_TOKEN 은 워크플로가 준다).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ASSETS = ("ClaudePet.zip", "ClaudePet-universal.zip", "ClaudePet.dmg", "ClaudePet-universal.dmg",
          "claude-pet-win.zip", "claude-pet-win-setup.exe")
# tests.yml 의 실기기 잡 이름(앞부분). 이 둘이 success 로 '있어야' 한다 — 없거나 건너뛴 것은 통과가 아니다.
REAL_JOB_PREFIXES = ("Real Mac", "Real Windows")
TESTS_WORKFLOW = "tests.yml"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ───────────────────────────── 판정 (순수) ─────────────────────────────
def release_mode(event, ref):
    """'publish' 는 push 된 refs/tags/vX.Y.Z 뿐. 그 밖의 모든 것은 'dry-run'."""
    if event == "push" and re.fullmatch(r"refs/tags/v[0-9]+\.[0-9]+\.[0-9]+", str(ref or "")):
        return "publish"
    return "dry-run"


def version_problems(tag, app_version):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(app_version or "")):
        return [f"APP_VERSION 이 major.minor.fix 가 아니다: {app_version!r}"]
    if tag != "v" + app_version:
        return [f"태그 {tag!r} 와 앱 버전 {app_version!r} 이 다르다 (태그는 'v{app_version}' 이어야 한다)"]
    return []


def notes_problems(notes_text, app_version):
    heading = f"**v{app_version}**"
    if any(line.strip() == heading for line in str(notes_text).splitlines()):
        return []
    return [f"RELEASE_NOTES.md 에 {heading} 절이 없다"]


def pick_main_run(runs, sha):
    """그 커밋의 main push 실행 중 가장 최근 것(없으면 None). PR·수동·다른 브랜치의 실행은 세지 않는다."""
    mine = [r for r in runs or () if r.get("event") == "push" and r.get("head_branch") == "main"
            and r.get("head_sha") == sha]
    return max(mine, key=lambda r: r.get("id") or 0) if mine else None


def ci_problems(run, jobs):
    if not run:
        return ["이 커밋의 tests.yml main push 실행이 없다 — 태그는 main 의 CI 가 초록이 된 커밋에 붙인다"]
    out = []
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        out.append(f"tests.yml main 실행 {run.get('id')} 이 success 가 아니다: "
                   f"{run.get('status')}/{run.get('conclusion')}")
    for job in jobs or ():
        if job.get("conclusion") != "success":
            out.append(f"잡이 success 가 아니다: {job.get('name')} ({job.get('status')}/{job.get('conclusion')})")
    for prefix in REAL_JOB_PREFIXES:
        if not any(str(j.get("name", "")).startswith(prefix) and j.get("conclusion") == "success"
                   for j in jobs or ()):
            out.append(f"실기기 잡이 success 로 돌지 않았다: {prefix}")
    return out


def asset_problems(expected, actual):
    """만든 것(expected)과 올라간 것(actual)이 같은 여섯 파일인가 → 문제 목록."""
    names = sorted(a.get("name") for a in expected)
    if names != sorted(ASSETS):
        return [f"만든 파일이 정해진 여섯이 아니다: {names}"]
    out = []
    want = {a["name"]: a for a in expected}
    got = {}
    for a in actual:
        if a.get("name") in got:
            out.append(f"올라간 자산이 겹친다: {a.get('name')}")
        got[a.get("name")] = a
    for name in sorted(set(want) - set(got)):
        out.append(f"올라가지 않았다: {name}")
    for name in sorted(set(got) - set(want), key=str):
        out.append(f"정해지지 않은 자산이 올라갔다: {name}")
    for name in sorted(set(want) & set(got)):
        w, g = want[name], got[name]
        if w.get("size") != g.get("size"):
            out.append(f"크기가 다르다: {name} (만든 것 {w.get('size')}, 올라간 것 {g.get('size')})")
        if not g.get("sha256") or str(w.get("sha256")).lower() != str(g.get("sha256")).lower():
            out.append(f"SHA-256 이 다르다(또는 없다): {name}")
    return out


# ───────────────────────────── 도구 ─────────────────────────────
def app_version():
    with open(os.path.join(ROOT, "claude_pet.py"), encoding="utf-8") as f:
        m = re.search(r'^APP_VERSION = "([^"]+)"', f.read(), re.M)
    return m.group(1) if m else ""


def file_sum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"name": os.path.basename(path), "size": os.path.getsize(path), "sha256": h.hexdigest()}


def gh_json(*args):
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"❌ gh api 실패 (rc={r.returncode}): {r.stderr.strip()[:300]}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def set_outputs(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    for k, v in kv.items():
        print(f"  {k} = {v if len(str(v)) < 200 else str(v)[:200] + '…'}")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def fail(problems):
    for p in problems:
        print("❌ " + p)
    raise SystemExit(1)


# ───────────────────────────── gate ─────────────────────────────
def cmd_gate(a):
    mode = release_mode(a.event, a.ref)
    version = app_version()
    with open(os.path.join(ROOT, "RELEASE_NOTES.md"), encoding="utf-8") as f:
        problems = notes_problems(f.read(), version)
    if mode == "publish":
        tag = a.ref[len("refs/tags/"):]
        problems += version_problems(tag, version)
        on_main = subprocess.run(["git", "merge-base", "--is-ancestor", a.sha, "origin/main"], cwd=ROOT)
        if on_main.returncode != 0:
            problems.append("태그 커밋이 origin/main 에 없다")
        runs = gh_json(f"repos/{a.repo}/actions/workflows/{TESTS_WORKFLOW}/runs"
                       f"?head_sha={a.sha}&event=push&branch=main&per_page=100")
        run = pick_main_run((runs or {}).get("workflow_runs"), a.sha)
        jobs = []
        if run:
            jobs = (gh_json(f"repos/{a.repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100")
                    or {}).get("jobs") or []
            print(f"tests.yml main 실행 {run['id']}: {run.get('status')}/{run.get('conclusion')}")
            for j in jobs:
                print(f"  {j.get('conclusion')}: {j.get('name')}")
        problems += ci_problems(run, jobs)
        name, title = tag, f"Token Pet {tag}"
    else:
        print("시험(dry-run): 빌드·서명·공증·초안 업로드까지 하고 초안을 지운다. 게시하지 않는다.")
        print("  (main·CI 조건은 게시할 때만 본다 — 시험은 브랜치의 커밋으로도 돈다)")
        name = f"dry-run-{a.run_id}"
        title = f"DRY RUN {a.run_id} — Token Pet v{version} (게시하지 않음)"
    if problems:
        fail(problems)
    print(f"✅ gate 통과 ({mode})")
    set_outputs(mode=mode, version=version, name=name, title=title)


# ───────────────────────────── sums ─────────────────────────────
def cmd_sums(a):
    problems = [f"만든 파일이 없거나 비었다: {os.path.basename(p)}" for p in a.files
                if not os.path.isfile(p) or os.path.getsize(p) == 0]
    if problems:
        fail(problems)
    set_outputs(sums=json.dumps([file_sum(p) for p in a.files], separators=(",", ":")))


# ───────────────────────────── publish ─────────────────────────────
def _releases(repo):
    return gh_json(f"repos/{repo}/releases?per_page=100") or []


def _remote_assets(release):
    out = []
    for x in release.get("assets") or ():
        digest = str(x.get("digest") or "")
        out.append({"name": x.get("name"), "size": x.get("size") if x.get("state") == "uploaded" else None,
                    "sha256": digest[len("sha256:"):] if digest.startswith("sha256:") else ""})
    return out


def cmd_publish(a):
    expected = [x for e in a.expect for x in json.loads(e)]
    problems = asset_problems(expected, expected)           # 여섯 개인가
    local = []
    for name in ASSETS:
        path = os.path.join(a.dir, name)
        if os.path.isfile(path):
            local.append(file_sum(path))
    problems = problems or asset_problems(expected, local)  # 러너에서 만든 것과 여기 받은 것이 같은가
    if not os.path.isfile(a.notes) or os.path.getsize(a.notes) == 0:
        problems.append("릴리스 본문이 없다")
    if problems:
        fail(problems)
    for x in local:
        print(f"  {x['name']}  {x['size']}  sha256:{x['sha256']}")

    for old in [r for r in _releases(a.repo) if r.get("tag_name") == a.name]:
        if not old.get("draft"):
            fail([f"{a.name} 릴리스가 이미 공개돼 있다 — 공개된 릴리스는 덮어쓰지 않는다"])
        print(f"남은 초안을 지운다: {old.get('id')}")
        gh_json("-X", "DELETE", f"repos/{a.repo}/releases/{old['id']}")

    create = ["gh", "release", "create", a.name, "--repo", a.repo, "--draft", "--title", a.title,
              "--notes-file", a.notes, "--target", a.sha]
    if a.mode == "publish":
        create.append("--verify-tag")
    create += [os.path.join(a.dir, name) for name in ASSETS]
    published = False
    rid = None
    try:
        subprocess.run(create, check=True)
        drafts = [r for r in _releases(a.repo) if r.get("tag_name") == a.name and r.get("draft")]
        if len(drafts) != 1:
            fail([f"방금 만든 초안을 찾지 못했다 ({len(drafts)}개)"])
        rid = drafts[0]["id"]
        problems = asset_problems(expected, _remote_assets(drafts[0]))
        if problems:
            fail(problems)
        print("✅ 올라간 여섯 자산의 크기·SHA-256 이 만든 것과 같다")
        if a.mode != "publish":
            print("시험이므로 공개하지 않는다.")
            return
        gh_json("-X", "PATCH", f"repos/{a.repo}/releases/{rid}", "-F", "draft=false", "-f", "make_latest=true")
        published = True
        live = gh_json(f"repos/{a.repo}/releases/tags/{a.name}")
        problems = asset_problems(expected, _remote_assets(live))
        if live.get("draft") or live.get("id") != rid:
            problems.append("공개한 릴리스가 태그로 보이지 않는다")
        if problems:
            fail(problems)
        print(f"🚀 게시: {live.get('html_url')}")
    finally:
        if not published:
            for r in _releases(a.repo):
                if r.get("draft") and (r.get("id") == rid or r.get("tag_name") == a.name):
                    gh_json("-X", "DELETE", f"repos/{a.repo}/releases/{r['id']}")
                    print(f"초안을 지웠다: {r['id']}")
            left = [r for r in _releases(a.repo) if r.get("tag_name") == a.name]
            if left:
                print("❌ 초안이 남아 있다")
                raise SystemExit(1)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):                 # cp949 콘솔(Windows 러너)에서 죽지 않게
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    for name in ("event", "ref", "sha", "repo", "run-id"):
        g.add_argument("--" + name, required=True)
    g.set_defaults(fn=cmd_gate)
    s = sub.add_parser("sums")
    s.add_argument("files", nargs="+")
    s.set_defaults(fn=cmd_sums)
    u = sub.add_parser("publish")
    u.add_argument("--mode", required=True, choices=("publish", "dry-run"))
    for name in ("repo", "sha", "name", "title", "notes", "dir"):
        u.add_argument("--" + name, required=True)
    u.add_argument("--expect", action="append", required=True)
    u.set_defaults(fn=cmd_publish)
    a = p.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
