"""MT-01, Chapter 1 half: what the B2 prior implies, from the stored link and design.

SOP 6.5: "MT-01 prior predictive (Ch1: implied shadow-zone called-strike rate in [0.10, 0.90]
for >=95% of draws, implied between-umpire SD of the top-edge shift < 3.0 in for >=99%)".

Chapter 1's one prior is B2's, SOP W3.18: b ~ normal(0, 1), sd ~ exponential(2),
sigma ~ exponential(2), cor ~ lkj(2). The surface is a penalised bam with no prior to check.
B2's outcome is an offset delta, in inches, from the league link g_e(d) that W3.12 fitted on
2022-2024 (out/dev/ch1_synth/link.parquet, logits on a 0.001 in grid). A draw's implied
called-strike rate is the mean of g_e(d - delta) over the shadow band |d| <= 3.0 in (SOP W3.5)
at the 2022-2024 pitch locations. No 2025 or 2026 row is read.

The gated reading follows the SOP's words, one rate per draw: the league rate (delta is the
edge's fixed effects in that regime, no umpire term), pooled over the three edges by their
2022-2024 shadow-band pitch counts, in each regime B2 predicts. The per-edge, umpire and cell
readings are reported in logs/decisions-pending/model-tests.md, not gated here. The SD clause
reads tau, the SD of abs_step: B2's umpire terms are shared by the edges, so it is the
between-umpire SD of the 2025 -> 2026 top-edge shift. The 2024 -> 2026 shift's SD is gated too.
Draws are numpy's, 20,000 at seed 20260922, so the Monte Carlo SE of a share near 0.95 is 0.0015.
"""

import re

import numpy as np
import pytest
from mt_ch1_common import SCRIPT, SYN, need

pytestmark = pytest.mark.fast
LINK, DESIGN = SYN / "link.parquet", SYN / "design.parquet"
need(LINK, DESIGN, SCRIPT)
pq = pytest.importorskip("pyarrow.parquet")

EDGES = ("side", "top", "bot")
S, SEED, BAND, STEP = 20_000, 20260922, 3.0, 0.001
DGRID = np.round(np.arange(-8.0, 8.0 + 1e-9, 0.01), 2)


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
        "b_abs": rng.normal(0, 1, (S, 3)),
        "tau_buf": rng.exponential(0.5, S),
        "tau": rng.exponential(0.5, S),
        "rho": 2 * rng.beta(2.5, 2.5, S) - 1,
    }  # LKJ(2) margin at K = 3: (r + 1) / 2 ~ Beta(2.5, 2.5)
    return curves, counts, pr


CURVES, COUNTS, PRIOR = _setup()
WEIGHTS = np.array([COUNTS[e] for e in EDGES], float) / sum(COUNTS.values())
REGIMES = {
    "pre_buffer": PRIOR["b"],
    "buffer_2025": PRIOR["b"] + PRIOR["b_buf"],
    "abs_2026": PRIOR["b"] + PRIOR["b_buf"] + PRIOR["b_abs"],
}


def _rate_at_zero():
    mix = sum(w * CURVES[e] for w, e in zip(WEIGHTS, EDGES, strict=True))
    return float(np.interp(0, DGRID, mix))


def test_the_priors_checked_are_the_models():
    src = SCRIPT.read_text(encoding="utf-8")
    body = re.search(r"b2_priors <- function\(\) \{(.*?)\n\}", src, re.S).group(1)
    for p in (
        'normal(0, 1), class = "b"',
        'exponential(2), class = "sd"',
        'exponential(2), class = "sigma"',
        'lkj(2), class = "cor"',
    ):
        assert p in body, f"b2_priors() no longer carries {p}"


@pytest.mark.parametrize("regime", list(REGIMES))
def test_mt01_league_shadow_rate_in_band(regime):
    delta = REGIMES[regime]
    rate = (
        np.column_stack([np.interp(delta[:, i], DGRID, CURVES[e]) for i, e in enumerate(EDGES)])
        @ WEIGHTS
    )
    share = float(np.mean((rate >= 0.10) & (rate <= 0.90)))
    assert share >= 0.95, (
        f"{regime}: implied shadow-zone called-strike rate in [0.10, 0.90] "
        f"in {share:.4f} of {S} draws, "
        f"needs >= 0.95; above 0.90 in {np.mean(rate > 0.90):.4f}, "
        f"below 0.10 in {np.mean(rate < 0.10):.4f}; "
        f"rate at delta = 0 is {_rate_at_zero():.3f}"
    )


def test_mt01_between_umpire_sd_of_top_edge_shift():
    tau, tb, rho = PRIOR["tau"], PRIOR["tau_buf"], PRIOR["rho"]
    s_abs = float(np.mean(tau < 3.0))
    s_all = float(np.mean(np.sqrt(tb**2 + tau**2 + 2 * rho * tb * tau) < 3.0))
    assert abs(s_abs - (1 - np.exp(-6.0))) < 0.002
    assert s_abs >= 0.99, f"2025 -> 2026 shift: SD < 3.0 in in {s_abs:.4f} of draws"
    assert s_all >= 0.99, f"2024 -> 2026 shift: SD < 3.0 in in {s_all:.4f} of draws"
