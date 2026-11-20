#!/usr/bin/env python3
"""릴리스 워크플로(.github/workflows/release.yml, auto-tag.yml)의 판정과 게시 — stdlib 만 쓴다.

    python3 ci/release_ci.py auto-tag --repo <owner/name> --sha <sha>
    python3 ci/release_ci.py gate    --event push --ref refs/tags/v1.2.2 --sha <sha> --repo <owner/name> --run-id <id>
    python3 ci/release_ci.py sums    <file>...
    python3 ci/release_ci.py publish --mode publish|dry-run --repo <owner/name> --sha <sha> --name <tag>
                                     --title <title> --notes <file> --dir <folder> --expect <json> [--expect <json>]

auto-tag main 의 CI 가 끝난 커밋에 태그를 달 것인가(TOK-64). 그 커밋의 tests.yml main push 실행이 실기기 잡
         둘을 포함해 전부 success 이고, APP_VERSION 이 공개된 최신 릴리스보다 크고, 그 vX.Y.Z 태그가 아직
         없을 때만 태그를 달고 release.yml 을 그 태그에서 깨운다. 버전을 올리지 않은 머지는 아무것도 하지
         않는다. 사람이 태그를 미는 단계는 없다 — 릴리스 결정은 버전을 올린 PR 을 main 에 머지하는 것이다.
gate     게시해도 되는가. 게시(publish)는 **vX.Y.Z 태그 ref 에서 도는 실행**뿐이고 나머지는 전부 시험(dry-run)이다.
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
RELEASE_WORKFLOW = "release.yml"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ───────────────────────────── 판정 (순수) ─────────────────────────────
def release_mode(event, ref):
    """'publish' 는 refs/tags/vX.Y.Z 에서 도는 실행뿐 — auto-tag.yml 이 태그를 달고 workflow_dispatch 로 깨운
    것(GITHUB_TOKEN 으로 만든 태그는 push 이벤트를 내지 않는다)과 push 된 태그. 그 밖의 모든 것은 'dry-run'.
    어느 쪽이든 gate 의 나머지 조건(버전·노트·main·main 의 CI)을 똑같이 지난다."""
    if event in ("push", "workflow_dispatch") and re.fullmatch(r"refs/tags/v[0-9]+\.[0-9]+\.[0-9]+",
                                                               str(ref or "")):
        return "publish"
    return "dry-run"


_VERSION_RE = r"[0-9]+\.[0-9]+\.[0-9]+"


def _vtuple(version):
    return tuple(int(x) for x in version.split("."))


def latest_release_version(releases):
    """공개된 vX.Y.Z 릴리스 가운데 가장 큰 버전(없으면 None). 초안·프리릴리스·다른 모양의 태그는 세지 않는다."""
    found = []
    for r in releases or ():
        m = re.fullmatch("v(" + _VERSION_RE + ")", str(r.get("tag_name") or ""))
        if m and not r.get("draft") and not r.get("prerelease"):
            found.append(m.group(1))
    return max(found, key=_vtuple) if found else None


def auto_tag_decision(app_version, latest, tag_exists, run, jobs, notes_text):
    """main 의 CI 가 끝난 커밋에 태그를 달 것인가 → ('tag' | 'skip' | 'fail', 이유들).

    skip 은 아무것도 하지 않는 초록이다(버전을 올리지 않은 머지). fail 은 버전은 올렸는데 릴리스할 수 없는
    모양 — 태그를 달면 release.yml 의 gate 에서 죽고 태그만 남으므로, 달기 전에 빨갛게 끝낸다."""
    red = ci_problems(run, jobs)
    if red:
        return "skip", red
    version = str(app_version or "")
    if not re.fullmatch(_VERSION_RE, version):
        return "fail", [f"APP_VERSION 이 major.minor.fix 가 아니다: {app_version!r}"]
    if latest is not None and _vtuple(version) <= _vtuple(latest):
        return "skip", [f"버전이 올라가지 않았다: 앱 {version}, 최신 릴리스 {latest}"]
    if tag_exists:
        return "skip", [f"v{version} 태그가 이미 있다 — 있는 태그는 옮기지도 다시 게시하지도 않는다"]
    missing = notes_problems(notes_text, version)
    if missing:
        return "fail", missing
    return "tag", [f"앱 {version} > 최신 릴리스 {latest} — v{version} 태그를 달고 release.yml 을 깨운다"]


def tag_and_dispatch(repo, tag, sha, api):
    """그 커밋에 태그를 달고 release.yml 을 그 태그에서 깨운다 → 문제 목록. api(method, path, fields) → (ok, text).

    깨우지 못하면 방금 단 태그를 지운다: 태그만 남으면 다음 실행이 '이미 있는 태그'로 건너뛴다."""
    ok, text = api("POST", f"repos/{repo}/git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})
    if not ok:
        return [f"{tag} 태그를 달지 못했다: {text}"]
    ok, text = api("POST", f"repos/{repo}/actions/workflows/{RELEASE_WORKFLOW}/dispatches", {"ref": tag})
    if ok:
        return []
    out = [f"release.yml 을 깨우지 못했다: {text}"]
    gone, why = api("DELETE", f"repos/{repo}/git/refs/tags/{tag}", {})
    out.append(f"방금 단 {tag} 태그를 지웠다" if gone else f"방금 단 {tag} 태그를 지우지 못했다: {why}")
    return out


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


def gh_call(method, path, fields=None):
    """(ok, 짧은 오류 글) — 실패해도 끝내지 않는다. 호출한 쪽이 뒷정리를 정한다."""
    args = ["gh", "api", "-X", method, path]
    for k, v in (fields or {}).items():
        args += ["-f", f"{k}={v}"]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return r.returncode == 0, r.stderr.strip()[:300]


def main_ci(repo, sha):
    """그 커밋의 tests.yml main push 실행과 그 잡들 → (run 또는 None, jobs)."""
    runs = gh_json(f"repos/{repo}/actions/workflows/{TESTS_WORKFLOW}/runs"
                   f"?head_sha={sha}&event=push&branch=main&per_page=100")
    run = pick_main_run((runs or {}).get("workflow_runs"), sha)
    jobs = []
    if run:
        jobs = (gh_json(f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100")
                or {}).get("jobs") or []
        print(f"tests.yml main 실행 {run['id']}: {run.get('status')}/{run.get('conclusion')}")
        for j in jobs:
            print(f"  {j.get('conclusion')}: {j.get('name')}")
    return run, jobs


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


# ───────────────────────────── auto-tag ─────────────────────────────
def cmd_auto_tag(a):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if head != a.sha:
        fail(["체크아웃한 커밋이 시험한 커밋이 아니다"])
    if subprocess.run(["git", "merge-base", "--is-ancestor", a.sha, "origin/main"], cwd=ROOT).returncode != 0:
        fail(["이 커밋이 origin/main 에 없다"])
    version = app_version()
    with open(os.path.join(ROOT, "RELEASE_NOTES.md"), encoding="utf-8") as f:
        notes = f.read()
    run, jobs = main_ci(a.repo, a.sha)
    latest = latest_release_version(_releases(a.repo))
    tag = "v" + version
    refs = gh_json(f"repos/{a.repo}/git/matching-refs/tags/{tag}") or []
    exists = any(r.get("ref") == f"refs/tags/{tag}" for r in refs)
    action, why = auto_tag_decision(version, latest, exists, run, jobs, notes)
    print(f"앱 버전 {version} · 최신 릴리스 {latest} · {tag} 태그 {'있음' if exists else '없음'}")
    if action == "fail":
        fail(why)
    for line in why:
        print("  " + line)
    if action == "tag":
        problems = tag_and_dispatch(a.repo, tag, a.sha, gh_call)
        if problems:
            fail(problems)
        print(f"🏷  {tag} → release.yml 을 깨웠다")
    else:
        print("태그·릴리스 없음.")
    set_outputs(action=action, tag=tag if action == "tag" else "")


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
        run, jobs = main_ci(a.repo, a.sha)
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
    t = sub.add_parser("auto-tag")
    for name in ("repo", "sha"):
        t.add_argument("--" + name, required=True)
    t.set_defaults(fn=cmd_auto_tag)
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
