"""MT-01, Chapter 2 half: the W4.7 prior predictive gates, recomputed without R.

Owner: SOP W4.7 (lane ch2-w47). The rest of tests/model belongs to the model-tests lane.

MT-01 reads the Chapter 2 gates "on the probit scale" (SOP section 6). The W4.7 script
samples M1's prior on two links. The probit arm's two gates are the verdict. The logit
arm, the link SOP W4.10 fits, is the named sensitivity finding SENS-W4.7-LOGIT: its
numbers must be present and must agree with its own draws, but they do not gate.

Every quantile here is recomputed from the per-draw values the script writes into
out/ch2/log/prior_predictive.json, with R's default type 7 quantile. The last test reruns
the R script with --check, which samples the prior again and compares every number.
The json and the frame are not in git, so on a clean clone these tests skip.
"""

import json
import math
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
JSON = ROOT / "out" / "ch2" / "log" / "prior_predictive.json"
SCRIPT = ROOT / "R" / "ch2" / "03_prior_predictive.R"
SOP_PRIORS = ["normal(0, 1.5) on Intercept (centred)", "normal(0, 1) on b", "exponential(4) on sd"]
TOL = 2e-6  # per-draw S is stored to 6 decimals, file quantiles are rounded to 6

if not JSON.exists():
    pytest.skip(
        "out/ch2/log/prior_predictive.json is absent (clean clone): run W4.7 first",
        allow_module_level=True,
    )

J = json.loads(JSON.read_text(encoding="utf-8"))


def q7(xs, p):
    """R's default quantile, type 7."""
    s = sorted(xs)
    h = (len(s) - 1) * p
    lo = math.floor(h)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


def league_rate(arm):
    n = J["design"]["n"]
    return [k / n for k in J["arms"][arm]["per_draw"]["n_overturned"]]


def between_sd(arm):
    return J["arms"][arm]["per_draw"]["between_challenger_sd"]


def test_priors_and_draws_are_the_sop_ones():
    assert J["model"]["priors"] == SOP_PRIORS
    assert J["model"]["sample_prior"] == "only"
    for arm in ("probit", "logit"):
        a = J["arms"][arm]
        assert a["draws"] == 1000 and len(a["per_draw"]["n_overturned"]) == 1000
        assert a["sampler"]["seed"] == 20260922 and a["sampler"]["divergent"] == 0


def test_outcome_never_read_and_no_fit():
    assert J["design"]["outcome_read"] is False
    assert not list((ROOT / "out" / "ch2").rglob("provenance.json"))


def test_mt01_ch2_gate1_probit_league_rate():
    L = league_rate("probit")
    lo, hi, md = q7(L, 0.025), q7(L, 0.975), q7(L, 0.5)
    g = J["arms"]["probit"]["gates"]["gate1_league_rate"]
    assert abs(g["interval95"][0] - lo) < TOL and abs(g["interval95"][1] - hi) < TOL
    assert abs(g["median"] - md) < TOL
    assert lo <= 0.10 and hi >= 0.90, (
        f"95% interval [{lo:.4f}, {hi:.4f}] does not cover [0.10, 0.90]"
    )
    assert 0.35 <= md <= 0.65, f"median {md:.4f} outside [0.35, 0.65]"


def test_mt01_ch2_gate2_probit_between_challenger_sd():
    s90 = q7(between_sd("probit"), 0.90)
    assert abs(J["arms"]["probit"]["gates"]["gate2_between_challenger_sd"]["q90"] - s90) < TOL
    assert s90 < 0.30, f"q90 {s90:.4f} is not below 0.30"


def test_verdict_is_the_probit_arm():
    assert J["gated_arm"] == "probit"
    g = J["arms"]["probit"]["gates"]
    both = g["gate1_league_rate"]["pass"] and g["gate2_between_challenger_sd"]["pass"]
    assert J["verdict"] == ("PASS" if both else "FAIL")
    assert J["verdict"] == "PASS"


def test_sens_logit_is_reported_and_agrees_with_its_draws():
    f = [x for x in J["sensitivity_findings"] if x["id"] == "SENS-W4.7-LOGIT"]
    assert len(f) == 1 and f[0]["arm"] == "logit"
    f = f[0]
    L = league_rate("logit")
    lo, hi = q7(L, 0.025), q7(L, 0.975)
    assert abs(f["gate1_interval95"][0] - lo) < TOL and abs(f["gate1_interval95"][1] - hi) < TOL
    assert f["gate1_holds"] == (lo <= 0.10 and hi >= 0.90 and 0.35 <= q7(L, 0.5) <= 0.65)
    assert abs(f["gate1_shortfall_lower"] - max(0.0, lo - 0.10)) < TOL
    assert abs(f["gate1_shortfall_upper"] - max(0.0, 0.90 - hi)) < TOL
    s90 = q7(between_sd("logit"), 0.90)
    assert abs(f["gate2_q90"] - s90) < TOL and f["gate2_holds"] == (s90 < 0.30)


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not on PATH")
def test_rerun_matches_file():
    for p in ("data/interim/ch2/challenges.parquet", "warehouse/abs.duckdb"):
        if not (ROOT / p).exists():
            pytest.skip(f"{p} absent")
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
