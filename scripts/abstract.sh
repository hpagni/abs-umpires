#!/usr/bin/env bash
# scripts/abstract.sh -- `make abstract`. SOP W6.10 to W6.12, fleet phase 06.
#
# One command from the ledger to the paste sheet. It reads docs/numbers.json and
# writes nothing that is not derived from it:
#   1. GD-12, tools/comms/check_seal_order.sh. Its exit status decides whether the wide
#      pre-registration sentence is even allowed (D-67). The narrow one is the default.
#   2. tools/comms/build_exhibits.R    abstract/table1.*, abstract/figure1.*, sidecars
#   3. tools/comms/fill_slots.R        abstract/ssac2027_abstract.filled.md, and the
#                                      .inline-table copy that makes room for the table
#      tools/comms/r1_agenda.py        submissions/ssac2027/R1-agenda.md, review R1
#   4. tools/comms/build_submission.py submissions/ssac2027/, once CALL and BREAK_YEAR
#      are written by the owner in abstract/owner-calls.json
#
# It does not run export_numbers.R: the ledger is W7.24's, regenerated when a fit step
# lands, and this script only reads it. It fits nothing and reads no data.
#
# Environment:
#   ABS_LEDGER           the ledger (default docs/numbers.json)
#   ABS_VARIANT          main | null-buffer | sign-reversal (default main), D-66
#   ABS_CALLS            the owner's CALL and BREAK_YEAR (default abstract/owner-calls.json)
#   ABS_PREREG_SENTENCE  narrow | wide (default narrow); wide needs GD-12 to pass
#   ABS_OUTDIR           where abstract/, out/tables/ and submissions/ssac2027/ are
#                        written (default the repository). The dry run points it under
#                        out/dev/, so a synthetic file never lands in abstract/.
#   ABS_TAG              a dry-run tag inserted into every output file name
#
# Exit 0 drafted (owner slots may still be pending); 1 a ledger slot is missing; 3 over
# the 470-word cap after the SOP cut ladder; 2 anything else.
set -uo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2
LEDGER=${ABS_LEDGER:-docs/numbers.json}
VARIANT=${ABS_VARIANT:-main}
CALLS=${ABS_CALLS:-abstract/owner-calls.json}
PREREG=${ABS_PREREG_SENTENCE:-narrow}
OUT=${ABS_OUTDIR:-$root}
TAG=${ABS_TAG:-}
sfx() { if [ -n "$TAG" ]; then printf '.%s' "$TAG"; fi; }
case "$OUT" in /*) ;; *) OUT="$root/$OUT" ;; esac
if [ -n "$TAG" ] && [ "$OUT" = "$root" ]; then
  echo "abstract: ABS_TAG marks a dry run; set ABS_OUTDIR so its files stay out of abstract/"
  exit 2
fi
mkdir -p "$OUT/abstract" "$OUT/out/tables" "$OUT/submissions/ssac2027"

rel_out=${OUT#"$root"}; rel_out=${rel_out#/}
echo "abstract: ledger $LEDGER, variant $VARIANT, output root ${rel_out:-.}${TAG:+, tag $TAG}"

# The wide sentence says the plan preceded estimation. A vacuous pass (no receipt, no
# tag) proves nothing, so it needs at least one fit receipt, all descending from the
# pushed tag.
seal_flag=""
seal_out=$(bash tools/comms/check_seal_order.sh 2>&1)
seal=$?
printf '%s\n' "$seal_out"
if [ "$seal" -eq 0 ] && printf '%s\n' "$seal_out" |
     grep -Eq '^SEAL-ORDER OK \(([1-9][0-9]*)/\1 fit receipt\(s\) descend from'; then
  seal_flag="--seal-order-ok"
  echo "abstract: GD-12 passed on real receipts; the wide sentence is allowed if ABS_PREREG_SENTENCE=wide"
else
  echo "abstract: GD-12 has not proven the ordering; the narrow pre-registration sentence stands (D-67)"
fi

# The exhibits first: the inline table's length is what the no-upload body must hold.
Rscript tools/comms/build_exhibits.R --ledger "$LEDGER" ${TAG:+--tag "$TAG"} \
  --abstract-dir "$OUT/abstract" --tables-dir "$OUT/out/tables"
ex=$?

# Two fills from the same ledger: the body as pasted with the table uploaded, and the
# body for a form with no upload field, which must also hold the inline table.
fill() {
  Rscript tools/comms/fill_slots.R --ledger "$LEDGER" --variant "$VARIANT" --calls "$CALLS" \
    --out "$OUT/abstract/ssac2027_abstract$(sfx)$1.filled.md" \
    --report "$OUT/out/tables/abstract_fill_report$(sfx)$1.json" \
    --prereg-sentence "$PREREG" --extra-words "$2" $seal_flag
}
fill "" 0
rc=$?
[ "$ex" -eq 0 ] || { echo "abstract: build_exhibits exited $ex; stopping"; exit "$ex"; }
[ "$rc" -eq 0 ] || { echo "abstract: fill_slots exited $rc; stopping"; exit "$rc"; }
inline_words=$(wc -w < "$OUT/abstract/table1$(sfx).inline.md" | tr -d ' ')
fill ".inline-table" "$inline_words"
rc_inline=$?
[ "$rc_inline" -le 1 ] || [ "$rc_inline" -eq 3 ] || { echo "abstract: fill_slots (inline table) exited $rc_inline"; exit 2; }
[ "$rc_inline" -ne 3 ] || echo "abstract: the no-upload body is over the cap after the whole ladder; review R1 decides"

uv run --locked python tools/comms/r1_agenda.py --ledger "$LEDGER" \
  --report "$OUT/out/tables/abstract_fill_report$(sfx).json" \
  --report-inline "$OUT/out/tables/abstract_fill_report$(sfx).inline-table.json" \
  --out "$OUT/submissions/ssac2027/R1-agenda$(sfx).md" || exit 2

uv run --locked python tools/comms/build_submission.py ${TAG:+--tag "$TAG"} \
  --filled "$OUT/abstract/ssac2027_abstract.filled.md" \
  --filled-inline "$OUT/abstract/ssac2027_abstract.inline-table.filled.md" \
  --inline "$OUT/abstract/table1.inline.md" --table "$OUT/abstract/table1.md" \
  --report "$OUT/out/tables/abstract_fill_report.json" \
  --out-dir "$OUT/submissions/ssac2027"
sub=$?
case "$sub" in
  0) echo "abstract: drafted, exhibits built, submission package written" ;;
  1) echo "abstract: drafted and exhibits built; the package waits for the owner's CALL and BREAK_YEAR (review R1)" ;;
  *) echo "abstract: build_submission exited $sub"; exit "$sub" ;;
esac
exit 0
