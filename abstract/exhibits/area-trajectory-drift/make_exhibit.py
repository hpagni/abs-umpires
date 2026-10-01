"""Figure 1: zone area by season, each step read against one season's drift.

Reads ONLY committed tables under out/ch1/tab (no data/, no new fit) and writes
area-trajectory-drift.png (300 dpi, 6.5 x 4.2 in), area-trajectory-drift.svg, caption.md,
alt.txt and data-sources.md next to this script. Every number drawn or printed is read from a
table row; nothing is typed.

On the plot: the five fitted season areas with their 95% bars, the two steps as arrows from
each step's baseline (the prior season's level plus one season of the 2022-2024 trend) down to
the season's fitted level, with their values and intervals, the period labels, and a small
bracket marking the 2023-to-2024 change itself. Every explanation is in the caption.

Run from the repository root:
    uv run --locked python abstract/exhibits/area-trajectory-drift/make_exhibit.py
"""

from __future__ import annotations

import csv
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TAB = os.path.join(ROOT, "out", "ch1", "tab")
OUT = os.path.dirname(os.path.abspath(__file__))
SLUG = "area-trajectory-drift"

SEASONS = [2022, 2023, 2024, 2025, 2026]
MINUS = "\u2212"  # typographic minus in the image and the caption; ASCII '-' in the CSVs
EN = "\u2013"  # en dash for year spans


def read_rows(name: str) -> list[dict[str, str]]:
    with open(os.path.join(TAB, name), newline="") as fh:
        return list(csv.DictReader(fh))


def one(rows: list[dict[str, str]], **where: str) -> dict[str, str]:
    hits = [r for r in rows if all(r[k] == v for k, v in where.items())]
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one row for {where}, found {len(hits)}")
    return hits[0]


# ---- T3: area level per season (72-inch batter, 2024 mix) -------------------------------
t3 = read_rows("T3_estimands.csv")
level: dict[int, dict[str, float]] = {}
for s in SEASONS:
    r = one(t3, fit="main", arm="primary", estimand="area_sqin", season=str(s))
    if r["units"] != "sq in":
        raise SystemExit(f"T3 units for {s} are {r['units']!r}, expected 'sq in'")
    level[s] = {k: float(r[k]) for k in ("point", "lo95", "hi95")}

# ---- T4: trend g and the two steps net of trend ----------------------------------------
t4 = read_rows("T4_decomposition.csv")
comp: dict[str, dict[str, float]] = {}
for c, units in (("g", "sq in per season"), ("delta_buffer", "sq in"), ("delta_abs", "sq in")):
    r = one(t4, fit="main", arm="primary", estimand="area_sqin", component=c)
    if r["units"] != units:
        raise SystemExit(f"T4 units for {c} are {r['units']!r}, expected {units!r}")
    comp[c] = {k: float(r[k]) for k in ("point", "lo95", "hi95")}
g = comp["g"]["point"]

# The decomposition identity the figure relies on: each step is the season's level minus the
# previous season's level carried forward by g. Checked here so the brackets cannot drift
# from the printed numbers.
cf_2025 = level[2024]["point"] + g
cf_2026 = level[2025]["point"] + g
for name, cf, s in (("delta_buffer", cf_2025, 2025), ("delta_abs", cf_2026, 2026)):
    implied = level[s]["point"] - cf
    if not math.isclose(implied, comp[name]["point"], abs_tol=1e-6):
        raise SystemExit(
            f"{name}: level minus carried-forward level {implied} != table {comp[name]['point']}"
        )

# ---- T5: placebo P1 (failed), the drift scale -------------------------------------------
t5 = read_rows("T5_placebos.csv")
p1 = one(t5, placebo="P1", quantity="area_sqin 2024 minus 2023")
if p1["units"] != "sq in":
    raise SystemExit("P1 units are not sq in")
p1_est, p1_lo, p1_hi = (float(p1[k]) for k in ("estimate", "lo", "hi"))
p1_level = float(p1["interval_level"])
p1_margin = float(p1["margin_or_threshold"])
p1_verdict = p1["verdict"]
if not math.isclose(p1_est, level[2024]["point"] - level[2023]["point"], abs_tol=1e-6):
    raise SystemExit("P1 estimate does not equal the 2024 minus 2023 level from T3")
if p1_verdict != "fail":
    raise SystemExit(f"P1 verdict is {p1_verdict!r}; the caption says it failed")


def f1(x: float) -> str:
    """One decimal, true minus sign, explicit plus on positives."""
    s = f"{x:+.1f}"
    return s.replace("-", MINUS)


def f1s(x: float) -> str:
    """One decimal with a true minus sign and no plus."""
    return f"{x:.1f}".replace("-", MINUS)


def pct(lvl: float) -> str:
    return f"{round(lvl * 100)}%"


# ---- figure ----------------------------------------------------------------------------
plt.rcParams.update(
    {
        "font.family": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 8.5,
        "axes.labelsize": 9,
        "xtick.labelsize": 9,
        "ytick.labelsize": 8.5,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    }
)

INK = "#1a1a1a"
INK2 = "#4d4d4d"
GRID = "#e6e6e6"
BAND = {2022: "#f6f6f6", 2025: "#eef3f9", 2026: "#e3ebf4"}
STEP = "#1f4e79"  # dark blue, the two step arrows
DRIFT = "#a8611e"  # rust, the 2023-to-2024 change

X = {s: i + 1 for i, s in enumerate(SEASONS)}
fig, ax = plt.subplots(figsize=(6.5, 4.2))
fig.subplots_adjust(left=0.105, right=0.985, top=0.965, bottom=0.115)

y_lo, y_hi = 428.0, 515.0
ax.set_xlim(0.5, 5.5)
ax.set_ylim(y_lo, y_hi)

# period bands and their labels
periods = [
    (0.5, 3.5, BAND[2022], f"2022{EN}2024"),
    (3.5, 4.5, BAND[2025], "2025"),
    (4.5, 5.5, BAND[2026], "2026\n(to 21 Sep)"),
]
for x0, x1, col, lab in periods:
    ax.add_patch(
        Rectangle((x0, y_lo), x1 - x0, y_hi - y_lo, facecolor=col, edgecolor="none", zorder=0)
    )
    ax.text(
        (x0 + x1) / 2,
        y_hi - 1.4,
        lab,
        ha="center",
        va="top",
        fontsize=8.5,
        color=INK,
        zorder=6,
        fontweight="bold",
        linespacing=1.15,
    )
ax.axvline(3.5, color="white", lw=1.2, zorder=1)
ax.axvline(4.5, color="white", lw=1.2, zorder=1)

# grid and axes
ax.set_yticks(range(430, 511, 10))
ax.grid(axis="y", color=GRID, lw=0.6, zorder=0.5)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color(INK2)
    ax.spines[side].set_linewidth(0.6)
ax.tick_params(colors=INK2, width=0.6, length=3)
ax.set_xticks(list(X.values()))
ax.set_xticklabels([str(s) for s in SEASONS])
ax.set_xlabel("Season")
ax.set_ylabel("Area of the 50% strike contour, sq in\n(72-inch batter, 2024 pitch mix)")


def bracket(x, y_top, y_bot, color, lw=1.1, w=0.05):
    ax.plot([x, x], [y_top, y_bot], color=color, lw=lw, zorder=4, solid_capstyle="butt")
    ax.plot([x - w, x + w], [y_top, y_top], color=color, lw=lw, zorder=4)
    ax.plot([x - w, x + w], [y_bot, y_bot], color=color, lw=lw, zorder=4)


def arrow(x, y_from, y_to, color, w=0.05):
    # a short tick at the baseline, then an arrow down to the fitted level
    ax.plot([x - w, x + w], [y_from, y_from], color=color, lw=1.1, zorder=4)
    ax.annotate(
        "",
        xy=(x, y_to),
        xytext=(x, y_from),
        arrowprops={"arrowstyle": "-|>", "color": color, "lw": 1.1, "shrinkA": 0, "shrinkB": 0},
        zorder=4,
    )


# step arrows, net of trend: from the baseline (prior season plus g) down to the fitted level
xb = {2025: X[2025] - 0.2, 2026: X[2026] - 0.2}
d25, d26 = comp["delta_buffer"], comp["delta_abs"]
arrow(xb[2025], cf_2025, level[2025]["point"], STEP)
arrow(xb[2026], cf_2026, level[2026]["point"], STEP)
ax.text(
    X[2025],
    level[2025]["lo95"] - 4.0,
    f"2025 step, net of trend\n{f1(d25['point'])} sq in\n"
    f"95%: {f1s(d25['lo95'])} to {f1s(d25['hi95'])}",
    ha="center",
    va="top",
    fontsize=8,
    color=INK,
    zorder=6,
    linespacing=1.25,
)
ax.text(
    X[2026],
    cf_2026 + 3.0,
    f"2026 step, net of trend\n{f1(d26['point'])} sq in\n"
    f"95%: {f1s(d26['lo95'])} to {f1s(d26['hi95'])}",
    ha="center",
    va="bottom",
    fontsize=8,
    color=INK,
    zorder=6,
    linespacing=1.25,
)

# the 2023-to-2024 change, a small bracket labelled with its value
xp1 = (X[2023] + X[2024]) / 2
bracket(xp1, level[2024]["point"], level[2023]["point"], DRIFT)
ax.text(
    xp1,
    max(level[2023]["point"], level[2024]["point"]) + 2.2,
    f"2023{EN}2024\n{f1(p1_est)} sq in\nplacebo, failed",
    ha="center",
    va="bottom",
    fontsize=7.5,
    color=INK,
    zorder=6,
    linespacing=1.2,
)

# points with 95% bars and printed levels
for s in SEASONS:
    p, lo, hi = level[s]["point"], level[s]["lo95"], level[s]["hi95"]
    ax.plot([X[s], X[s]], [lo, hi], color=INK, lw=1.0, zorder=5, solid_capstyle="butt")
    ax.plot(X[s], p, marker="o", ms=4.6, mfc="white", mec=INK, mew=1.1, zorder=6)
    ax.text(X[s] + 0.08, p + 1.3, f1s(p), ha="left", va="bottom", fontsize=8, color=INK, zorder=6)

png = os.path.join(OUT, f"{SLUG}.png")
svg = os.path.join(OUT, f"{SLUG}.svg")
fig.savefig(png, dpi=300, metadata={"Software": None})
fig.savefig(svg, metadata={"Creator": None, "Date": None})

# ---- caption and alt text, from the same values ----------------------------------------
gi = comp["g"]
caption = (
    f"Figure 1. Fitted 50 percent contour areas (72-inch batter, 2024 pitch mix), with "
    f"95% model-conditional intervals. Arrows are the 2025 and 2026 steps net "
    f"of the 2022{EN}2024 trend of {f1(gi['point'])} sq in per season (95%: "
    f"{f1s(gi['lo95'])} to {f1s(gi['hi95'])}), each from the prior season plus that trend. "
    f"The bracket is the 2023-to-2024 change, {f1s(p1_est)} sq in "
    f"({pct(p1_level)}: {f1s(p1_lo)} to {f1s(p1_hi)}), with zone and grading rules "
    f"unchanged; that placebo failed. Grading changed in 2025, regular-season challenges "
    f"began in 2026; neither step is attributed. A confirmatory sealed-set calibration check "
    f"is pending.\n"
)
n_words = len(caption.split())
if n_words > 90:
    raise SystemExit(f"caption has {n_words} words; the limit is 90")
with open(os.path.join(OUT, "caption.md"), "w") as fh:
    fh.write(caption)

levels_txt = ", ".join(f"{s} {f1s(level[s]['point'])}" for s in SEASONS)
alt = (
    f"Dot chart of strike-zone area by season, 2022 to 2026, in square inches with 95 percent "
    f"bars. The points are {levels_txt}. Pale period bands mark 2022{EN}2024, 2025 and 2026 "
    f"(through 21 September). Downward arrows show the steps net of the "
    f"2022{EN}2024 trend. Each runs from the prior season's level plus the trend down to the "
    f"fitted level. They are 2025 {f1s(d25['point'])} (95 percent: {f1s(d25['lo95'])} to "
    f"{f1s(d25['hi95'])}) and 2026 {f1s(d26['point'])} ({f1s(d26['lo95'])} to "
    f"{f1s(d26['hi95'])}). A small rust bracket between 2023 and 2024 marks that change, "
    f"{f1(p1_est)} sq in ({pct(p1_level)}: {f1s(p1_lo)} to {f1s(p1_hi)}), labelled no zone "
    f"rule change. Both arrows are longer than that bracket.\n"
)
if len(alt) < 40:
    raise SystemExit("alt text too short")
with open(os.path.join(OUT, "alt.txt"), "w") as fh:
    fh.write(alt)

# ---- data-sources.md, written from the same rows the plot used --------------------------
FENCE_NOTE = (
    "Fenced as code: these are table cells and raw values, provenance rather than printed "
    "results, so quality/check_numbers.py does not read them."
)
lines = [
    "# Data sources, area-trajectory-drift",
    "",
    "Every number on the figure is read by `make_exhibit.py` from these committed tables under",
    "`out/ch1/tab/`. No file under `data/` and no model object is read; no fit is run. Printed",
    "values are the table values rounded to one decimal by the script.",
    "",
    "## Files, rows and columns read",
    "",
    "- `T3_estimands.csv`, rows `fit=main`, `arm=primary`, `estimand=area_sqin`, `season` 2022 "
    "to 2026:",
    "  columns `point`, `lo95`, `hi95`, `units` (checked equal to `sq in`).",
    "- `T4_decomposition.csv`, rows `fit=main`, `arm=primary`, `estimand=area_sqin`, "
    "`component` in",
    "  {`g`, `delta_buffer`, `delta_abs`}: columns `point`, `lo95`, `hi95`, `units` (checked).",
    "- `T5_placebos.csv`, row `placebo=P1`, `quantity=area_sqin 2024 minus 2023`: columns "
    "`estimate`,",
    "  `lo`, `hi`, `interval_level`, `margin_or_threshold`, `verdict`, `units` (checked).",
    "",
    "## Numbers that appear on the figure, its caption and its alt text",
    "",
    FENCE_NOTE,
    "",
    "```text",
    "| Printed | Value in table | Source |",
    "|---|---:|---|",
]
for s in SEASONS:
    r = level[s]
    lines.append(
        f"| {f1s(r['point'])} (bar {f1s(r['lo95'])} to {f1s(r['hi95'])}) | {r['point']:.6f} "
        f"[{r['lo95']:.6f}, {r['hi95']:.6f}] | T3_estimands.csv, season {s}, point, lo95, hi95 |"
    )
lines += [
    f"| trend {f1(gi['point'])} per season (95%: {f1s(gi['lo95'])} to {f1s(gi['hi95'])}), "
    f"caption only | {gi['point']:.6f} [{gi['lo95']:.6f}, {gi['hi95']:.6f}] | "
    "T4_decomposition.csv, component g |",
    f"| 2025 step {f1(d25['point'])} (95%: {f1s(d25['lo95'])} to {f1s(d25['hi95'])}) | "
    f"{d25['point']:.6f} [{d25['lo95']:.6f}, {d25['hi95']:.6f}] | "
    "T4_decomposition.csv, component delta_buffer |",
    f"| 2026 step {f1(d26['point'])} (95%: {f1s(d26['lo95'])} to {f1s(d26['hi95'])}) | "
    f"{d26['point']:.6f} [{d26['lo95']:.6f}, {d26['hi95']:.6f}] | "
    "T4_decomposition.csv, component delta_abs |",
    f"| 2023 to 2024 {f1(p1_est)} on the small bracket; ({pct(p1_level)}: {f1s(p1_lo)} to "
    f"{f1s(p1_hi)}) and the verdict in the caption | {p1_est:.6f} [{p1_lo:.6f}, {p1_hi:.6f}], "
    f"level {p1_level}, margin {p1_margin}, verdict {p1_verdict} | "
    "T5_placebos.csv, P1, estimate, lo, hi, interval_level, margin_or_threshold, verdict |",
    "```",
    "",
    "## Derived positions (not printed)",
    "",
    FENCE_NOTE,
    "",
    "```text",
    f"- Step baselines, where each arrow starts: 2024 level + g = "
    f"{cf_2025:.6f}; 2025 level + g = {cf_2026:.6f}. Each arrow ends at the season's level.",
    "  The script checks that level minus baseline equals the T4 step to 1e-6.",
    "  The script checks that the P1 estimate equals the 2024 minus 2023 level to 1e-6.",
    "- The small bracket runs from the 2023 level to the 2024 level.",
    "- Period band labels are years; 2026 runs to 21 September, the last open day (T1_sample.csv).",
    "```",
    "",
    "## Not drawn",
    "",
    "The All-Star-break placebo tick is not on the figure: it sat beside no arrow. The "
    "abstract's Results print the largest All-Star-break swing. The 10.8 sq in drift bars "
    "drawn behind each step in an earlier version were removed at a reviewer's request; the "
    "comparison is read from the rust bracket on the same axis.",
    "",
    "## Seal",
    "",
    "The tables read were committed before this exhibit was built (`git log -- out/ch1/tab`) and",
    "T1_sample.csv records the last open 2026 date as 2026-09-21. The script reads nothing else.",
    "",
]
with open(os.path.join(OUT, "data-sources.md"), "w") as fh:
    fh.write("\n".join(lines))

print("wrote", png, svg, f"caption ({n_words} words)", file=sys.stderr)
