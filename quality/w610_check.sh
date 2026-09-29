#!/usr/bin/env bash
# quality/w610_check.sh -- the scripted verify for SOP W6.10, the abstract draft.
#
# Runs, in order, and exits 0 only when every one passes:
#   1. scripts/abstract.sh (`make abstract`): fill the template from the ledger, write the
#      R1 agenda, draw the exhibits
#   2. the SOP word counter on the filled text as written, "#" marks included, with
#      <<CALL>> counted as 25 words and <<BREAK_YEAR>> as 1 while the owner has not
#      written them; cap 470
#   3. no slot other than CALL and BREAK_YEAR left unfilled
#   4. SSAC format: one title, exactly the four sections in order, no fifth heading, the
#      inline prior-art citation, and at least one 95% interval in Results
#   5. at most two tables or figures combined, each with its sidecar; figure alt text of
#      at least 40 characters (WR-14)
#   6. the writing gates on this step's files: quality/prose_lint.py, quality/check_numbers.py
#      (WR-07, against the ledger the text was filled from) and tools/comms/check_blind.py
#   7. on the real run only, `make lint-prose` over the whole corpus
#
# Before the Chapter 1 slots land in docs/numbers.json, step 1 stops with the missing
# slots named and this check fails. That is the correct state until W6.7 has run.
#
# The dry run sets ABS_LEDGER, ABS_OUTDIR, ABS_TAG, ABS_VARIANT and ABS_CALLS exactly as
# scripts/abstract.sh reads them (ops/abstract_dryrun.sh does this).
set -uo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2
TAG=${ABS_TAG:-}
OUT=${ABS_OUTDIR:-$root}
case "$OUT" in /*) ;; *) OUT="$root/$OUT" ;; esac
LEDGER=${ABS_LEDGER:-docs/numbers.json}
sfx() { if [ -n "$TAG" ]; then printf '.%s' "$TAG"; fi; }
A="$OUT/abstract"
FILLED="$A/ssac2027_abstract$(sfx).filled.md"
fails=0
step() { printf '\n== %s\n' "$1"; }
bad() { echo "W6.10 FAIL: $1"; fails=$((fails + 1)); }

step "1. scripts/abstract.sh"
bash scripts/abstract.sh || bad "scripts/abstract.sh exited $?"

step "2-4. word counter, slots, sections on ${FILLED#"$root"/}"
ABS_FILLED="$FILLED" uv run --locked python - <<'PY' || bad "word count, slots or sections"
import os, re, sys, pathlib
p = pathlib.Path(os.environ["ABS_FILLED"])
if not p.exists():
    print("FAIL: filled abstract missing; scripts/abstract.sh did not write it"); sys.exit(1)
t = p.read_text(encoding="utf-8")
slots = re.findall(r"<<([A-Z0-9_]+)>>", t)
other = sorted(set(slots) - {"CALL", "BREAK_YEAR"})
if other:
    print("FAIL: unfilled non-owner slot(s): " + ", ".join(other)); sys.exit(1)
n = len(t.split()) + 24 * slots.count("CALL")  # the SOP counter; a slot is one word
print(f"words: {n} of 470 (CALL {'pending, 25 reserved' if 'CALL' in slots else 'written'}, "
      f"BREAK_YEAR {'pending, 1 reserved' if 'BREAK_YEAR' in slots else 'written'})")
ok = n <= 470
heads = re.findall(r"^#{2,6}\s+(.*?)\s*$", t, re.M)
if heads != ["Introduction", "Methods", "Results", "Conclusion"]:
    print(f"FAIL: SSAC sections are {heads}"); ok = False
if len(re.findall(r"^#\s", t, re.M)) != 1:
    print("FAIL: exactly one title line expected"); ok = False
if "(Clemens, FanGraphs, 28 April 2026)" not in t:
    print("FAIL: the inline prior-art citation is missing (WR-05, WR-12)"); ok = False
res = t.split("## Results", 1)[-1].split("## Conclusion", 1)[0]
if not re.search(r"\(95% CI -?[\d.]+ to -?[\d.]+\)", res):
    print("FAIL: Results carries no estimate with a 95% interval (SSAC: actual results)"); ok = False
if ok:
    print("sections: Introduction, Methods, Results, Conclusion; no fifth; Results has intervals")
sys.exit(0 if ok else 1)
PY

step "5. exhibits"
n_ex=$(find "$A" -maxdepth 1 -type f \( -name "table*.png" -o -name "figure*.png" \) | wc -l | tr -d ' ')
echo "tables and figures in ${A#"$root"/}: $n_ex"
[ "$n_ex" -le 2 ] || bad "$n_ex tables and figures; SSAC allows two combined"
for f in "$A/table1$(sfx).md" "$A/table1$(sfx).png" "$A/figure1$(sfx).png" "$A/figure1$(sfx).alt.txt" \
         "$OUT/out/tables/table1_data$(sfx).csv" "$OUT/out/tables/figure1_data$(sfx).csv"; do
  [ -s "$f" ] || bad "missing ${f#"$root"/}"
done
alt=$(tr -d '\n' < "$A/figure1$(sfx).alt.txt" 2>/dev/null | wc -c | tr -d ' ')
echo "figure1 alt text: $alt characters"
[ "${alt:-0}" -ge 40 ] || bad "figure1 alt text under 40 characters (WR-14)"

step "6. writing gates on this step's files"
mine=("$FILLED" "$A/table1$(sfx).md" "$A/table1$(sfx).inline.md" "$A/figure1$(sfx).alt.txt")
uv run --locked python quality/prose_lint.py "${mine[@]}" abstract/ssac2027_abstract.md abstract/variants \
  || bad "quality/prose_lint.py"
uv run --locked python quality/prose_lint.py "$OUT/submissions/ssac2027/R1-agenda$(sfx).md" \
  || bad "quality/prose_lint.py on the R1 agenda"
uv run --locked python quality/check_numbers.py --ledger "$LEDGER" "${mine[@]}" \
  || bad "quality/check_numbers.py (WR-07)"
uv run --locked python tools/comms/check_blind.py "${mine[@]}" || bad "tools/comms/check_blind.py (WR-15)"

if [ -z "$TAG" ]; then
  step "7. make lint-prose"
  make lint-prose || bad "make lint-prose"
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "W6.10 OK: filled, within 470 words, four sections, at most two exhibits, gates green"
  exit 0
fi
echo "W6.10 FAILED: $fails check(s)"
exit 1
