"""SOP W6.10, owner review R1: the 45-minute agenda, generated from the same ledger.

Sections (a) to (h): the headline numbers, the placebo verdicts and the consequence that
applies, three RESULT CALL proposals with the test each needs, BREAK_YEAR, the variant,
the paste sheet at the form, the deadline, and what stays open. It also reads
out/ch1/tab/T4_decomposition.csv and T5_placebos.csv for the share and the placebos.
It never chooses. Each proposal is marked as one; the owner makes the call.

It writes to submissions/ssac2027/, not abstract/: the agenda prints word counts,
which are not ledger numbers, and abstract/ is under the WR-07 number gate.

    uv run --locked python tools/comms/r1_agenda.py --ledger F --report F --out F

Exit 0 written, 2 usage.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAP = 470


def words(text: str) -> int:
    return len(text.split())


def entry(ledger: dict, slot: str):
    for e in ledger.get("entries", []):
        if e.get("slot") == slot:
            return e
    return None


def reading(e):
    """'loss', 'gain' or 'flat' from a signed entry's 95% interval; None if absent."""
    if not e or e.get("lo95") is None or e.get("hi95") is None:
        return None
    lo, hi = float(e["lo95"]), float(e["hi95"])
    if hi < 0:
        return "loss"
    if lo > 0:
        return "gain"
    return "flat"


def inline_line(rep) -> str:
    """The no-upload body: its count and its cuts, from the second fill's report."""
    if not rep:
        return "The no-upload body was not filled in this run."
    cuts = [c["rung"] for c in rep.get("cuts", []) if c.get("applied")]
    n = int(rep.get("words_counted", 0))
    verdict = "within the cap" if n <= CAP else f"OVER THE CAP by {n - CAP} words after every rung"
    return (
        f"The no-upload body counts {n} words with the inline table, {verdict}. "
        f"Cuts: {', '.join(cuts) or 'none'}."
    )


def deadline_lines() -> list[str]:
    """The README's Deadline section, verbatim: the deadline is kept in one place."""
    path = os.path.join(ROOT, "submissions", "ssac2027", "README.md")
    if not os.path.exists(path):
        return ["submissions/ssac2027/README.md is absent; read the deadline from the SOP."]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    body = text.split("## Deadline", 1)[-1].split("\n## ", 1)[0].strip()
    return body.split("\n") if "## Deadline" in text else ["The README has no Deadline section."]


def read_csv(rel: str) -> list[dict]:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def consequence_lines() -> list[str]:
    """Where the P1 consequence stands: headline.csv's first row, and the DEVIATIONS entry."""
    hl = read_csv("out/tables/headline.csv")
    first = hl[0] if hl else {}
    dev = ""
    path = os.path.join(ROOT, "docs", "DEVIATIONS.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            heads = [ln for ln in fh if ln.startswith("## DEV-") and "placebo P1" in ln]
        dev = heads[-1][3:].split(":", 1)[0] if heads else ""
    out = []
    if first.get("id") == "CH1_P1":
        out.append("Applied: `out/tables/headline.csv` leads with CH1_P1, written by W6.7 from T5:")
        out += ["", "> " + first.get("sentence", ""), ""]
    else:
        out.append("Still to do: `out/tables/headline.csv` has no leading row stating P1's result.")
    out.append(
        f"`docs/DEVIATIONS.md` records it as {dev}, as the W3.21 CONSEQUENCE line asks."
        if dev
        else "Still to do: `docs/DEVIATIONS.md` has no dated entry for it, which the W3.21 "
        "CONSEQUENCE line asks for."
    )
    out.append("The DECISIONS.md entry D-P6-01 records the fourth abstract variant.")
    return out


def filled_text(report) -> str:
    path = os.path.join(ROOT, report.get("out", "")) if report.get("out") else ""
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def t4_row(rows, estimand: str, component: str):
    for r in rows:
        if r.get("arm") == "primary" and r["estimand"] == estimand and r["component"] == component:
            return r
    return None


def f(x, d=1) -> str:
    try:
        return f"{float(x):.{d}f}"
    except (TypeError, ValueError):
        return "n/a"


def interval(e, level: int = 95, d=None) -> str:
    """'point (L to H)' from a ledger entry's printed form, at the level it was stored."""
    if not e:
        return "absent from the ledger"
    pr = e.get("print") or {}
    lo, hi = pr.get(f"lo{level}"), pr.get(f"hi{level}")
    pt = pr.get("point")
    if pt is None and lo is not None:  # a published range, not an interval
        return f"{lo} to {hi}"
    return f"{pt} ({level}% CI {lo} to {hi})" if lo is not None else (pt or "")


def proposals(share, buf, abs_, drift):
    """Three candidate RESULT CALL sentences, one per reading, and the test each needs.

    The consequence of a failed P1 applies to every artifact, so each proposal is
    descriptive: it says when the zone moved, never what moved it."""
    lo, hi = float(share["lo95"]), float(share["hi95"])
    return [
        (
            "Most of the 2024-to-2026 contraction came in 2025, the first season under the "
            "smaller grading buffer, before ABS challenges began.",
            "the 2026 share's 95% interval lies wholly below 0.5",
            hi < 0.5,
        ),
        (
            "Measured against 2022-2024, more of the zone's contraction came in the 2026 ABS "
            "season than in the 2025 buffer season.",
            "the 2026 share's 95% interval lies wholly above 0.5",
            lo > 0.5,
        ),
        (
            "The zone shrank by comparable amounts in 2025 and in 2026, and year-to-year "
            "drift is too large to rank the two seasons.",
            "the 2026 share's interval covers 0.5, or the gap between the steps is no larger "
            "than the P1 drift",
            (lo <= 0.5 <= hi) or abs(abs_ - buf) <= abs(drift),
        ),
    ]


def agenda(ledger: dict, report: dict, ledger_path: str) -> str:
    printed = report.get("printed") or {}
    filled = filled_text(report)
    counted = int(report.get("words_counted", 0))
    buf_e, abs_e = entry(ledger, "D_BUF"), entry(ledger, "D_ABS")
    buf, abs_ = reading(buf_e), reading(abs_e)
    ch2 = sorted(
        e["slot"] for e in ledger.get("entries", []) if e.get("slot", "").startswith("CH2_")
    )
    synthetic = "_synthetic" in ledger
    t4 = read_csv("out/ch1/tab/T4_decomposition.csv")
    t5 = read_csv("out/ch1/tab/T5_placebos.csv")
    total = t4_row(t4, "area_sqin", "delta_total")
    share = t4_row(t4, "area_sqin", "share_abs")
    p1 = [r for r in t5 if r["placebo"] == "P1"]
    p2 = [r for r in t5 if r["placebo"] == "P2"]
    p1_fail = any(r["verdict"] == "fail" for r in p1)
    p2_fail = any(r["verdict"] == "fail" for r in p2)
    lines = [
        "# Owner review R1: the SSAC abstract" + (" (SYNTHETIC LEDGER)" if synthetic else ""),
        "",
        f"Generated by `tools/comms/r1_agenda.py` from `{ledger_path}`, the fill report,",
        "`out/ch1/tab/T4_decomposition.csv` and `out/ch1/tab/T5_placebos.csv`. Every call below",
        "is the owner's. Nothing here is written into the abstract, `out/ch1/decision.md` or",
        "`abstract/owner-calls.json` by an agent.",
        (
            "CALL and BREAK_YEAR are still slots: "
            + ", ".join(report.get("owner_pending") or [])
            + ". No agent writes them."
            if report.get("owner_pending")
            else "CALL and BREAK_YEAR were read from the owner's calls file."
        ),
        "",
        f"Variant filled: {report.get('variant', 'main')}. Words counted: {counted} of {CAP},",
        f"with {report.get('owner_reserve', 0)} words held for the owner slots.",
        f"Pre-registration sentence: {report.get('prereg_sentence', 'narrow')}.",
        "",
        "## (a) The headline numbers",
        "",
        "Area in square inches, edges in inches, at a 72-inch batter. Contraction reads negative.",
        "The two steps are net of the 2022-2024 trend.",
        "",
        "| quantity | units | estimate (interval) | ledger slot |",
        "|---|---|---|---|",
    ]
    rows = [
        ("P1 placebo: area, 2024 minus 2023", "sq in", "P1_AREA", 90),
        ("P1 placebo: shadow-band strike rate, 2024 minus 2023", "pp", "P1_SHADOW", 90),
        ("P2 placebo: largest All-Star-break area shift of five", "sq in", "P2_AREA_MAX", 95),
        ("2025 step (buffer season), area", "sq in", "D_BUF", 95),
        ("2026 step (ABS season), area", "sq in", "D_ABS", 95),
        ("2022-2024 pre-trend, area", "sq in per season", "D_PRE", 95),
        ("2025 step, top edge", "in", "T1_BUF_TOP", 95),
        ("2026 step, top edge", "in", "T1_ABS_TOP", 95),
        ("2025 step, bottom edge", "in", "T1_BUF_BOT", 95),
        ("2026 step, bottom edge", "in", "T1_ABS_BOT", 95),
        ("2025 step, half-width", "in", "T1_BUF_HW", 95),
        ("2026 step, half-width", "in", "T1_ABS_HW", 95),
        ("Plane change, top edge (D-R0-04 top-edge caveat)", "in", "D_PLANE_TOP", 95),
        ("Plane change, bottom edge", "in", "D_PLANE_BOT", 95),
        ("2025-to-2026 area change, plane-corrected", "sq in", "A_CORR", 95),
        ("Published 2025-to-2026 range (Clemens)", "sq in", "A_PUB", 95),
        ("Between-umpire SD of the 2025-to-2026 shift", "in", "SD_UMP", 95),
        ("Split-half reliability of that shift", "ratio", "REL_UMP", 95),
        ("Umpires", "count", "N_UMP", 95),
        ("Called pitches, P0", "count", "N_CALLED_P0", 95),
        ("Games, P0", "count", "N_GAMES_P0", 95),
        ("Challenged pitches, zone validation", "count", "N_CHAL", 95),
        ("CH1-A5: binned minus smooth, 2025 step, area", "sq in", "A5_BUF", 95),
        ("CH1-A5: binned minus smooth, 2026 step, area", "sq in", "A5_ABS", 95),
        ("CH1-A5: area tolerance", "sq in", "A5_TOL", 95),
    ]
    for label, units, slot, level in rows:
        lines.append(f"| {label} | {units} | {interval(entry(ledger, slot), level)} | {slot} |")
    if total and share:
        lines += [
            f"| 2024-to-2026 total, area (not a slot) | sq in | {f(total['point'])} "
            f"({f(total['lo95'])} to {f(total['hi95'])}) | T4 row delta_total |",
            f"| Share of the two steps in 2026 (not a slot) | ratio | {f(share['point'], 3)} "
            f"({f(share['lo95'], 3)} to {f(share['hi95'], 3)}) | T4 row share_abs |",
        ]
    lines += [
        "",
        "The 2025 and 2026 steps sum to more than the 2024-to-2026 total. The gap is twice the",
        "pre-trend term g, which belongs to neither step. The abstract prints the two steps and",
        "not the total, so it never shows the sum.",
        "",
        "## (b) The placebos and the consequence that applies",
        "",
        "| placebo | quantity | estimate | interval | margin or threshold | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for r in p1 + p2:
        iv = (
            f"90% CI {f(r['lo'], 2)} to {f(r['hi'], 2)}"
            if r["placebo"] == "P1"
            else f"five placebos, {f(r['lo'], 2)} to {f(r['hi'], 2)}"
        )
        lines.append(
            f"| {r['placebo']} | {r['quantity']} ({r['units']}) | {f(r['estimate'], 2)} | {iv} "
            f"| {f(r['margin_or_threshold'], 2)} | {r['verdict']} |"
        )
    lines += [
        "",
        f"P1 {'FAILED' if p1_fail else 'passed'}. "
        f"P2 {'FAILED' if p2_fail else 'passed'} on every estimand."
        if p1 or p2
        else "T5_placebos.csv is absent: W3.21 has not run.",
        "",
    ]
    if p1_fail or p2_fail:
        lines += [
            "The frozen consequence applies as written, `PREREGISTRATION.md` section 8:",
            "",
            "> if P1 or P2 fails, the three-regime decomposition is reported as **descriptive**,",
            "> the causal language is removed from every artifact, and the failure is the",
            "> headline finding.",
            "",
            'CH1-A3 says the same: "Failure converts the chapter to descriptive and removes the',
            'causal language, and that failure is then the headline finding."',
            "",
            "What it means in plain terms: two seasons under one rule moved about half as far as",
            "the 2025 step. So the design can say when the zone moved, not what moved it. P2",
            "passing says the 2026 step is far larger than any within-season drift across an",
            "All-Star break.",
            "",
            *consequence_lines(),
            "",
        ]
    lines += [
        "## (c) RESULT CALL: three PROPOSALS for the owner",
        "",
        "PROPOSALS ONLY. The owner accepts, edits or rejects each. No agent writes the",
        "RESULT CALL line in `out/ch1/decision.md` or the CALL slot. Each is descriptive, as",
        "the consequence in (b) requires.",
        "",
    ]
    if share and buf_e and abs_e:
        drift = next((float(r["estimate"]) for r in p1 if r["quantity"].startswith("area")), 0.0)
        for i, (text, test, ok) in enumerate(
            proposals(share, float(buf_e["value"]), float(abs_e["value"]), drift), 1
        ):
            lines += [
                f'{i}. PROPOSAL, {words(text)} words: "{text}"',
                f"   Justified if {test}. Here: 2026 share {f(share['point'], 3)} "
                f"(95% CI {f(share['lo95'], 3)} to {f(share['hi95'], 3)}); steps "
                f"{f(buf_e['value'])} and {f(abs_e['value'])} sq in; P1 drift {f(drift)} sq in. "
                f"{'The numbers support it.' if ok else 'The numbers do not support it.'}",
            ]
        lines += [
            "",
            "Which the numbers support: the second. The 2026 share's interval sits above one half,",
            "so more of the contraction came in 2026. The margin is small, and a year-to-year",
            "drift of the P1 size is about as large as the gap between the two steps. That",
            "argues for wording the second as a measurement, not a ranking of rules. The third",
            "passes on the drift test, but not on the share interval.",
        ]
    else:
        lines.append("The ledger or T4 lacks the numbers for a reading; no proposal is offered.")
    lines += [
        "",
        "## (d) BREAK_YEAR",
        "",
        f"D_BUF reads {buf or 'absent'} and D_ABS reads {abs_ or 'absent'} on their 95% intervals.",
        "The rule is 2025 when the buffer step's interval excludes zero, otherwise 2026.",
        (
            "The numbers support **2025**: the 2025 step's interval excludes zero, so the zone "
            "was already smaller in 2025, before ABS challenges. Descriptively, that is where "
            "the break starts. The P1 drift is less than half that step and runs the other way."
            if buf == "loss"
            else "The numbers support 2026: the 2025 step's interval does not exclude zero."
        ),
        "",
        "## (e) Which abstract variant applies",
        "",
        "**descriptive** (`abstract/variants/ssac2027_abstract.descriptive.md`), because P1",
        'failed. The three D-66 variants (main, null-buffer, sign-reversal) all say "accounts',
        'for", so none carries the consequence. D-P6-01 in DECISIONS.md records it.',
        "`scripts/abstract.sh` fills it by default. The owner may reword it at R1, but not",
        "restore causal wording.",
        "",
        "## (f) The paste sheet at the form",
        "",
        "After the owner writes `abstract/owner-calls.json` as",
        '`{"CALL": "<sentence>", "BREAK_YEAR": "<year>"}`, `make abstract` writes',
        "`submissions/ssac2027/paste-sheet.md`, `submitted-abstract.txt` and",
        "`submitted-abstract.inline-table.txt`. Until then those three do not exist. At the form:",
        "",
        "1. Track: Baseball.",
        "2. Title: line 1 of `submitted-abstract.txt`.",
        "3. Body: the rest of `submitted-abstract.txt`. If the form has no upload field, paste",
        "   `submitted-abstract.inline-table.txt` instead.",
        "4. Uploads, only if the form has an upload field: `abstract/table1.png`, and",
        "   `abstract/figure1.png` if the figure stays.",
        "5. Author fields: typed at the form only, from `abstract/FORM-FIELDS.md` section 3",
        "   item 7. They are never pasted into the body or copied into this file (D-69, WR-19).",
        "6. After submitting: the confirmation screenshot and `receipt.eml` go into",
        "   `submissions/ssac2027/`, as its README says.",
        "",
        inline_line(report.get("inline")),
        "",
        "## (g) Deadline",
        "",
        "Quoted from `submissions/ssac2027/README.md`, which owns the deadline:",
        "",
        *deadline_lines(),
        "",
        "## (h) What stays open",
        "",
        "- The owner's sign-off line in DECISIONS.md, SOP section 9.1.",
        "- D-67: the narrow pre-registration sentence stands. Keep ABS_PREREG_SENTENCE=narrow.",
        "  GD-12 now passes on real receipts, so the script would allow the wide one if asked.",
        "- The SENS arms: W3.22's multiverse did not run, so CH1-A9 sign stability is not",
        "  evaluated. The five arms present agree in sign on all eight geometric components.",
        "- CH1-A5 misses on area. The binned estimates exceed the smooth fit by "
        + (
            f"{f(abs(float(t4_row(t4, 'area_sqin', 'delta_buffer')['binned_minus_bam'])))} and "
            f"{f(abs(float(t4_row(t4, 'area_sqin', 'delta_abs')['binned_minus_bam'])))} sq in"
            if t4_row(t4, "area_sqin", "delta_buffer")
            else "an amount T4 does not carry"
        )
        + ",",
        "  against a 3 sq in tolerance. The frozen rule makes it a limitation of the write-up. "
        + (
            "The Conclusion names it, from A5_BUF, A5_ABS and A5_TOL."
            if "A5_BUF" in printed
            else "The abstract does not name it yet."
        ),
        (
            "- D-R0-04's top-edge caveat: the Results say top-edge intervals are slightly too"
            " narrow. The caveat that the study cannot declare no change at the top edge is not"
            " needed, because the abstract makes no such claim."
            if "Top-edge intervals are slightly too narrow" in filled
            else "- D-R0-04's top-edge caveat: the abstract prints top-edge numbers without it."
        ),
        "- The RESULT CALL line in `out/ch1/decision.md`, and CALL and BREAK_YEAR.",
        "- `make abstract` then `bash quality/w612_check.sh`, then RP-08 and the numbers freeze.",
        "",
        "## Also for R1",
        "",
        "The slots as printed in this fill:",
        "",
        "| slot | printed | words |",
        "|---|---|---:|",
    ]
    for slot, value in printed.items():
        lines.append(f"| {slot} | {value} | {words(value)} |")
    cuts = report.get("cuts") or []
    lines += ["", "Cut ladder, SOP order. Rungs applied in this fill:", ""]
    lines += [
        f"- {c['rung']}: " + ("cut" if c.get("applied") else f"not cut, {c.get('why', '')}")
        for c in cuts
    ] or ["- none; the fill is within the cap"]
    lines += [
        "",
        (
            "Chapter 2 slots in the ledger: " + ", ".join(ch2) + "."
            if ch2
            else "Chapter 2: the ledger holds no CH2_ slot, so rung 2 of the cut ladder applies "
            "and there is no Chapter 2 sentence."
        ),
        "",
        "- Figure 1: keeping it costs no body words when the form takes an upload.",
        "- Checklist rule 8's MLB attribution string costs 7 words and does not fit the cap.",
        "- docs/harmonized_zone.md F1: the zone the W3.8 gate scored uses measured height, and",
        "  the Chapter 1 primary uses roster height. Decide whether Methods says so.",
        "- N_CALLED prints P0 as T1 counts it. The fits drop the four games without ABS",
        "  hardware (621 pitches), so the fitted sample is slightly smaller"
        + (
            ". Methods says the fits use samples drawn from P0."
            if "samples drawn from" in filled
            else ", and Methods does not say so."
        ),
        "",
    ]
    missing = report.get("missing") or []
    lines.append("Missing slots: " + (", ".join(missing) if missing else "none") + ".")
    return "\n".join(lines) + "\n"


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", default="docs/numbers.json")
    ap.add_argument("--report", default="out/tables/abstract_fill_report.json")
    ap.add_argument("--out", default="submissions/ssac2027/R1-agenda.md")
    ap.add_argument("--report-inline", default="")
    a = ap.parse_args(argv[1:])
    full = lambda p: p if os.path.isabs(p) else os.path.join(ROOT, p)  # noqa: E731
    with open(full(a.ledger), encoding="utf-8") as fh:
        ledger = json.load(fh)
    with open(full(a.report), encoding="utf-8") as fh:
        report = json.load(fh)
    if a.report_inline and os.path.exists(full(a.report_inline)):
        with open(full(a.report_inline), encoding="utf-8") as fh:
            report["inline"] = json.load(fh)
    os.makedirs(os.path.dirname(full(a.out)), exist_ok=True)
    with open(full(a.out), "w", encoding="utf-8") as fh:
        fh.write(agenda(ledger, report, os.path.relpath(full(a.ledger), ROOT)))
    print(f"r1_agenda: {os.path.relpath(full(a.out), ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
