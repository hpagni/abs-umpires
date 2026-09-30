#!/usr/bin/env python3
"""ops/ci_check.py -- SOP step W9.10, CI: the two workflows, checked on this machine.

W9.10 implements SOP W1.16: `ci.yml` with six parallel jobs on ubuntu-latest, on push
and pull request, under 8 minutes, and `seal-guard.yml`. The gh token here lacks the
`workflow` scope, so both files are parked in ops/ci-pending/ until the owner moves
them (ops/ci-pending/README.md). This script reads them from .github/workflows/ once
they are there and from ops/ci-pending/ until then, and checks everything that can be
checked without a runner:

  C1  both files parse as YAML
  C2  both trigger on push and pull_request, and neither on a schedule
  C3  ci.yml has exactly the six jobs, each on ubuntu-latest with steps, no `needs`
      (so all six run in parallel) and timeout-minutes at most 8; seal-guard likewise
  C4  every `uses:` is one of the pinned actions and nothing else
  C5  each job runs the SOP table's commands; no job compiles Stan; the python and
      guard jobs carry the prerequisites the W9.10 rehearsal showed a fresh runner
      needs (xdist PYTHONPATH, R for the seam tests, the git hooks, -n 4 under the
      red team); ops/ci_rehearse.py runs the jobs themselves on a clean clone
  C6  zero MLB calls: arm first and audit last in every job, the enforcement script's
      selftest, no MLB-family host named in a workflow, every MLB-family host named in
      a tracked file on the sinkhole list
  C7  no nightly.yml, no keepalive, and docs/runbook.md carries the SOP's text
  C8  seal-guard runs W9.7 layers 3 and 4, and its provenance step, byte for byte, passes
      on a clean clone of HEAD and fails on each of six planted violations
  C9  R-31: the README does not present a green badge as reproduction
  C10 actionlint, when it is installed; nothing is installed to run it

SOP clause 3, "CI is green on every push in under 8 minutes", is a measurement on a
GitHub runner. This script cannot make it and never reports it as passed: it prints
PENDING-OWNER with the reason. `gh run list --repo hpagni/abs-umpires` is where the
measured wall clock appears once the owner has moved the files.

Usage: uv run --locked python ops/ci_check.py
Exit 0 when no check fails, 1 otherwise. C10 prints SKIP, counted as neither, when
actionlint is absent. No network call; the clone in C8 is local.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
NO_MLB = ROOT / "ops" / "ci_no_mlb.sh"
JOBS = ("lint", "python", "r", "dbt", "guard", "secrets")
PINS = {
    "actions/checkout@v7.0.1",
    "actions/setup-python@v7.0.0",
    "astral-sh/setup-uv@v10.2.0",
    "actions/upload-artifact@v7.0.1",
    "actions/cache@v6.1.0",
    "r-lib/actions/setup-r@v2",
}
FAMILY = re.compile(
    r"(?<![a-z0-9-])((?:[a-z0-9-]+\.)*"
    r"(?:mlb\.com|milb\.com|mlbstatic\.com|mlbinfra\.com|mlbam\.com|mlbam\.net|mlb\.tv))"
    r"(?![a-z0-9-])",
    re.IGNORECASE,
)
RUNBOOK_TEXT = (
    "In a public repository, scheduled workflows are automatically disabled when no "
    "repository activity has occurred in 60 days",
    "gh workflow enable <name> --repo hpagni/abs-umpires",
    "default branch only",
    "UTC",
    "delayed at the start of every hour",
    "keepalive commit",
)
STAN_TOKENS = (
    "install_cmdstan",
    "cmdstan_model",
    "rebuild_cmdstan",
    "R/00_setup.R",
    "r-smoke",
    "brms::brm",
    "brm(",
    "cmdstanr::cmdstan_make",
)

# ok is True (PASS), False (FAIL) or None (SKIP: not run, counted as neither)
results: list[tuple[str, str, bool | None, str]] = []


def record(cid: str, label: str, ok: bool | None, detail: str) -> None:
    results.append((cid, label, ok, detail))
    status = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
    print(f"{cid:<4} {label:<16} {status}  {detail}")


def run(cmd: list[str], cwd: pathlib.Path = ROOT, stdin: str | None = None):
    return subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, check=False)


def locate() -> tuple[str, dict[str, pathlib.Path]]:
    live = ROOT / ".github" / "workflows"
    if (live / "ci.yml").is_file() or (live / "seal-guard.yml").is_file():
        return "live", {"ci": live / "ci.yml", "seal-guard": live / "seal-guard.yml"}
    parked = ROOT / "ops" / "ci-pending"
    return "parked", {"ci": parked / "ci.yml", "seal-guard": parked / "seal-guard.yml"}


def triggers(doc: dict) -> dict:
    on = doc.get("on", doc.get(True))  # PyYAML reads a bare `on:` key as True
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return dict.fromkeys(on)
    return on or {}


def job_text(job: dict) -> str:
    return "\n".join(str(s.get("run", "")) for s in job.get("steps", []))


def uses_of(job: dict) -> list[str]:
    return [str(s["uses"]) for s in job.get("steps", []) if "uses" in s]


def check_shape(docs: dict[str, dict]) -> None:
    bad = [
        n
        for n, d in docs.items()
        if not ({"push", "pull_request"} <= set(triggers(d))) or "schedule" in triggers(d)
    ]
    record(
        "C2",
        "triggers",
        not bad,
        "push and pull_request, no schedule" if not bad else f"wrong triggers in {bad}",
    )

    problems = []
    names = tuple(docs["ci"].get("jobs", {}))
    if set(names) != set(JOBS) or len(names) != len(JOBS):
        problems.append(f"ci.yml jobs are {names}, the SOP names {JOBS}")
    for wf, doc in docs.items():
        for name, job in doc.get("jobs", {}).items():
            if job.get("runs-on") != "ubuntu-latest":
                problems.append(f"{wf}/{name} runs-on {job.get('runs-on')!r}")
            if not job.get("steps"):
                problems.append(f"{wf}/{name} has no steps")
            if "needs" in job:
                problems.append(f"{wf}/{name} needs {job['needs']}, so it is not parallel")
            t = job.get("timeout-minutes")
            if not isinstance(t, int) or t > 8:
                problems.append(f"{wf}/{name} timeout-minutes {t!r}, the budget is 8")
    record(
        "C3",
        "six jobs",
        not problems,
        "ci.yml: lint python r dbt guard secrets, parallel, ubuntu-latest, 8 min cap each; "
        "seal-guard: 1 job, same"
        if not problems
        else "; ".join(problems),
    )

    seen, off = set(), []
    for wf, doc in docs.items():
        for name, job in doc.get("jobs", {}).items():
            for u in uses_of(job):
                seen.add(u)
                if u not in PINS:
                    off.append(f"{wf}/{name}: {u}")
    record(
        "C4",
        "pinned actions",
        not off,
        f"{len(seen)} distinct, all on the pin list: {', '.join(sorted(seen))}"
        if not off
        else f"not on the pin list: {off}",
    )


def check_commands(ci: dict) -> None:
    jobs = ci.get("jobs", {})
    want = {
        "lint": [
            "ruff check .",
            "ruff format --check .",
            "ops/lint_http.sh",
            "ops/hook_no_raw_data.sh --tracked",
            "make lint-prose",
            "git diff --name-only",
            "'*.md'",
        ],
        "python": [
            "uv sync --locked",
            "uv run --locked pytest tests/unit tests/fixtures tests/guard -q -n 4",
        ],
        "r": ["renv::restore(", 'testthat::test_dir("tests/testthat")'],
        "dbt": [
            "synth_feed.py",
            "COPY (SELECT * FROM read_csv_auto",
            "dbt deps && dbt parse && dbt build --target ci",
        ],
        "guard": ["make test-guard", "make prove-guard-redteam"],
        "secrets": ["gitleaks detect --redact --no-banner"],
    }
    uses_want = {
        "python": ["astral-sh/setup-uv@v10.2.0"],
        "r": ["r-lib/actions/setup-r@v2", "actions/cache@v6.1.0"],
    }
    problems = []
    for name, needles in want.items():
        text = job_text(jobs.get(name, {}))
        problems += [f"{name}: missing {n!r}" for n in needles if n not in text]
        problems += [
            f"{name}: does not use {u}"
            for u in uses_want.get(name, [])
            if u not in uses_of(jobs.get(name, {}))
        ]
    r_job = jobs.get("r", {})
    setup_r = [s for s in r_job.get("steps", []) if str(s.get("uses", "")).startswith("r-lib/")]
    if not setup_r or str(setup_r[0].get("with", {}).get("r-version")) != "4.5.2":
        problems.append("r: setup-r is not pinned to R 4.5.2")
    # No Stan compile anywhere in CI: the python job restores R too, so every job
    # is scanned, not only r.
    for name in JOBS:
        dumped = yaml.safe_dump(jobs.get(name, {}))
        problems += [f"{name}: Stan token {t!r} present" for t in STAN_TOKENS if t in dumped]
    # The prerequisites the W9.10 rehearsal showed the SOP's own lines need on a
    # fresh runner (see the comments above the python and guard jobs in ci.yml).
    py_job = jobs.get("python", {})
    py_text = job_text(py_job)
    if "tests/guard" not in str(py_job.get("env", {}).get("PYTHONPATH", "")):
        problems.append("python: PYTHONPATH lacks tests/guard, xdist dies on VacuousGuard")
    if "r-lib/actions/setup-r@v2" not in uses_of(py_job) or "renv::restore(" not in py_text:
        problems.append("python: no R and renv library for the seam tests in tests/unit")
    if "pre-commit install" not in py_text or "ops/install_git_hooks.sh" not in py_text:
        problems.append("python: git hooks not installed for tests/unit/test_layout.py")
    g_env = jobs.get("guard", {}).get("env", {})
    if "-n 4" not in str(g_env.get("PYTEST_ADDOPTS", "")):
        problems.append("guard: no PYTEST_ADDOPTS -n 4, the serial red team is past 8 minutes")
    if "tests/guard" not in str(g_env.get("PYTHONPATH", "")):
        problems.append("guard: PYTHONPATH lacks tests/guard, xdist dies on VacuousGuard")
    for name in ("guard", "secrets", "python"):
        co = jobs.get(name, {}).get("steps", [{}])[0]
        if co.get("with", {}).get("fetch-depth") != 0:
            problems.append(f"{name}: checkout is not full history (fetch-depth: 0)")
    dbt_text = job_text(jobs.get("dbt", {}))
    for t in ("--target dev", "--target prod", "--target sealed", "warehouse/"):
        if t in dbt_text:
            problems.append(f"dbt: {t!r} in the ci job")
    record(
        "C5",
        "SOP commands",
        not problems,
        "every command in the W1.16 table, no Stan compile in any job, dbt on target ci only, "
        "python and guard prerequisites present"
        if not problems
        else "; ".join(problems),
    )


def check_no_mlb(docs: dict[str, dict], paths: dict[str, pathlib.Path]) -> None:
    problems = []
    for wf, doc in docs.items():
        for name, job in doc.get("jobs", {}).items():
            steps = job.get("steps", [])
            runs = [i for i, s in enumerate(steps) if "run" in s]
            arm = [i for i in runs if "ops/ci_no_mlb.sh arm" in str(steps[i]["run"])]
            audit = [i for i in runs if "ops/ci_no_mlb.sh audit" in str(steps[i]["run"])]
            if (
                not arm
                or arm[0] != 1
                or not str(steps[0].get("uses", "")).startswith("actions/checkout@")
            ):
                problems.append(f"{wf}/{name}: arm is not the first step after checkout")
            if not audit or audit[-1] != runs[-1]:
                problems.append(f"{wf}/{name}: audit is not the last run step")
            elif str(steps[audit[-1]].get("if", "")) != "always()":
                problems.append(f"{wf}/{name}: audit does not run under if: always()")
        for m in FAMILY.finditer(paths[wf].read_text(encoding="utf-8")):
            problems.append(f"{wf}: names the MLB-family host {m.group(1)}")
    st = run(["bash", str(NO_MLB), "selftest"])
    st_last = (st.stdout.strip().splitlines() or ["no output"])[-1]
    if st.returncode != 0:
        problems.append("ci_no_mlb.sh selftest failed: " + st_last)
    hosts = set(run(["bash", str(NO_MLB), "hosts"]).stdout.split())
    named: dict[str, str] = {}
    listed = run(
        [
            "git",
            "grep",
            "-I",
            "-l",
            "-i",
            "-E",
            r"mlb\.com|milb\.com|mlbstatic|mlbinfra|mlbam|mlb\.tv",
        ]
    ).stdout.split()
    for f in listed:
        if f == "ops/ci_no_mlb.sh":
            continue  # its selftest plants family names that no code reaches
        try:
            text = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in FAMILY.finditer(text):
            named.setdefault(m.group(1).lower().rstrip("."), f)
    missing = {h: f for h, f in named.items() if h not in hosts}
    problems += [f"{h} (named in {f}) is not on the sinkhole list" for h, f in missing.items()]
    record(
        "C6",
        "zero MLB calls",
        not problems,
        f"arm first and audit last in all 7 jobs; {st_last}"
        f"; {len(named)} MLB-family host(s) named in tracked files, all {len(hosts)} on "
        f"the sinkhole list"
        if not problems
        else "; ".join(problems),
    )


def check_nightly() -> None:
    problems = []
    for d in (ROOT / ".github" / "workflows", ROOT / "ops" / "ci-pending"):
        problems += [f"{p.relative_to(ROOT)} exists" for p in d.glob("nightly.y*ml")]
    runbook = ROOT / "docs" / "runbook.md"
    # whitespace-normalised: the runbook wraps the quoted sentence across lines
    text = " ".join(runbook.read_text(encoding="utf-8").split()) if runbook.is_file() else ""
    problems += [f"docs/runbook.md lacks {t!r}" for t in RUNBOOK_TEXT if t not in text]
    if "no `nightly.yml`" not in text:
        problems.append("docs/runbook.md does not say there is no nightly.yml")
    plist = ROOT / "ops" / "com.absump.nightly.plist"
    ptext = plist.read_text(encoding="utf-8") if plist.is_file() else ""
    if not (
        re.search(r"<key>Hour</key>\s*<integer>3</integer>", ptext)
        and re.search(r"<key>Minute</key>\s*<integer>30</integer>", ptext)
    ):
        problems.append("the local launchd nightly plist is not at 03:30")
    record(
        "C7",
        "no nightly.yml",
        not problems,
        "no nightly.yml; nightly is local launchd (ops/com.absump.nightly.plist); runbook "
        "carries the 60-day rule, UTC, default branch, hourly delay, re-enable, no keepalive"
        if not problems
        else "; ".join(problems),
    )


def prov_script(sg: dict) -> str:
    step = next(
        s
        for s in sg["jobs"]["seal-guard"]["steps"]
        if s.get("name") == "pre-registration tag and sealed provenance"
    )
    body = str(step["run"])
    start = body.index("<<'PY'\n") + len("<<'PY'\n")
    return body[start : body.rindex("\nPY")]


def check_seal_guard(sg: dict) -> None:
    problems = []
    text = job_text(sg["jobs"]["seal-guard"])
    for n in (
        "pytest tests/guard/test_no_sealed_reads.py",
        "pytest tests/guard/test_seal_receipts.py",
    ):
        if n not in text:
            problems.append(f"missing {n!r}")
    script = prov_script(sg)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ci_check_seal."))
    clone = tmp / "clone"
    try:
        head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        run(["git", "clone", "-q", "--shared", "--no-checkout", str(ROOT), str(clone)])
        run(["git", "checkout", "-q", "--detach", head], cwd=clone)
        py = [sys.executable, "-"]

        def attempt() -> tuple[int, str]:
            r = run(py, cwd=clone, stdin=script)
            return r.returncode, ((r.stdout + r.stderr).strip().splitlines() or [""])[-1]

        def reset() -> None:
            run(["git", "checkout", "-q", "--", "."], cwd=clone)
            run(["git", "clean", "-fdxq"], cwd=clone)

        rc, last = attempt()
        if rc != 0:
            problems.append(f"clean clone of {head[:12]} fails: {last}")
        clean_line = last
        tag_date = run(["git", "log", "-1", "--format=%cI", "prereg-v1^{commit}"]).stdout.strip()
        before = (datetime.fromisoformat(tag_date) - timedelta(days=1)).isoformat()
        after = (datetime.fromisoformat(tag_date) + timedelta(days=1)).isoformat()
        tag_sha = run(["git", "rev-list", "-n", "1", "prereg-v1"]).stdout.strip()
        sealed_ok = json.dumps(
            {
                "prereg_tag": "prereg-v1",
                "prereg_commit": tag_sha,
                "fit_started_at": after,
                "input_max_game_date": "2026-09-21",
            }
        )
        plants = [
            (
                "a fit started a day before the tag",
                "fail",
                {"out/models/plant/provenance.json": json.dumps({"fit_started_at": before})},
            ),
            (
                "a sealed output with no sibling provenance",
                "fail",
                {"out/sealed/plant/fit.parquet": "x"},
            ),
            (
                "a fit_started_at that is not a timestamp",
                "fail",
                {"out/models/plant/provenance.json": '{"fit_started_at": "yesterday"}'},
            ),
            ("PREREGISTRATION.md edited after the lock", "fail", {"PREREGISTRATION.md": None}),
            (
                "a sealed output with complete provenance after the tag",
                "pass",
                {
                    "out/sealed/plant/fit.parquet": "x",
                    "out/sealed/plant/provenance.json": sealed_ok,
                },
            ),
            ("the tag deleted", "fail", {}),
        ]
        verdicts = []
        for label, expect, files in plants:
            reset()
            for rel, body in files.items():
                p = clone / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                if body is None:
                    p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                else:
                    p.write_text(body, encoding="utf-8")
            if label == "the tag deleted":
                run(["git", "tag", "-d", "prereg-v1"], cwd=clone)
            rc, last = attempt()
            ok = (rc != 0) if expect == "fail" else (rc == 0)
            verdicts.append(ok)
            print(f"     plant: {label:<56} expect {expect}, exit {rc}: {last[:90]}")
            if not ok:
                problems.append(f"plant '{label}' expected {expect}, got exit {rc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    record(
        "C8",
        "seal-guard",
        not problems,
        f"layers 3 and 4 named; provenance step on clean HEAD: {clean_line}; "
        f"{sum(verdicts)}/{len(plants)} plants behave"
        if not problems
        else "; ".join(problems),
    )


def check_readme() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    problems = []
    if "A green badge is not a reproduction" not in text:
        problems.append("README.md lacks 'A green badge is not a reproduction'")
    if "`make prove`" not in text or "authoritative" not in text:
        problems.append("README.md does not name make prove on the Mac as the authoritative gate")
    badge = re.search(r"actions/workflows/[^)\s]*badge\.svg", text)
    if badge and "not a reproduction" not in text[badge.start() : badge.start() + 1200]:
        problems.append("a CI badge without the R-31 disclaimer beside it")
    for claim in ("reproduced by CI", "CI reproduces", "green badge proves"):
        if claim.lower() in text.lower():
            problems.append(f"README.md claims {claim!r}")
    record(
        "C9",
        "R-31 wording",
        not problems,
        "no badge presented as reproduction; make prove on the Mac named authoritative"
        if not problems
        else "; ".join(problems),
    )


def main() -> int:
    state, paths = locate()
    print(f"W9.10 ci_check: workflows {state} at {paths['ci'].parent.relative_to(ROOT)}/")
    docs: dict[str, dict] = {}
    errors = []
    for name, p in paths.items():
        try:
            docs[name] = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"{p.relative_to(ROOT)}: {exc}")
    record(
        "C1",
        "yaml",
        not errors,
        "ci.yml and seal-guard.yml parse" if not errors else "; ".join(errors),
    )
    if errors:
        return 1
    check_shape(docs)
    check_commands(docs["ci"])
    check_no_mlb(docs, paths)
    check_nightly()
    check_seal_guard(docs["seal-guard"])
    check_readme()
    if shutil.which("actionlint"):
        r = run(["actionlint", *[str(p) for p in paths.values()]])
        record(
            "C10",
            "actionlint",
            r.returncode == 0,
            "clean" if r.returncode == 0 else r.stdout.strip()[:400],
        )
    else:
        record(
            "C10",
            "actionlint",
            None,
            "not installed on this machine, so not run; nothing was installed to run it",
        )
    passed = sum(1 for r in results if r[2] is True)
    failed = sum(1 for r in results if r[2] is False)
    skipped = len(results) - passed - failed
    print(
        "CL3  clause 3        PENDING-OWNER  CI green on every push in under 8 minutes: NOT "
        "MEASURABLE UNTIL THE OWNER ENABLES THE SCOPE. The gh token lacks `workflow`, so the "
        "files are "
        + (
            "live; read `gh run list --repo hpagni/abs-umpires` for the measured wall clock"
            if state == "live"
            else "parked and no run exists"
        )
        + ". Never reported as passed by this script."
    )
    print(
        f"W9.10 ci_check: {passed} PASS, {failed} FAIL, {skipped} SKIP of {len(results)}; "
        "clause 3 PENDING-OWNER"
    )
    return 0 if failed == 0 and passed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
