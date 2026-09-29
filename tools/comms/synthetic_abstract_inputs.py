"""The abstract dry run's inputs: an obviously synthetic set of result CSVs.

SOP W6.10 dry run, fleet phase 06. Before prereg-v1 no fit may touch 2025 or 2026
data, so the abstract machinery is proven on round numbers that no model produced.
Every file name carries SYNTHETIC, the ledger base is empty (no real entry is carried
into the synthetic ledger), and every value is a round number chosen by hand. There is
no randomness, so no seed is needed; two runs write the same bytes.

The CSVs follow the contracts the real steps write, so the same exporter reads them:
    out/tables/abstract_slots_ch1.SYNTHETIC.csv   W6.7: the Results slots it writes, no more
    out/ch1/tab/umpire_eb_summary.SYNTHETIC.csv   W6.8: one wide row
    out/ch1/tab/T4_decomposition.SYNTHETIC.csv    W3.16: component x quantity
    out/ch1/tab/T4_plane_component.SYNTHETIC.csv  W3.17: quantity, per edge
    out/ch1/tab/T1_sample.SYNTHETIC.csv           W3.5: T1's layout, rows P0, P1, Z_games, ...
    out/ch1/tab/T2_zone_gate.SYNTHETIC.csv        W3.8: T2's layout, rows overall, ...

The ledger base holds no real entry. It holds three decoys in the positions W6.3 and W6.4
keep theirs: a feed slot first, and W6.4's N_CALLED and N_GAMES last, with values that are
not P0's. The abstract must print P0's counts, and the export must leave the decoys first
and last, byte for byte (tests/unit/test_abstract_ledger.py checks the bytes).

    uv run --locked python tools/comms/synthetic_abstract_inputs.py --out DIR
    uv run --locked python tools/comms/synthetic_abstract_inputs.py --verify FILLED

--out writes DIR/in/..., DIR/numbers-base.SYNTHETIC.json and DIR/owner-calls.SYNTHETIC.json.
--verify is the dry run's recovery check: every slot of a filled main-variant abstract must
print its truth below, formatted here in Python, independently of the R exporter, and no
decoy may appear. Exit 0 recovered, 1 not.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TAG = "SYNTHETIC"
SRC = "SYNTHETIC, hand-set round number"

# slot, point, lo95, hi95, units. A negative area is a loss. A_PUB is a range only.
SLOTS = [
    ("D_BUF", -10.0, -15.0, -5.0, "sq in"),
    ("D_ABS", -20.0, -25.0, -15.0, "sq in"),
    ("D_PRE", -1.0, -2.0, 0.0, "sq in per season"),
    ("D_PLANE_TOP", -0.5, -0.6, -0.4, "in"),
    ("D_PLANE_BOT", -1.5, -1.6, -1.4, "in"),
    ("A_CORR", -30.0, -40.0, -20.0, "sq in"),
    ("A_PUB", None, -20.0, -10.0, "sq in"),
]
# The Methods counts: P0 and its games from T1 (W3.5), the scored challenges from T2 (W3.8).
COUNTS = {"N_CALLED": 1000000, "N_GAMES": 10000, "N_CHAL": 5000}
T1_HEAD = [
    "order",
    "block",
    "row_id",
    "rule",
    "unit",
    "y2022",
    "y2023",
    "y2024",
    "y2025",
    "y2026",
    "total",
    "expected",
    "note",
]
T1_ROWS = [  # row_id, unit, total; the seasons split each total in five equal parts
    ("S_all", "pitches", 3000000),
    ("C_called", "pitches", 1100000),
    ("P0", "pitches", COUNTS["N_CALLED"]),
    ("P1", "pitches", 800000),
    ("Z_games", "games", COUNTS["N_GAMES"]),
    ("U_umpires", "umpires", 100),
]
T2_HEAD = [
    "row_id",
    "population",
    "zone",
    "n",
    "n_agree",
    "n_disagree",
    "agreement_pct",
    "threshold_pct",
    "verdict",
    "benchmark_pct",
    "benchmark_n",
    "note",
]
T2_ROWS = [
    ("overall", COUNTS["N_CHAL"]),
    ("outside_band", 4000),
    ("arm_roster_offset_overall", 5000),
]
# Decoys: W6.3's feed slot first and W6.4's ABS-measured-cohort counts last, as in the
# real ledger. Their values differ from P0's, so printing one of them is caught.
DECOYS_FIRST = [("N_FEED_GAMES_2026", 2000, "W6.3")]
DECOYS_LAST = [("N_CALLED", 777777, "W6.4"), ("N_GAMES", 7777, "W6.4")]
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


def decoy(slot: str, value: int, step: str) -> dict:
    return {
        "slot": slot,
        "value": value,
        "units": "counts",
        "what": f"SYNTHETIC decoy for {step}",
        "source": "SYNTHETIC",
        "produced_by": step,
        "carried_by": step,
    }


def fmt(x: float, d: int) -> str:
    s = f"{x:,.{d}f}" if d == 0 else f"{x:.{d}f}"
    return s[1:] if s.startswith("-") and float(s.replace(",", "")) == 0 else s


def expected() -> dict:
    """The string each slot must print, from the truth above and abstract_slots.json."""
    with open(os.path.join(ROOT, "tools", "comms", "abstract_slots.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    truth = {s: (p, lo, hi, u) for s, p, lo, hi, u in SLOTS}
    for k in ("SD_UMP", "REL_UMP"):
        truth[k] = (UMPIRE[k], UMPIRE[k + "_lo95"], UMPIRE[k + "_hi95"], "")
    out = {k: fmt(v, 0) for k, v in COUNTS.items()}
    out["N_UMP"] = fmt(UMPIRE["N_UMP"], 0)
    for slot, (p, lo, hi, _) in truth.items():
        s = spec["slots"][slot]
        d = s.get("digits", spec["digits"].get(s["units"], 2))
        if s.get("orient") == "contraction":
            p, lo, hi = -p, -hi, -lo
        if s["kind"] == "range":
            out[slot] = f"{fmt(lo, d)} to {fmt(hi, d)}{s.get('suffix', '')}"
        else:
            out[slot] = f"{fmt(p, d)} (95% CI {fmt(lo, d)} to {fmt(hi, d)})"
    return out


def verify(filled: str) -> int:
    with open(filled, encoding="utf-8") as fh:
        text = fh.read()
    bad = [f"{k}: expected '{v}'" for k, v in expected().items() if v not in text]
    bad += [
        f"decoy {s} printed: {fmt(v, 0)}"
        for s, v, _ in DECOYS_FIRST + DECOYS_LAST
        if re.search(rf"(?<![0-9,.]){re.escape(fmt(v, 0))}(?![0-9,])", text)
    ]
    for b in bad:
        print(f"synthetic recovery FAIL: {b}")
    if not bad:
        n = len(expected())
        print(f"synthetic recovery: all {n} numeric slots print their truth, no decoy printed")
    return 1 if bad else 0


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out")
    g.add_argument("--verify")
    a = ap.parse_args(argv[1:])
    if a.verify:
        return verify(a.verify)
    out = a.out
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
    write_csv(
        os.path.join(out, "in", "out", "ch1", "tab", f"T1_sample.{TAG}.csv"),
        T1_HEAD,
        [
            [i + 1, "sample", r, SRC, u, *([n // 5] * 5), n, "", SRC]
            for i, (r, u, n) in enumerate(T1_ROWS)
        ],
    )
    write_csv(
        os.path.join(out, "in", "out", "ch1", "tab", f"T2_zone_gate.{TAG}.csv"),
        T2_HEAD,
        [[r, SRC, SRC, n, n, 0, 100, 99.75, "PASS", "", "", SRC] for r, n in T2_ROWS],
    )
    base = {
        "_what": "SYNTHETIC ledger base for the abstract dry run. No real entry; three decoys.",
        "entries": [decoy(*d) for d in DECOYS_FIRST] + [decoy(*d) for d in DECOYS_LAST],
    }
    with open(os.path.join(out, f"numbers-base.{TAG}.json"), "w", encoding="utf-8") as fh:
        json.dump(base, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(os.path.join(out, f"owner-calls.{TAG}.json"), "w", encoding="utf-8") as fh:
        json.dump({"CALL": CALL, "BREAK_YEAR": "YEAR-SYNTHETIC"}, fh, indent=2)
        fh.write("\n")
    print(
        f"synthetic_abstract_inputs: {len(SLOTS) + len(COUNTS) + 3} slots, 16 table cells and "
        f"{len(DECOYS_FIRST) + len(DECOYS_LAST)} decoys in {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
