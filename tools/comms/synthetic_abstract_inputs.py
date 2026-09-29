"""The abstract dry run's inputs: an obviously synthetic set of result CSVs.

SOP W6.10 dry run, fleet phase 06. Before prereg-v1 no fit may touch 2025 or 2026
data, so the abstract machinery is proven on round numbers that no model produced.
Every file name carries SYNTHETIC, the ledger base is empty (no real entry is carried
into the synthetic ledger), and every value is a round number chosen by hand. There is
no randomness, so no seed is needed; two runs write the same bytes.

The CSVs follow the contracts the real steps write, so the same exporter reads them:
    out/tables/abstract_slots_ch1.SYNTHETIC.csv   W6.7: slot, point, lo95, hi95, units, ...
    out/ch1/tab/umpire_eb_summary.SYNTHETIC.csv   W6.8: one wide row
    out/ch1/tab/T4_decomposition.SYNTHETIC.csv    W3.16: component x quantity
    out/ch1/tab/T4_plane_component.SYNTHETIC.csv  W3.17: quantity, per edge

    uv run --locked python tools/comms/synthetic_abstract_inputs.py --out DIR

Writes DIR/in/..., DIR/numbers-base.SYNTHETIC.json and DIR/owner-calls.SYNTHETIC.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

TAG = "SYNTHETIC"
SRC = "SYNTHETIC, hand-set round number"

# slot, point, lo95, hi95, units. A negative area is a loss. A_PUB is a range only.
SLOTS = [
    ("N_CALLED", 1000000, None, None, "counts"),
    ("N_GAMES", 10000, None, None, "counts"),
    ("N_CHAL", 5000, None, None, "counts"),
    ("D_BUF", -10.0, -15.0, -5.0, "sq in"),
    ("D_ABS", -20.0, -25.0, -15.0, "sq in"),
    ("D_PRE", -1.0, -2.0, 0.0, "sq in per season"),
    ("D_PLANE_TOP", -0.5, -0.6, -0.4, "in"),
    ("D_PLANE_BOT", -1.5, -1.6, -1.4, "in"),
    ("A_CORR", -30.0, -40.0, -20.0, "sq in"),
    ("A_PUB", None, -20.0, -10.0, "sq in"),
]
UMPIRE = {
    "SD_UMP": 0.2,
    "SD_UMP_lo95": 0.1,
    "SD_UMP_hi95": 0.3,
    "REL_UMP": 0.5,
    "REL_UMP_lo95": 0.4,
    "REL_UMP_hi95": 0.6,
    "REL_UMP_estimator": "split-half, Spearman-Brown (SYNTHETIC)",
    "N_UMP": 100,
}
QUANT = ("top_in", "bot_in", "half_width_in", "area_sqin")
T4 = {  # component: (point, lo95, hi95) per quantity, in QUANT order
    "g": [(-0.1, -0.2, 0.0), (0.1, 0.0, 0.2), (-0.1, -0.2, 0.0), (-1.0, -2.0, 0.0)],
    "delta_buffer": [(-0.5, -0.7, -0.3), (0.5, 0.3, 0.7), (-0.2, -0.3, -0.1), (-10.0, -15.0, -5.0)],
    "delta_abs": [(-1.0, -1.2, -0.8), (1.0, 0.8, 1.2), (-0.5, -0.6, -0.4), (-20.0, -25.0, -15.0)],
}
PLANE = [(-0.5, -0.6, -0.4), (-1.5, -1.6, -1.4), (0.0, -0.1, 0.1), (10.0, 5.0, 15.0)]
# 25 words, the reserve fill_slots holds for CALL, and one limitation word for WR-18.
CALL = (
    "SYNTHETIC CALL, not a result: this sentence stands in for the owner's wording, "
    "and its limitation is that no real number exists before review R1."
)


def write_csv(path: str, header, rows) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    out = ap.parse_args(argv[1:]).out
    blank = lambda v: "" if v is None else v  # noqa: E731
    write_csv(
        os.path.join(out, "in", "out", "tables", f"abstract_slots_ch1.{TAG}.csv"),
        ["slot", "point", "lo95", "hi95", "units", "estimator", "source_csv", "source_row"],
        [
            [s, blank(p), blank(lo), blank(hi), u, SRC, SRC, i + 1]
            for i, (s, p, lo, hi, u) in enumerate(SLOTS)
        ],
    )
    write_csv(
        os.path.join(out, "in", "out", "ch1", "tab", f"umpire_eb_summary.{TAG}.csv"),
        list(UMPIRE),
        [list(UMPIRE.values())],
    )
    write_csv(
        os.path.join(out, "in", "out", "ch1", "tab", f"T4_decomposition.{TAG}.csv"),
        ["component", "quantity", "point", "lo95", "hi95", "identity_residual"],
        [[c, q, *v, 0] for c, vals in T4.items() for q, v in zip(QUANT, vals, strict=True)],
    )
    write_csv(
        os.path.join(out, "in", "out", "ch1", "tab", f"T4_plane_component.{TAG}.csv"),
        ["quantity", "point", "lo95", "hi95"],
        [[q, *v] for q, v in zip(QUANT, PLANE, strict=True)],
    )
    base = {
        "_what": "SYNTHETIC ledger base for the abstract dry run. It holds no entry.",
        "entries": [],
    }
    with open(os.path.join(out, f"numbers-base.{TAG}.json"), "w", encoding="utf-8") as fh:
        json.dump(base, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(out, f"owner-calls.{TAG}.json"), "w", encoding="utf-8") as fh:
        json.dump({"CALL": CALL, "BREAK_YEAR": "YEAR-SYNTHETIC"}, fh, indent=2)
        fh.write("\n")
    print(f"synthetic_abstract_inputs: {len(SLOTS) + 3} slots and 16 table cells in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
