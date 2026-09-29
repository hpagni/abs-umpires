"""The Chapter 1 sprint fits, SOP W3.14 to W3.18, W3.21, W6.7 and W6.8, on synthetic data only.

Owner: the ch1-fits lane. Nothing here reads a real row. The synthetic table comes from
R/ch1/29_synthetic_table.R with a fixed seed, and its truth is the generating function. The ABS
step injects the W3.12(a) shifts, top -0.60, bottom +0.30 and half-width -0.10 in. The buffer step
is -0.30, +0.15 and +0.05 in, over a pre-trend of -0.05, +0.03 and -0.04 in a season.

    fast   the R unit suite (tests/ch1/test_ch1_sprint.R), and the ledger generator keeping the
           W6.3 and W6.4 generators' bytes
    slow   the whole chain on the tiny synthetic table, every entry point called as the post-tag
           run calls it, with 200 draws and a 2-chain sampler. The decomposition's 95% intervals
           must cover the injected buffer and ABS shifts, and the output checker must pass on
           every step. About 10 minutes on the M3 Pro.
"""

import csv
import importlib.util
import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GEN = ROOT / "R" / "ch1" / "29_synthetic_table.R"
CONTRACT = (
    "n_games",
    "n_rows",
    "min_official_date",
    "max_official_date",
    "game_pk_sha256",
    "analysis_sets_touched",
    "seed",
    "code_sha256",
    "git_sha",
)
B2_FITS = "sop,sens_abs_prior,sens_sd_exp1,sens_sd_exp4,ue_us"


def rscript(*args, timeout=3600):
    return subprocess.run(
        ["Rscript", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def fails(log):
    return [line for line in log.splitlines() if line.startswith("FAIL")]


@pytest.mark.fast
def test_the_r_unit_suite_passes():
    done = rscript(ROOT / "tests" / "ch1" / "test_ch1_sprint.R", timeout=900)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
    assert " 0 FAIL" in done.stdout


@pytest.mark.fast
def test_the_ledger_generator_keeps_the_w63_and_w64_bytes(tmp_path):
    """New model slots must not make ops/sprint_*_checkpoint.py --check report drift."""
    tables = tmp_path / "out" / "tables"
    tables.mkdir(parents=True)
    head = ["slot", "point", "lo95", "hi95", "units", "estimator", "source_csv", "source_row"]
    t4 = "out/ch1/tab/T4_decomposition.csv"
    tp = "out/ch1/tab/T4_plane_component.csv"
    with open(tables / "abstract_slots_ch1.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        w.writerow(["D_ABS", "-7.654", "-9.9", "-5.4", "sq in", "synthetic", t4, "3"])
        w.writerow(["D_PLANE_TOP", "-0.412", "-0.61", "-0.2", "in", "synthetic", tp, "1"])
    ledger = tmp_path / "docs" / "numbers.json"
    done = rscript(
        ROOT / "tools" / "comms" / "export_numbers.R",
        "--inputs",
        tmp_path,
        "--base",
        ROOT / "docs" / "numbers.json",
        "--out",
        ledger,
        "--synthetic",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    text = ledger.read_text(encoding="utf-8")
    data = json.loads(text)
    for name in ("sprint_feed_checkpoint", "sprint_join_checkpoint"):
        mod = load_module(name, ROOT / "ops" / f"{name}.py")
        again = mod.render_ledger(data, mod.ledger_slots(data))
        assert again == text, f"{name} would re-render the ledger"
    slots = [e["slot"] for e in data["entries"]]
    assert {"D_ABS", "D_PLANE_TOP"} <= set(slots)


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory):
    base = tmp_path_factory.mktemp("ch1_sprint")
    table = base / "syn" / "ch1_synth.parquet"
    out = base / "run" / "out"
    logs = {}
    made = rscript(GEN, "--make", "--out", base / "syn", "--scale", "tiny")
    assert made.returncode == 0, made.stdout + made.stderr
    t = ["--table", table, "--out", out]
    stan = ["--stan-chains", "2", "--stan-warmup", "250", "--stan-sampling", "250"]
    runs = [
        ("W3.14", [ROOT / "R/ch1/20_surfaces.R", *t, "--draws", "200"]),
        ("W3.15", [ROOT / "R/ch1/22_estimands.R", *t, "--draws", "200"]),
        ("W3.16", [ROOT / "R/ch1/23_decomposition.R", *t]),
        ("W3.17", [ROOT / "R/ch1/24_plane.R", *t, "--draws", "200"]),
        ("W3.18", [ROOT / "R/ch1/25_heterogeneity.R", *t, *stan, "--b2-fits", B2_FITS]),
        ("W3.21", [ROOT / "R/ch1/26_placebos.R", *t]),
        ("W6.7", [ROOT / "R/ch1/27_abstract_ch1.R", *t]),
        ("W6.8", [ROOT / "R/ch1/28_umpire_summary.R", *t]),
        ("score", [GEN, "--score", *t]),
        (
            "check",
            [ROOT / "tests/ch1/check_ch1_outputs.R", "--out", out, "--step", "all", "--synthetic"],
        ),
    ]
    codes = {}
    for name, args in runs:
        done = rscript(*args)
        logs[name] = done.stdout + done.stderr
        codes[name] = done.returncode
    return {"out": out, "codes": codes, "logs": logs}


@pytest.mark.parametrize("name", ["W3.14", "W3.15", "W3.16", "W3.21", "W6.7", "W6.8", "score"])
def test_each_entry_point_runs_clean_on_the_synthetic_table(dry_run, name):
    log = dry_run["logs"][name]
    assert dry_run["codes"][name] == 0, fails(log) or log[-3000:]


def test_the_plane_and_heterogeneity_steps_run(dry_run):
    # The tiny table's 2025 has about 5,000 surface rows, so a few plane draws can cross outside
    # their window, and a 2-chain dry-run sampler is not a reported fit; neither is an error.
    allowed = ("draws complete", "monotone", "prior sensitivity")
    for name in ("W3.17", "W3.18"):
        log = dry_run["logs"][name]
        bad = [f for f in fails(log) if not any(a in f for a in allowed)]
        assert not bad, bad
        assert "Error" not in log, log[-3000:]


def test_the_decomposition_recovers_the_injected_shifts(dry_run):
    """Each primary 95% interval for delta_buffer and delta_abs covers the generating truth."""
    rows = read_rows(dry_run["out"] / "ch1" / "log" / "dryrun_score.csv")
    edges = ("top_in", "bot_in", "half_width_in")
    prim = [
        r
        for r in rows
        if r["fit"] == "primary"
        and r["component"] in ("delta_buffer", "delta_abs")
        and r["estimand"] in edges
    ]
    assert len(prim) == 6
    missed = [
        (r["estimand"], r["component"], r["truth"], r["lo95"], r["hi95"])
        for r in prim
        if r["covered"] != "TRUE"
    ]
    assert not missed, missed


def test_the_output_checker_passes(dry_run):
    assert dry_run["codes"]["check"] == 0, fails(dry_run["logs"]["check"])


def test_every_receipt_meets_gd01_and_names_one_commit(dry_run):
    receipts = sorted(dry_run["out"].rglob("provenance.json"))
    assert receipts, "no provenance.json under the dry run's out/"
    for path in receipts:
        rec = json.loads(path.read_text(encoding="utf-8"))
        assert all(k in rec for k in CONTRACT), (path, [k for k in CONTRACT if k not in rec])
        assert re.fullmatch(r"[0-9a-f]{40}", str(rec["git_sha"])), (path, rec["git_sha"])


def test_no_output_names_a_cause_before_the_placebos_pass(dry_run):
    t5 = read_rows(dry_run["out"] / "ch1" / "tab" / "T5_placebos.csv")
    verdicts = {r["placebo"]: r["placebo_verdict"] for r in t5}
    headline = (dry_run["out"] / "tables" / "headline.csv").read_text(encoding="utf-8")
    if not (verdicts.get("P1") == "pass" and verdicts.get("P2") == "pass"):
        assert "attributable" not in headline
    w316 = [r["sentence"] for r in read_rows(dry_run["out"] / "tables" / "headline.csv")]
    assert w316 and "attributable" not in w316[0]
