"""The Chapter 1 sprint fits, SOP W3.14 to W3.18, W3.21, W6.7 and W6.8, on synthetic data only.

Owner: the ch1-fits lane. Nothing here reads a real row. The synthetic table comes from
R/ch1/29_synthetic_table.R with a fixed seed, and its truth is the generating function. The ABS
step injects the W3.12(a) shifts, top -0.60, bottom +0.30 and half-width -0.10 in. The buffer step
is -0.30, +0.15 and +0.05 in, over a pre-trend of -0.05, +0.03 and -0.04 in a season.

    fast   the R unit suite (tests/ch1/test_ch1_sprint.R). The ledger generator keeping the W6.3
           and W6.4 generators' bytes is tests/unit/test_abstract_ledger.py's (W7.24).
    slow   the whole chain on the tiny synthetic table, every entry point called as the post-tag
           run calls it, with 200 draws and a 2-chain sampler. The decomposition's 95% intervals
           must cover the injected buffer and ABS shifts, and the output checker must pass on
           every step. About 10 minutes on the M3 Pro.
"""

import csv
import json
import pathlib
import re
import shutil
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
T2_FIXTURE = ROOT / "tests" / "ch1" / "fixtures" / "T2_zone_gate_synthetic.csv"
ARMS = {
    "main": "primary",
    "undersmooth": "SENS-B1-UNDERSMOOTH",
    "abs_cohort": "ABS-measured arm",
    "single_offset": "SENS-HEIGHT-SINGLE",
    "panel": "CH1-A14 balanced panel",
    "binned": "CH1-A5 binned logistic",
}


def rscript(*args, timeout=3600):
    return subprocess.run(
        ["Rscript", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


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


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory):
    base = tmp_path_factory.mktemp("ch1_sprint")
    table = base / "syn" / "ch1_synth.parquet"
    out = base / "run" / "out"
    logs = {}
    made = rscript(GEN, "--make", "--out", base / "syn", "--scale", "tiny")
    assert made.returncode == 0, made.stdout + made.stderr
    # W6.7 reads N_CHAL from W3.8's zone-gate table; a dry run gets the synthetic fixture.
    (out / "ch1" / "tab").mkdir(parents=True)
    shutil.copy(T2_FIXTURE, out / "ch1" / "tab" / "T2_zone_gate.csv")
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


def test_every_arm_is_in_t3_and_t4_under_its_label(dry_run):
    tab = dry_run["out"] / "ch1" / "tab"
    t3 = read_rows(tab / "T3_estimands.csv")
    assert {r["fit"]: r["arm"] for r in t3} == ARMS
    arms = read_rows(tab / "T4_decomposition_arms.csv")
    assert {r["fit"]: r["arm"] for r in arms} == {k: v for k, v in ARMS.items() if k != "main"}
    t4 = read_rows(tab / "T4_decomposition.csv")
    assert {r["arm"] for r in t4} == {"primary"}


def test_the_height_cohort_flag_agrees_on_the_synthetic_table(dry_run):
    """Every synthetic batter shares the generating zone, so D-P4-04's clause must read agree."""
    t4 = read_rows(dry_run["out"] / "ch1" / "tab" / "T4_decomposition.csv")
    assert {r["height_cohort_flag"] for r in t4} == {"agree"}


def test_n_chal_is_traced_to_the_zone_gate_table(dry_run):
    slots = read_rows(dry_run["out"] / "tables" / "abstract_slots_ch1.csv")
    gate = read_rows(T2_FIXTURE)
    n_chal = [r for r in slots if r["slot"] == "N_CHAL"]
    overall = [r for r in gate if r["row_id"] == "overall"]
    assert len(n_chal) == 1 and len(overall) == 1
    assert float(n_chal[0]["point"]) == float(overall[0]["n"])
    assert n_chal[0]["source_csv"] == "out/ch1/tab/T2_zone_gate.csv"
    assert n_chal[0]["source_columns"] == "n"


def _broken_copy(dry_run, tmp_path, name, edit):
    """A copy of the dry run's out/ with one table edited, and the checker's exit on it."""
    root = tmp_path / name
    shutil.copytree(dry_run["out"], root / "out", symlinks=True)
    path = root / "out" / "ch1" / "tab" / edit[0]
    rows = read_rows(path)
    rows, fields = edit[1](rows, list(rows[0].keys()))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    done = rscript(
        ROOT / "tests/ch1/check_ch1_outputs.R",
        "--out",
        root / "out",
        "--step",
        edit[2],
        "--synthetic",
    )
    return done.returncode, fails(done.stdout)


def test_the_checker_fails_on_a_missing_arm_a_missing_flag_or_a_wrong_label(dry_run, tmp_path):
    cases = {
        "missing_arm_t3": (
            "T3_estimands.csv",
            lambda rows, f: ([r for r in rows if r["fit"] != "single_offset"], f),
            "W3.15",
        ),
        "wrong_label_t3": (
            "T3_estimands.csv",
            lambda rows, f: (
                [{**r, "arm": "SENS-HEIGHT"} if r["fit"] == "single_offset" else r for r in rows],
                f,
            ),
            "W3.15",
        ),
        "missing_arm_t4": (
            "T4_decomposition_arms.csv",
            lambda rows, f: ([r for r in rows if r["fit"] != "abs_cohort"], f),
            "W3.16",
        ),
        "missing_flag": (
            "T4_decomposition.csv",
            lambda rows, f: (rows, [c for c in f if c != "height_cohort_flag"]),
            "W3.16",
        ),
        "wrong_flag": (
            "T4_decomposition.csv",
            lambda rows, f: (
                [
                    {**r, "height_cohort_flag": "primary is sensitive to the height cohort"}
                    for r in rows
                ],
                f,
            ),
            "W3.16",
        ),
    }
    for name, edit in cases.items():
        code, failed = _broken_copy(dry_run, tmp_path, name, edit)
        assert code == 1 and failed, (name, code)
