"""MT-01, Chapter 2 half: the W4.7 prior predictive gates, recomputed without R.

Owner: SOP W4.7. MT-01 reads the Chapter 2 gates "on the probit scale" (SOP section 6), and
SOP W4.10 fits M1 on the logit link. The W4.7 script samples M1's prior on both links, and
both arms' two gates are the verdict. M1's Intercept prior is normal(0, INTERCEPT_SD), the
smallest multiple of 0.05 at which both links clear both gates by two Monte Carlo standard
errors of the gate's own 1,000-draw quantile (`--derive`, out/ch2/log/intercept_scale.json).
SOP W4.10's normal(0, 1.5) is the sensitivity arm SENS-M1-INTERCEPT-SOP: sampled, reported and
not gated. docs/prereg/ch2.md section 6 records the change.

Every quantile here is recomputed from the per-draw values the script writes into
out/ch2/log/prior_predictive.json, with R's default type 7 quantile. The file is a list of one
record, the shape the W2.21 export gate (tests/unit/test_exports.py) reads. The last test
reruns the R script with --check, which samples the prior again and compares every number.
The json and the frame are not in git, so on a clean clone these tests skip.
"""

import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

from absump import paths

ROOT = pathlib.Path(__file__).resolve().parents[2]
JSON = ROOT / "out" / "ch2" / "log" / "prior_predictive.json"
DERIVE = ROOT / "out" / "ch2" / "log" / "intercept_scale.json"
SCRIPT = ROOT / "R" / "ch2" / "03_prior_predictive.R"
ISD = float(
    re.search(r"^INTERCEPT_SD +<- ([0-9.]+)$", SCRIPT.read_text(encoding="utf-8"), re.M).group(1)
)
PRIORS = [f"normal(0, {ISD:g}) on Intercept (centred)", "normal(0, 1) on b", "exponential(4) on sd"]
SOP_PRIORS = ["normal(0, 1.5) on Intercept (centred)", "normal(0, 1) on b", "exponential(4) on sd"]
LINKS = ("probit", "logit")
TOL = 2e-6  # per-draw S is stored to 6 decimals, file quantiles are rounded to 6

if not JSON.exists():
    pytest.skip(
        "out/ch2/log/prior_predictive.json is absent (clean clone): run W4.7 first",
        allow_module_level=True,
    )

RAW = json.loads(JSON.read_text(encoding="utf-8"))
J = RAW[0] if isinstance(RAW, list) and RAW else RAW


def q7(xs, p):
    """R's default quantile, type 7."""
    s = sorted(xs)
    h = (len(s) - 1) * p
    lo = math.floor(h)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


def league_rate(arm):
    n = J["design"]["n"]
    return [k / n for k in arm["per_draw"]["n_overturned"]]


def test_file_is_a_list_of_one_record():
    assert isinstance(RAW, list) and len(RAW) == 1 and isinstance(RAW[0], dict)


def test_priors_and_draws():
    assert J["model"]["priors"] == PRIORS
    assert J["model"]["priors_sensitivity_arm"] == SOP_PRIORS
    assert J["model"]["sample_prior"] == "only"
    for arms, prior in (
        (J["arms"], f"normal(0, {ISD:g})"),
        (J["sensitivity_arms"], "normal(0, 1.5)"),
    ):
        for link in LINKS:
            a = arms[link]
            assert a["intercept_prior"] == prior and a["link"] == link
            assert a["draws"] == 1000 and len(a["per_draw"]["n_overturned"]) == 1000
            assert a["sampler"]["seed"] == 20260922 and a["sampler"]["divergent"] == 0


def test_outcome_never_read_and_no_fit():
    assert J["design"]["outcome_read"] is False
    assert not list((ROOT / "out" / "ch2").rglob("provenance.json"))


@pytest.mark.parametrize("link", LINKS)
def test_mt01_ch2_gate1_league_rate(link):
    a = J["arms"][link]
    L = league_rate(a)
    lo, hi, md = q7(L, 0.025), q7(L, 0.975), q7(L, 0.5)
    g = a["gates"]["gate1_league_rate"]
    assert abs(g["interval95"][0] - lo) < TOL and abs(g["interval95"][1] - hi) < TOL
    assert abs(g["median"] - md) < TOL
    assert lo <= 0.10 and hi >= 0.90, (
        f"{link}: 95% interval [{lo:.4f}, {hi:.4f}] does not cover [0.10, 0.90]"
    )
    assert 0.35 <= md <= 0.65, f"{link}: median {md:.4f} outside [0.35, 0.65]"


@pytest.mark.parametrize("link", LINKS)
def test_mt01_ch2_gate2_between_challenger_sd(link):
    a = J["arms"][link]
    s90 = q7(a["per_draw"]["between_challenger_sd"], 0.90)
    assert abs(a["gates"]["gate2_between_challenger_sd"]["q90"] - s90) < TOL
    assert s90 < 0.30, f"{link}: q90 {s90:.4f} is not below 0.30"


def test_verdict_is_both_arms():
    assert J["gated_arm"] == list(LINKS)
    both = all(
        J["arms"][k]["gates"]["gate1_league_rate"]["pass"]
        and J["arms"][k]["gates"]["gate2_between_challenger_sd"]["pass"]
        for k in LINKS
    )
    assert J["verdict"] == ("PASS" if both else "FAIL")
    assert J["verdict"] == "PASS"


@pytest.mark.parametrize("link", LINKS)
def test_sensitivity_arm_is_reported_and_agrees_with_its_draws(link):
    f = [
        x
        for x in J["sensitivity_findings"]
        if x["id"] == "SENS-M1-INTERCEPT-SOP" and x["arm"] == link
    ]
    assert len(f) == 1
    f = f[0]
    a = J["sensitivity_arms"][link]
    L = league_rate(a)
    lo, hi = q7(L, 0.025), q7(L, 0.975)
    assert abs(f["gate1_interval95"][0] - lo) < TOL and abs(f["gate1_interval95"][1] - hi) < TOL
    assert f["gate1_holds"] == (lo <= 0.10 and hi >= 0.90 and 0.35 <= q7(L, 0.5) <= 0.65)
    assert abs(f["gate1_shortfall_lower"] - max(0.0, lo - 0.10)) < TOL
    assert abs(f["gate1_shortfall_upper"] - max(0.0, 0.90 - hi)) < TOL
    s90 = q7(a["per_draw"]["between_challenger_sd"], 0.90)
    assert abs(f["gate2_q90"] - s90) < TOL and f["gate2_holds"] == (s90 < 0.30)


def test_intercept_scale_is_the_derived_one():
    assert DERIVE.exists(), "out/ch2/log/intercept_scale.json is absent: run --derive"
    rows = json.loads(DERIVE.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
    grid = sorted({r["intercept_sd"] for r in rows})
    clears = {
        g: all(r["gates_hold_by_two_se"] for r in rows if r["intercept_sd"] == g) for g in grid
    }
    assert all(len([r for r in rows if r["intercept_sd"] == g]) == len(LINKS) for g in grid)
    first = min(g for g in grid if clears[g])
    assert abs(first - ISD) < 1e-9, f"derived {first}, script {ISD}"
    assert [r["intercept_sd"] for r in rows if r["chosen"]] == [first] * len(LINKS)
    for r in rows:
        ok = (
            r["league_rate_q025"] + 2 * r["se1000_q025"] <= 0.10
            and r["league_rate_q975"] - 2 * r["se1000_q975"] >= 0.90
            and 0.35 + 2 * r["se1000_q50"] <= r["league_rate_q50"] <= 0.65 - 2 * r["se1000_q50"]
            and r["between_sd_q90"] + 2 * r["se1000_between_sd_q90"] < 0.30
        )
        assert ok == r["gates_hold_by_two_se"], (r["link"], r["intercept_sd"])


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not on PATH")
def test_rerun_matches_file():
    for p in (ROOT / "data/interim/ch2/challenges.parquet", paths.DUCKDB_PATH):
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} absent")
    r = subprocess.run(
        ["Rscript", str(SCRIPT.relative_to(ROOT)), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    tail = "\n".join(r.stdout.splitlines()[-6:])
    assert r.returncode == 0, tail
    assert "RECORD MT-01 Chapter 2 verdict: PASS" in r.stdout, tail
