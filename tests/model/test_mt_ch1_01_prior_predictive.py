"""MT-01, Chapter 1 half: what the B2 prior implies, from the stored link and design.

SOP 6.5: "MT-01 prior predictive (Ch1: implied shadow-zone called-strike rate in [0.10, 0.90]
for >=95% of draws, implied between-umpire SD of the top-edge shift < 3.0 in for >=99%)".

Chapter 1's one prior is B2's, SOP W3.18: b ~ normal(0, 1), sd ~ exponential(2),
sigma ~ exponential(2), cor ~ lkj(2), except the three edge:abs_step coefficients, whose prior
is normal(0, ABS_STEP_PRIOR_SD) (R/ch1/21_synthetic.R; docs/prereg/ch1.md 8.8). The surface is a
penalised bam with no prior to check. B2's outcome is an offset delta, in inches, from the
league link g_e(d) that W3.12 fitted on 2022-2024 (out/dev/ch1_synth/link.parquet, logits on a
0.001 in grid). A draw's implied called-strike rate is the mean of g_e(d - delta) over the shadow
band |d| <= 3.0 in (SOP W3.5) at the 2022-2024 pitch locations. No 2025 or 2026 row is read.

The gated reading follows the SOP's words, one rate per draw: the league rate (delta is the
edge's fixed effects in that regime, no umpire term), pooled over the three edges by their
2022-2024 shadow-band pitch counts, in each regime B2 predicts. The share of prior draws inside
[0.10, 0.90] is computed exactly: the rate is increasing in each edge's offset, so the bottom
edge's offset is integrated in closed form and the other two by 300-node Gauss-Hermite
quadrature. A 20,000-draw Monte Carlo at seed 20260922, the reading this test used before the
tag, is kept as a cross-check within four Monte Carlo standard errors. The SD clause reads tau,
the SD of abs_step: B2's umpire terms are shared by the edges, so it is the between-umpire SD of
the 2025 -> 2026 top-edge shift. The 2024 -> 2026 shift's SD is gated too.
"""

import re

import numpy as np
import pytest
from mt_ch1_common import SCRIPT, SYN, need

pytestmark = pytest.mark.fast
LINK, DESIGN = SYN / "link.parquet", SYN / "design.parquet"
need(LINK, DESIGN, SCRIPT)
pq = pytest.importorskip("pyarrow.parquet")
norm = pytest.importorskip("scipy.stats").norm

EDGES = ("side", "top", "bot")
S, SEED, BAND, STEP = 20_000, 20260922, 3.0, 0.001
DGRID = np.round(np.arange(-8.0, 8.0 + 1e-9, 0.01), 2)
SRC = SCRIPT.read_text(encoding="utf-8")
ABS_SD = float(re.search(r"^ABS_STEP_PRIOR_SD <- ([0-9.]+)$", SRC, re.M).group(1))
SOP_SD = 1.0  # SOP W3.18's normal(0, 1), the sensitivity arm SENS-B2-ABS-PRIOR


def _setup():
    lk = pq.read_table(LINK).to_pandas()
    u = lk["u"].to_numpy()
    assert abs(u[0] + 8) < 1e-9 and abs(u[-1] - 8) < 1e-9 and len(u) == 16001
    df = pq.read_table(
        DESIGN, columns=["season", "edge", "d"], filters=[("season", "<=", 2024)]
    ).to_pandas()
    assert set(df["season"]) == {2022, 2023, 2024} and df["d"].abs().max() <= BAND
    curves, counts = {}, {}
    for e in EDGES:
        d = df.loc[df["edge"] == e, "d"].to_numpy()
        lp = lk[e].to_numpy()
        w = np.bincount(
            np.clip(np.rint((d + 8) / STEP).astype(int), 0, len(u) - 1), minlength=len(u)
        )
        nz = np.nonzero(w)[0]
        rate = np.empty(len(DGRID))
        for k, dl in enumerate(DGRID):
            j = np.clip(nz - round(dl / STEP), 0, len(u) - 1)
            rate[k] = (w[nz] / (1 + np.exp(-lp[j]))).sum() / w.sum()
        curves[e], counts[e] = rate, len(d)
    rng = np.random.default_rng(SEED)
    pr = {
        "b": rng.normal(0, 1, (S, 3)),
        "b_buf": rng.normal(0, 1, (S, 3)),
        "z_abs": rng.normal(0, 1, (S, 3)),
        "tau_buf": rng.exponential(0.5, S),
        "tau": rng.exponential(0.5, S),
        "rho": 2 * rng.beta(2.5, 2.5, S) - 1,
    }  # LKJ(2) margin at K = 3: (r + 1) / 2 ~ Beta(2.5, 2.5)
    return curves, counts, pr


CURVES, COUNTS, PRIOR = _setup()
WEIGHTS = np.array([COUNTS[e] for e in EDGES], float) / sum(COUNTS.values())
X_GH, W_GH = np.polynomial.hermite_e.hermegauss(300)
W_GH = W_GH / W_GH.sum()


def regime_sd(regime, abs_sd):
    """The prior SD of one edge's league offset: b, b + b_buf, b + b_buf + b_abs."""
    return {"pre_buffer": 1.0, "buffer_2025": 2**0.5, "abs_2026": (2 + abs_sd**2) ** 0.5}[regime]


def exact_share(sd):
    """P(pooled league rate in [0.10, 0.90]) when each edge's offset is N(0, sd), independent."""
    for e in EDGES:
        assert np.all(np.diff(CURVES[e]) > 0), f"{e}: the rate is not increasing in the offset"
    a = (
        WEIGHTS[0] * np.interp(sd * X_GH, DGRID, CURVES["side"])[:, None]
        + WEIGHTS[1] * np.interp(sd * X_GH, DGRID, CURVES["top"])[None, :]
    )
    cb = CURVES["bot"]

    def offset_at(y):
        x = np.interp(y, cb, DGRID)
        return np.where(y >= cb[-1], np.inf, np.where(y <= cb[0], -np.inf, x))

    lo, hi = offset_at((0.10 - a) / WEIGHTS[2]), offset_at((0.90 - a) / WEIGHTS[2])
    return float((W_GH[:, None] * W_GH[None, :] * (norm.cdf(hi / sd) - norm.cdf(lo / sd))).sum())


def mc_share(regime, abs_sd):
    delta = {
        "pre_buffer": PRIOR["b"],
        "buffer_2025": PRIOR["b"] + PRIOR["b_buf"],
        "abs_2026": PRIOR["b"] + PRIOR["b_buf"] + abs_sd * PRIOR["z_abs"],
    }[regime]
    rate = (
        np.column_stack([np.interp(delta[:, i], DGRID, CURVES[e]) for i, e in enumerate(EDGES)])
        @ WEIGHTS
    )
    return float(np.mean((rate >= 0.10) & (rate <= 0.90)))


def test_the_priors_checked_are_the_models():
    body = re.search(r"b2_priors <- function\(abs_sd = ABS_STEP_PRIOR_SD\) \{(.*?)\n\}", SRC, re.S)
    assert body, "b2_priors() no longer takes abs_sd = ABS_STEP_PRIOR_SD"
    for p in (
        'normal(0, 1), class = "b"',
        'exponential(2), class = "sd"',
        'exponential(2), class = "sigma"',
        'lkj(2), class = "cor"',
        'set_prior(sprintf("normal(0, %s)", format(abs_sd)), class = "b", coef = cf)',
    ):
        assert p in body.group(1), f"b2_priors() no longer carries {p}"
    coefs = re.search(r"^ABS_STEP_COEFS +<- c\((.*)\)$", SRC, re.M).group(1)
    assert coefs == '"edgeside:abs_step", "edgetop:abs_step", "edgebot:abs_step"'


@pytest.mark.parametrize("regime", ["pre_buffer", "buffer_2025", "abs_2026"])
def test_mt01_league_shadow_rate_in_band(regime):
    share = exact_share(regime_sd(regime, ABS_SD))
    assert share >= 0.95, (
        f"{regime}: implied shadow-zone called-strike rate in [0.10, 0.90] in {share:.5f} of "
        f"the prior (exact), needs >= 0.95; abs_step prior normal(0, {ABS_SD})"
    )


@pytest.mark.parametrize("regime", ["pre_buffer", "buffer_2025", "abs_2026"])
def test_monte_carlo_reading_agrees_with_the_exact_share(regime):
    ex, mc = exact_share(regime_sd(regime, ABS_SD)), mc_share(regime, ABS_SD)
    se = (ex * (1 - ex) / S) ** 0.5
    assert abs(mc - ex) <= 4 * se, f"{regime}: Monte Carlo {mc:.4f}, exact {ex:.5f}, se {se:.4f}"


def test_abs_step_prior_is_the_derived_scale():
    """docs/prereg/ch1.md 8.8: the largest multiple of 0.05 in at which all three regimes clear."""
    ok = [
        s
        for s in np.round(np.arange(0.05, 1.0001, 0.05), 2)
        if all(
            exact_share(regime_sd(r, s)) >= 0.95 for r in ("pre_buffer", "buffer_2025", "abs_2026")
        )
    ]
    assert ok and abs(max(ok) - ABS_SD) < 1e-9, (
        f"derived {max(ok) if ok else None}, script {ABS_SD}"
    )


def test_sensitivity_arm_is_the_sop_prior_and_is_recorded_not_gated():
    share = exact_share(regime_sd("abs_2026", SOP_SD))
    assert "SENS-B2-ABS-PRIOR" in SRC and "b2_priors(NA)" in SRC
    assert share < 0.95, f"the SOP prior now clears 2026 ({share:.5f}); the annex says it does not"


def test_mt01_between_umpire_sd_of_top_edge_shift():
    tau, tb, rho = PRIOR["tau"], PRIOR["tau_buf"], PRIOR["rho"]
    s_abs = float(np.mean(tau < 3.0))
    s_all = float(np.mean(np.sqrt(tb**2 + tau**2 + 2 * rho * tb * tau) < 3.0))
    assert abs(s_abs - (1 - np.exp(-6.0))) < 0.002
    assert s_abs >= 0.99, f"2025 -> 2026 shift: SD < 3.0 in in {s_abs:.4f} of draws"
    assert s_all >= 0.99, f"2024 -> 2026 shift: SD < 3.0 in in {s_all:.4f} of draws"
