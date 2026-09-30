#!/usr/bin/env python
"""Candidate exhibit `table-periods-descriptive`: a rebuilt Table 1 with period
labels, the 2024-to-2026 total and the failed pre-registered placebo as a row.

Reads ONLY committed tables under out/ (no model object, no new fit):
  out/ch1/tab/T4_decomposition.csv    fit=main, arm=primary; components g,
                                      delta_buffer, delta_abs, delta_total
  out/ch1/tab/T5_placebos.csv         placebo=P1, both quantities
  out/ch1/tab/T4_plane_component.csv  all four estimands
  out/tables/table1_data.csv          print_* columns, used only to assert that
                                      this script's rounding reproduces them

Writes, next to this script:
  table-periods-descriptive.png (300 dpi, 6.5 in wide), .svg,
  caption.md, alt.txt, data-sources.md (generated from the same reads).

Run from the repository root:
  uv run --locked python abstract/exhibits/table-periods-descriptive/build.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[3]  # /Users/hudsonpagni/sports-project
OUT = Path(__file__).resolve().parent
SLUG = "table-periods-descriptive"

T4 = ROOT / "out/ch1/tab/T4_decomposition.csv"
T5 = ROOT / "out/ch1/tab/T5_placebos.csv"
TP = ROOT / "out/ch1/tab/T4_plane_component.csv"
T1 = ROOT / "out/tables/table1_data.csv"

MINUS = "\u2212"  # typographic minus in the rendered image; ASCII '-' in the CSVs

# ----------------------------------------------------------------------------
# Reads. Every value that appears on the exhibit is appended to LEDGER with its
# file, row filter and column, and data-sources.md is written from LEDGER.
# ----------------------------------------------------------------------------
LEDGER: list[dict] = []
FILES_READ: dict[str, set] = {}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def pick(rows: list[dict], where: dict, path: Path) -> dict:
    hits = [r for r in rows if all(r[k] == v for k, v in where.items())]
    if len(hits) != 1:
        sys.exit(f"{path.relative_to(ROOT)}: filter {where} matched {len(hits)} rows, need 1")
    return hits[0]


def take(row: dict, cols: list[str], where: dict, path: Path) -> dict:
    """Pull columns from a row and record them in the ledger."""
    rel = str(path.relative_to(ROOT))
    FILES_READ.setdefault(rel, set()).update(cols)
    got = {c: row[c] for c in cols}
    LEDGER.append({"file": rel, "where": where, "cols": got})
    return got


t4 = read_csv(T4)
t5 = read_csv(T5)
tp = read_csv(TP)
t1 = read_csv(T1)

# Rounding rule: table1_data.csv prints inches to 2 decimals and sq in to 1.
# Percentage points are not in table1_data.csv; the abstract text quotes the
# shadow-band placebo as 1.54 (1.03 to 2.04), so pp is printed to 2 decimals.
DECIMALS = {
    "in": 2,
    "in per season": 2,
    "sq in": 1,
    "sq in per season": 1,
    "pct": 2,
    "pct per season": 2,
    "pp": 2,
}


def fmt(x: str | float, units: str) -> str:
    d = DECIMALS[units]
    s = f"{float(x):.{d}f}"
    if s.startswith("-") and float(s) == 0:  # never print "-0.0"
        s = s[1:]
    return s


# Assert the rounding rule reproduces every print_* cell in table1_data.csv.
for r in t1:
    FILES_READ.setdefault(str(T1.relative_to(ROOT)), set()).update(
        ["row", "col", "units", "point", "lo95", "hi95", "print_point", "print_lo95", "print_hi95"]
    )
    for raw, printed in (("point", "print_point"), ("lo95", "print_lo95"), ("hi95", "print_hi95")):
        got = fmt(r[raw], r["units"])
        if got != r[printed]:
            sys.exit(
                f"rounding rule disagrees with table1_data.csv {r['slot']} {raw}: "
                f"{got} vs {r[printed]}"
            )
LEDGER.append(
    {
        "file": str(T1.relative_to(ROOT)),
        "where": {"all 16 rows": "rounding check only, nothing printed"},
        "cols": {"print_point, print_lo95, print_hi95": "matched by this script's fmt()"},
    }
)

ESTIMANDS = ["top_in", "bot_in", "half_width_in", "area_sqin", "shadow_rate"]
COL_HEAD = {
    "top_in": "Top edge\n(in)",
    "bot_in": "Bottom edge\n(in)",
    "half_width_in": "Half-width\n(in)",
    "area_sqin": "Area\n(sq in)",
    "shadow_rate": "Shadow-band\nstrike rate (pp)",
}


def t4_cell(estimand: str, component: str) -> dict:
    where = {"fit": "main", "arm": "primary", "estimand": estimand, "component": component}
    row = pick(t4, where, T4)
    v = take(row, ["point", "lo95", "hi95", "units"], where, T4)
    return {
        "point": fmt(v["point"], v["units"]),
        "lo": fmt(v["lo95"], v["units"]),
        "hi": fmt(v["hi95"], v["units"]),
        "level": "95%",
        "raw": (float(v["point"]), float(v["lo95"]), float(v["hi95"])),
    }


def t5_cell(quantity: str) -> dict:
    where = {"placebo": "P1", "quantity": quantity}
    row = pick(t5, where, T5)
    v = take(
        row,
        ["estimate", "lo", "hi", "interval_level", "margin_or_threshold", "verdict", "units"],
        where,
        T5,
    )
    if v["verdict"] != "fail":
        sys.exit(f"T5 P1 {quantity}: verdict is {v['verdict']}, the row label says FAILED")
    level = f"{round(float(v['interval_level']) * 100):d}%"
    return {
        "point": fmt(v["estimate"], v["units"]),
        "lo": fmt(v["lo"], v["units"]),
        "hi": fmt(v["hi"], v["units"]),
        "level": level,
        "margin": v["margin_or_threshold"],
        "units": v["units"],
        "raw": (float(v["estimate"]), float(v["lo"]), float(v["hi"])),
    }


def tp_cell(estimand: str) -> dict:
    where = {"estimand": estimand}
    row = pick(tp, where, TP)
    v = take(row, ["point", "lo95", "hi95", "units"], where, TP)
    return {
        "point": fmt(v["point"], v["units"]),
        "lo": fmt(v["lo95"], v["units"]),
        "hi": fmt(v["hi95"], v["units"]),
        "level": "95%",
        "raw": (float(v["point"]), float(v["lo95"]), float(v["hi95"])),
    }


# Placebo row: pre-registered on area and shadow-band rate only.
p1_area = t5_cell("area_sqin 2024 minus 2023")
p1_shadow = t5_cell("shadow_rate 2024 minus 2023")
if p1_area["level"] != p1_shadow["level"]:
    sys.exit("P1 rows carry different interval levels")
P1_LEVEL = p1_area["level"]
p1_margin_area = fmt(p1_area["margin"], "sq in").rstrip("0").rstrip(".")
p1_margin_shadow = fmt(p1_shadow["margin"], "pp").rstrip("0").rstrip(".")

ROWS = [
    {"label": ["2022-2024 trend, per season"], "cells": {e: t4_cell(e, "g") for e in ESTIMANDS}},
    {
        "label": [
            "2023 to 2024, no rule change",
            f"(pre-registered placebo, {P1_LEVEL} interval;",
            f"margins ±{p1_margin_area} sq in and ±{p1_margin_shadow} pp): FAILED",
        ],
        "cells": {"area_sqin": p1_area, "shadow_rate": p1_shadow},
        "shade": True,
    },
    {
        "label": ["2025 step, net of trend", "(grading buffer 0.75 in)"],
        "cells": {e: t4_cell(e, "delta_buffer") for e in ESTIMANDS},
    },
    {
        "label": ["2026 step, net of trend", "(ABS challenges)"],
        "cells": {e: t4_cell(e, "delta_abs") for e in ESTIMANDS},
    },
    {"label": ["2024 to 2026, total"], "cells": {e: t4_cell(e, "delta_total") for e in ESTIMANDS}},
    {
        "label": ["Plate-plane component, 2025", "read at mid-plate minus at the front"],
        "cells": {e: tp_cell(e) for e in ESTIMANDS if e != "shadow_rate"},
    },
]

# Sign-convention sentence reused from abstract/table1.md line 1.
SIGN_SENTENCE = "A positive value moves an edge up or outward, or enlarges the area."
FOOTNOTE = (
    f"Cells are point [95% interval] from coefficient draws of the fitted model; the placebo row "
    f"prints its pre-registered {P1_LEVEL} interval. {SIGN_SENTENCE} Because a season pair with "
    "no rule change moved beyond its margin, no step is attributed to its rule; the 2025 and 2026 "
    "labels name the period only. Top-edge intervals read slightly too narrow. Dashes: not "
    "estimated for that row."
)

# ----------------------------------------------------------------------------
# Layout, in inches from the top-left of a 6.5 in wide page strip.
# ----------------------------------------------------------------------------
W = 6.5
LEFT, RIGHT = 0.06, 6.44
LABEL_W = 2.20
COL_L = LEFT + LABEL_W
# relative column widths; the shadow-band column carries the widest intervals
_REL = [0.80, 0.80, 0.80, 0.84, 1.00]
_scale = (RIGHT - COL_L) / sum(_REL)
COL_X0 = [COL_L + sum(_REL[:i]) * _scale for i in range(len(_REL))]
COL_WS = [w * _scale for w in _REL]
FS_HEAD, FS_LABEL, FS_SUB, FS_POINT, FS_INT, FS_FOOT = 9.0, 9.0, 8.0, 9.0, 8.0, 8.0
LINE = 0.152  # in, line pitch at 9 pt
INK, INK2, RULE, SHADE = "#000000", "#4d4d4d", "#000000", "#ececec"
FONT = ["Helvetica", "Arial", "DejaVu Sans"]

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": FONT,
        "svg.fonttype": "none",
        "text.color": INK,
    }
)

hdr_h = 0.44
row_h = [max(2, len(r["label"])) * LINE + 0.14 for r in ROWS]
foot_lines = 4
foot_h = foot_lines * 0.135 + 0.10
H = 0.06 + hdr_h + sum(row_h) + foot_h + 0.05

fig = plt.figure(figsize=(W, H), dpi=300)
fig.patch.set_facecolor("white")
tr = fig.dpi_scale_trans


def Y(y_from_top: float) -> float:
    return H - y_from_top


def text(x, y, s, **kw):
    kw.setdefault("transform", tr)
    kw.setdefault("va", "center")
    return fig.text(x, Y(y), s, **kw)


def hline(y, x0=LEFT, x1=RIGHT, lw=0.8, color=RULE):
    fig.add_artist(
        Line2D([x0, x1], [Y(y), Y(y)], transform=tr, lw=lw, color=color, solid_capstyle="butt")
    )


def num(s: str) -> str:
    return s.replace("-", MINUS)


# Header
y = 0.06
hline(y, lw=1.0)
yc = y + hdr_h / 2
text(
    LEFT,
    yc,
    "Change in the fitted\n50 percent contour",
    fontsize=FS_HEAD,
    ha="left",
    weight="bold",
    linespacing=1.15,
)
for i, e in enumerate(ESTIMANDS):
    cx = COL_X0[i] + 0.5 * COL_WS[i]
    text(cx, yc, COL_HEAD[e], fontsize=FS_HEAD, ha="center", weight="bold", linespacing=1.15)
y += hdr_h
hline(y, lw=0.6)

# Body
for r, h in zip(ROWS, row_h, strict=True):
    if r.get("shade"):
        fig.add_artist(
            Rectangle(
                (LEFT, Y(y + h)),
                RIGHT - LEFT,
                h,
                transform=tr,
                facecolor=SHADE,
                edgecolor="none",
                zorder=0,
            )
        )
    # label lines, top-aligned within the row
    n = len(r["label"])
    block = n * LINE
    y0 = y + (h - block) / 2 + LINE / 2
    for k, line in enumerate(r["label"]):
        fs = FS_LABEL if k == 0 else FS_SUB
        col = INK if k == 0 else INK2
        if line.endswith("FAILED"):
            # print the verdict in bold ink at the end of the line
            stem = line[: -len("FAILED")]
            t = text(LEFT, y0 + k * LINE, stem, fontsize=fs, ha="left", color=col)
            fig.canvas.draw()
            bb = t.get_window_extent().transformed(tr.inverted())
            text(bb.x1, y0 + k * LINE, "FAILED", fontsize=fs, ha="left", color=INK, weight="bold")
        else:
            text(LEFT, y0 + k * LINE, line, fontsize=fs, ha="left", color=col)
    # numeric cells: point decimal-aligned on an anchor, interval centred below
    three = any(c["level"] != "95%" for c in r["cells"].values())
    yp = y + h / 2 - (1.0 if three else 0.5) * LINE + 0.01
    yi = y + h / 2 + (0.0 if three else 0.5) * LINE - 0.01
    yl = y + h / 2 + 1.0 * LINE - 0.01
    for i, e in enumerate(ESTIMANDS):
        cx = COL_X0[i] + 0.5 * COL_WS[i]
        anchor = COL_X0[i] + 0.62 * COL_WS[i]
        c = r["cells"].get(e)
        if c is None:
            text(cx, y + h / 2, "\u2013", fontsize=FS_POINT, ha="center", color=INK2)
            continue
        p = num(c["point"])
        ip, fp = p.split(".")
        text(anchor, yp, ip + ".", fontsize=FS_POINT, ha="right", color=INK)
        text(anchor, yp, fp, fontsize=FS_POINT, ha="left", color=INK)
        text(cx, yi, f"[{num(c['lo'])}, {num(c['hi'])}]", fontsize=FS_INT, ha="center", color=INK2)
        if c["level"] != "95%":
            text(cx, yl, f"{c['level']} interval", fontsize=FS_INT, ha="center", color=INK2)
    y += h
    hline(y, lw=0.4, color="#9a9a9a")
# bottom rule over the last light one
hline(y, lw=1.0)

# Footnote, wrapped to the strip width
import textwrap  # noqa: E402

wrapped = textwrap.wrap(FOOTNOTE, width=118, break_on_hyphens=False)
if len(wrapped) > foot_lines:
    sys.exit(f"footnote needs {len(wrapped)} lines, layout allows {foot_lines}")
y += 0.10
for k, line in enumerate(wrapped):
    text(LEFT, y + k * 0.135 + 0.06, line, fontsize=FS_FOOT, ha="left", color=INK2)

# ----------------------------------------------------------------------------
# Blind / descriptive checks on every string that will be drawn.
# ----------------------------------------------------------------------------
FORBIDDEN = [
    "effect",
    "impact",
    "caused",
    "because of the",
    "pagni",
    "hudson",
    "github",
    "abs-umpires",
    "http",
    "@",
    "umpire_hp_id",
    "university",
]
drawn = [t.get_text().lower() for t in fig.texts]
for s in drawn:
    for bad in FORBIDDEN:
        if bad in s:
            sys.exit(f"forbidden token {bad!r} in drawn text: {s!r}")

png = OUT / f"{SLUG}.png"
svg = OUT / f"{SLUG}.svg"
fig.savefig(png, dpi=300, facecolor="white")
fig.savefig(svg, facecolor="white")

# ----------------------------------------------------------------------------
# Caption, alt text and data-sources.md, generated from the same values.
# ----------------------------------------------------------------------------
area = {
    name: r["cells"]["area_sqin"]
    for name, r in zip(["trend", "placebo", "s2025", "s2026", "total", "plane"], ROWS, strict=True)
}

caption = (
    "Table 1. Measured changes in the fitted 50 percent strike contour, 72-inch batter, "
    "2024 pitch mix, read at mid-plate. Cells are point [95% interval]; the placebo row uses "
    f"its pre-registered {P1_LEVEL} interval. The 2023-to-2024 change, with no rule change, "
    "exceeded its margin, so the 2025 and 2026 steps are labelled by period and not "
    "attributed to a rule."
)
n_words = len(caption.split())
if n_words >= 60:
    sys.exit(f"caption has {n_words} words, must be under 60")
if "?" in caption or "?" in FOOTNOTE:
    sys.exit("no question marks allowed")
(OUT / "caption.md").write_text(caption + "\n")


def span(c, ascii_=True):
    return f"{c['point']} [{c['lo']}, {c['hi']}]"


alt = (
    "Table with six rows and five numeric columns: top edge and bottom edge and half-width "
    "in inches, area in square inches, and shadow-band strike rate in percentage points, "
    "each cell a point estimate with a 95 percent interval. Rows: the 2022-2024 trend per "
    f"season (area {span(area['trend'])} sq in); the 2023-to-2024 change with no rule "
    f"change, the pre-registered placebo with a {P1_LEVEL} interval, area "
    f"{span(area['placebo'])} sq in against a margin of {p1_margin_area} and shadow-band "
    f"rate {span(p1_shadow)} pp against {p1_margin_shadow}, marked FAILED; the 2025 step "
    f"net of trend, area {span(area['s2025'])} sq in; the 2026 step net of trend, area "
    f"{span(area['s2026'])} sq in; the 2024-to-2026 total, area {span(area['total'])} sq in; "
    "and the plate-plane component, 2025 read at mid-plate minus at the front, area "
    f"{span(area['plane'])} sq in. A footnote states that no step is attributed to its rule "
    "and that top-edge intervals read slightly too narrow."
)
assert len(alt) >= 40
(OUT / "alt.txt").write_text(alt + "\n")

lines = [
    f"# Data sources for `{SLUG}`",
    "",
    "Generated by build.py from the reads it performed; nothing here is typed by hand.",
    "No model object was loaded and no fit was run. All files are committed tables under out/.",
    "",
    "## Files and columns read",
    "",
]
for f, cols in sorted(FILES_READ.items()):
    lines.append(f"- `{f}`: columns {', '.join(sorted(cols))}")
lines += [
    "",
    "## Every number that appears on the exhibit",
    "",
    "Fenced as code: these are table cells and raw values, provenance rather than printed "
    "results, so quality/check_numbers.py does not read them.",
    "",
    "```text",
    "Rounding: inches to 2 decimals, sq in to 1 decimal (the `print_*` rule of "
    "`out/tables/table1_data.csv`, asserted against all 16 of its rows); percentage points to 2 "
    "decimals (as the abstract text quotes them). The image prints a typographic minus (U+2212) "
    "where the CSV has `-`.",
    "",
    "| Row | Column | Printed | Raw point, lo, hi | Interval | File | Row filter |",
    "|---|---|---|---|---|---|---|",
]
for r in ROWS:
    for e in ESTIMANDS:
        c = r["cells"].get(e)
        if c is None:
            lines.append(
                f"| {r['label'][0]} | {COL_HEAD[e].replace(chr(10), ' ')} "
                "| dash (not estimated for that row) | | | | |"
            )
            continue
        entry = next(
            L
            for L in reversed(LEDGER)
            if L["cols"].get("point", L["cols"].get("estimate")) == str(c["raw"][0])
            and (L["where"].get("estimand") == e or e in L["where"].get("quantity", ""))
        )
        raw = ", ".join(f"{v:.6g}" for v in c["raw"])
        where = "; ".join(f"{k}={v}" for k, v in entry["where"].items())
        lines.append(
            f"| {r['label'][0]} | {COL_HEAD[e].replace(chr(10), ' ')} | {span(c)} | {raw} "
            f"| {c['level']} | `{entry['file']}` | {where} |"
        )
lines += [
    "```",
    "",
    "## Other values printed",
    "",
    "Fenced as code: these are table cells and raw values, provenance rather than printed "
    "results, so quality/check_numbers.py does not read them.",
    "",
    "```text",
    f"- Placebo margins in the row label: {p1_margin_area} sq in and {p1_margin_shadow} pp, from "
    "`out/ch1/tab/T5_placebos.csv` column `margin_or_threshold` (P1 rows); verdict `fail` "
    "from column `verdict`.",
    f"- Interval level {P1_LEVEL} for the placebo row, from column `interval_level` (0.9).",
    "- Column headings and units from the `units` columns of the same rows "
    "(in, sq in, pct printed as pp).",
    "- Period labels (2022-2024; 2025, grading buffer 0.75 in; 2026, ABS challenges) are the "
    "pre-registered period names. The sign-convention sentence in the footnote is reused "
    "from line 1 of the `abstract/table1.md` that `tools/comms/build_exhibits.R` writes, "
    "and the caption's batter height and reference mix are from the same line.",
    "```",
    "",
    "## Full ledger of reads",
    "",
    "Fenced as code: these are table cells and raw values, provenance rather than printed "
    "results, so quality/check_numbers.py does not read them.",
    "",
    "```text",
]
for L in LEDGER:
    where = "; ".join(f"{k}={v}" for k, v in L["where"].items())
    cols = "; ".join(f"{k}={v}" for k, v in L["cols"].items())
    lines.append(f"- `{L['file']}` [{where}]: {cols}")
lines.append("```")
(OUT / "data-sources.md").write_text("\n".join(lines) + "\n")

print(
    f"wrote {png.relative_to(ROOT)} ({W} x {H:.2f} in at 300 dpi), {svg.name}, "
    f"caption ({n_words} words), alt, data-sources"
)
