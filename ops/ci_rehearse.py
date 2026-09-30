#!/usr/bin/env python3
"""ops/ci_rehearse.py -- SOP step W9.10: rehearse ci.yml's six jobs on this Mac.

NOT THE CI MEASUREMENT. SOP clause 3, "CI is green on every push in under 8
minutes", is measured on a GitHub runner and on nothing else. The workflows are
parked (ops/ci-pending/README.md), so no run exists yet. This script is the
nearest honest thing: for each job it makes a fresh clone of HEAD, the way a runner
checks out, and executes that job's `run:` blocks from ci.yml as written, in order,
with the job's env, stopping at the first failing step as a runner does. It prints,
per job, the exit, the seconds, and on failure the step and the tail of its output.

What differs from a runner, and why:
  - `uses:` steps are emulated, not run: the clone is the checkout, and uv, R 4.5.2
    and the renv cache are this Mac's (MACHINE FACTS). The cache and upload steps
    are no-ops here.
  - `ops/ci_no_mlb.sh arm|audit` and `install gitleaks` are skipped. Both need a
    Linux runner (/etc/hosts under sudo, resolvectl, a linux_x64 tarball). The
    zero-MLB matcher is proved on this machine by `ci_check.py` C6 (its selftest);
    gitleaks 8.30.1 is already installed here.
  - RENV_PATHS_ROOT and RENV_CONFIG_REPOS_OVERRIDE are dropped: they point renv at
    /home/runner and at Ubuntu binaries, and this Mac has its own renv cache.
  - Jobs run one after another, not in parallel: two bam fits may hold 10 GB here.
    The slowest job is the proxy for the workflow's wall clock, and it is a Mac's
    number, not a runner's. A runner has 4 slower cores; read it as a floor.

No network call is made to an MLB or Savant host by this script. The suites it runs
are the offline ones (network-marked tests live in tests/data, which CI does not
run); `dbt deps` and `uv sync` reach their own package hosts, as on a runner.

Usage: uv run --locked python ops/ci_rehearse.py [--keep] [job ...]
Exit 0 when every job rehearsed is green, 1 when any is red, 2 on a usage error.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
JOBS = ("lint", "python", "r", "dbt", "guard", "secrets")
EXPR = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")
HOST_ONLY_ENV = ("RENV_PATHS_ROOT", "RENV_CONFIG_REPOS_OVERRIDE")
DEFAULT_SHELL = ["bash", "--noprofile", "--norc", "-eo", "pipefail"]


def git(*args: str, cwd: pathlib.Path = ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def workflow() -> str:
    """ci.yml's path in the tree: .github/workflows/ once moved, ops/ci-pending/ until."""
    if (ROOT / ".github" / "workflows" / "ci.yml").is_file():
        return ".github/workflows/ci.yml"
    return "ops/ci-pending/ci.yml"


def substitute(text: str, ctx: dict[str, str], env: dict[str, str]) -> str:
    def one(m: re.Match) -> str:
        key = m.group(1)
        if key.startswith("env."):
            return env.get(key[4:], "")
        if key in ctx:
            return ctx[key]
        raise KeyError(f"expression not emulated: ${{{{ {key} }}}}")

    return EXPR.sub(one, text)


def host_skip(step: dict) -> str | None:
    run = str(step.get("run", ""))
    name = str(step.get("name", ""))
    if "ops/ci_no_mlb.sh" in run:
        return "runner only: /etc/hosts sinkhole and resolver observer (C6 selftest here)"
    if name.startswith("install gitleaks"):
        return "runner only: linux_x64 tarball; gitleaks is installed on this Mac"
    return None


def rehearse(job_name: str, job: dict, wf_env: dict, head: str, work: pathlib.Path) -> dict:
    jdir = work / job_name
    repo = jdir / "repo"
    temp = jdir / "runner-temp"
    temp.mkdir(parents=True)
    log = jdir / "job.log"
    start = time.monotonic()
    budget = 60 * int(job.get("timeout-minutes", 8))
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(repo)], check=True)
    git("checkout", "-q", "--detach", head, cwd=repo)
    gh_path = temp / "github_path"
    gh_path.touch()
    ctx = {
        "runner.temp": str(temp),
        "runner.os": "Linux",
        "github.workspace": str(repo),
        "github.event_name": "push",
        "github.base_ref": "",
        "github.event.before": git("rev-parse", f"{head}~1"),
        "github.event.repository.default_branch": "main",
        "github.ref": "refs/heads/rehearsal",
        "github.workflow": "ci",
    }
    env = dict(os.environ)
    # a runner has no project venv on PATH; `uv run` put this checkout's there
    env.pop("VIRTUAL_ENV", None)
    own_venv = str(ROOT / ".venv" / "bin")
    env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if p != own_venv)
    env.update(
        {
            "CI": "true",
            "GITHUB_WORKSPACE": str(repo),
            "GITHUB_PATH": str(gh_path),
            "RUNNER_TEMP": str(temp),
            "STAN_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
        }
    )
    for k, v in {**wf_env, **job.get("env", {})}.items():
        if k in HOST_ONLY_ENV:
            continue
        env[k] = substitute(str(v), ctx, env)
    ran = emulated = 0
    out = {"job": job_name, "exit": 0, "step": "", "tail": "", "budget": budget}
    with log.open("w") as fh:
        for i, step in enumerate(job.get("steps", [])):
            label = str(step.get("name") or step.get("uses") or f"step {i}")
            if "uses" in step:
                emulated += 1
                fh.write(f"== {label}: emulated on this Mac\n")
                continue
            why = host_skip(step)
            if why:
                emulated += 1
                fh.write(f"== {label}: skipped, {why}\n")
                continue
            senv = dict(env)
            for k, v in step.get("env", {}).items():
                senv[k] = substitute(str(v), ctx, senv)
            extra = [p for p in gh_path.read_text().splitlines() if p.strip()]
            if extra:
                senv["PATH"] = os.pathsep.join([*reversed(extra), senv["PATH"]])
            body = substitute(str(step["run"]), ctx, senv)
            cwd = repo / step.get("working-directory", ".")
            shell = str(step.get("shell", "bash"))
            if shell.startswith("Rscript"):
                script = temp / f"step{i}.R"
                cmd = ["Rscript", str(script)]
            else:
                script = temp / f"step{i}.sh"
                cmd = [*DEFAULT_SHELL, str(script)]
            script.write_text(body)
            fh.write(f"== {label}\n")
            fh.flush()
            remaining = 2 * budget - (time.monotonic() - start)
            try:
                rc = subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=senv,
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    timeout=max(remaining, 1),
                    check=False,
                ).returncode
            except subprocess.TimeoutExpired:
                rc = 124
                fh.write(f"== killed at twice the {budget // 60}-minute budget\n")
            ran += 1
            fh.write(f"== {label}: exit {rc}\n")
            if rc != 0:
                out.update(exit=rc, step=label)
                break
    out["secs"] = round(time.monotonic() - start)
    out["ran"], out["emulated"] = ran, emulated
    if out["exit"]:
        lines = [ln for ln in log.read_text(errors="replace").splitlines() if ln.strip()]
        out["tail"] = "\n".join("      | " + ln[:200] for ln in lines[-8:])
    out["log"] = str(log)
    return out


def main(argv: list[str]) -> int:
    keep = "--keep" in argv
    names = [a for a in argv if a != "--keep"]
    bad = [n for n in names if n not in JOBS]
    if bad:
        print(f"unknown job(s): {' '.join(bad)}; jobs are {' '.join(JOBS)}", file=sys.stderr)
        return 2
    shown = workflow()
    head = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain", "--", shown)
    wf = yaml.safe_load(git("show", f"HEAD:{shown}"))
    print(f"W9.10 rehearsal: {shown} at HEAD {head[:12]}, each job on its own clean clone")
    print("NOT the CI measurement: a Mac, jobs run serially, uses: steps emulated")
    if dirty:
        print(f"note: {shown} has uncommitted edits; the rehearsal runs HEAD's copy")
    work = pathlib.Path(tempfile.mkdtemp(prefix="ci-rehearse."))
    results = []
    for name in names or JOBS:
        r = rehearse(name, wf["jobs"][name], wf.get("env", {}), head, work)
        results.append(r)
        state = "GREEN" if r["exit"] == 0 else "RED"
        over = "  OVER BUDGET" if r["secs"] > r["budget"] else ""
        print(
            f"JOB  {name:<8} {state:<5} exit {r['exit']:<3} {r['secs']:>4} s  "
            f"({r['ran']} run, {r['emulated']} emulated or skipped){over}"
        )
        if r["exit"]:
            print(f"      failed at: {r['step']}")
            print(r["tail"])
    green = sum(r["exit"] == 0 for r in results)
    slow = max(results, key=lambda r: r["secs"])
    print(
        f"W9.10 rehearsal: {green} of {len(results)} jobs green on a clean clone of HEAD; "
        f"slowest {slow['job']} {slow['secs']} s on this Mac (a proxy, not the runner's "
        "wall clock). Clause 3 stays PENDING-OWNER."
    )
    if keep:
        print(f"work kept at {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if green == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
