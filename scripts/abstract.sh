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
#   ABS_VARIANT          main | null-buffer | sign-reversal | descriptive | owner (default
#                        owner). D-66 wrote the first three. Placebo P1 failed, so the
#                        frozen CH1-A3 consequence applies; descriptive carried it first
#                        (DECISIONS.md, 2026-09-30) and owner is the same case written in
#                        the owner's own voice, which replaces it (DECISIONS.md, 2026-09-30,
#                        the owner's instruction)
#   ABS_CALLS            the owner's CALL and BREAK_YEAR (default abstract/owner-calls.json;
#                        abstract/owner-calls.proposed.json holds the writer's proposal
#                        for review R1, filled only when named here)
#   ABS_EXHIBITS         a file naming the chosen exhibits, "figure1 <dir>" and "table1 <dir>"
#                        under abstract/exhibits/ (default abstract/exhibits/chosen.txt).
#                        On the real run, after build_exhibits.R, each chosen folder's PNG,
#                        alt text and caption are copied over abstract/figure1.png,
#                        abstract/figure1.alt.txt, abstract/table1.png and abstract/table1.md,
#                        so the checks read the exhibits that will be uploaded. The dry run
#                        (ABS_TAG set) keeps the generated ones.
#   ABS_PREREG_SENTENCE  narrow | wide (default narrow); wide needs GD-12 to pass
#   ABS_OUTDIR           where abstract/, out/tables/ and submissions/ssac2027/ are
#                        written (default the repository). The dry run points it under
#                        out/dev/, so a synthetic file never lands in abstract/.
#   ABS_TAG              a dry-run tag inserted into every output file name
#
# Exit 0 drafted (owner slots may still be pending); 1 a ledger slot is missing; 3 over
# the 495-word cap after the SOP cut ladder; 4 refused by GD-12 (a real run from a commit
# that does not descend from prereg-v1); 2 anything else.
set -uo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2
LEDGER=${ABS_LEDGER:-docs/numbers.json}
VARIANT=${ABS_VARIANT:-owner}
CALLS=${ABS_CALLS:-abstract/owner-calls.json}
EXHIBITS=${ABS_EXHIBITS:-abstract/exhibits/chosen.txt}
PREREG=${ABS_PREREG_SENTENCE:-narrow}
OUT=${ABS_OUTDIR:-$root}
TAG=${ABS_TAG:-}
sfx() { if [ -n "$TAG" ]; then printf '.%s' "$TAG"; fi; }
case "$OUT" in /*) ;; *) OUT="$root/$OUT" ;; esac
if [ -n "$TAG" ] && [ "$OUT" = "$root" ]; then
  echo "abstract: ABS_TAG marks a dry run; set ABS_OUTDIR so its files stay out of abstract/"
  exit 2
fi
# GD-12. Real numbers go into the abstract only from a commit that descends from the
# pre-registration tag (config/seal.yml), the rule every real fit entry point enforces. Only
# a dry run is exempt: ABS_TAG set and a ledger export_numbers.R marked _synthetic.
is_synth=$(python3 -c 'import json,sys; print("_synthetic" in json.load(open(sys.argv[1])))' "$LEDGER" 2>/dev/null)
if [ -n "$TAG" ] && [ "$is_synth" = "True" ]; then
  echo "abstract: dry run on a SYNTHETIC ledger; GD-12 ancestry is not required"
else
  prereg=$(sed -n 's/^prereg_tag:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' config/seal.yml | tr -d ' "' | head -1)
  if ! git merge-base --is-ancestor "${prereg:-prereg-v1}" HEAD 2>/dev/null; then
    echo "abstract: REFUSED (GD-12): HEAD $(git rev-parse --short HEAD) does not descend from ${prereg:-prereg-v1}."
    echo "abstract: real numbers are filled only after the pre-registration tag; the dry run is bash ops/abstract_dryrun.sh"
    exit 4
  fi
  echo "abstract: GD-12 ok, HEAD descends from $prereg"
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

# The chosen exhibits (2026-09-30): the exhibit lane keeps each candidate under
# abstract/exhibits/<dir>/ with its script, PNG, SVG, caption.md, alt.txt and
# data-sources.md. The two named in $EXHIBITS replace the generated figure1 and table1
# files, so W6.10 and W6.12 check the PNGs, alt text and caption that go to the form.
# table1.md becomes the chosen caption plus a pointer to the folder; the generated inline
# table (table1.inline.md) and the sidecar CSVs stay as built.
if [ "$ex" -eq 0 ] && [ -z "$TAG" ] && [ -s "$EXHIBITS" ]; then
  while read -r kind dir; do
    case "$kind" in figure1|table1) ;; ''|'#'*) continue ;; *) echo "abstract: $EXHIBITS names an unknown exhibit '$kind'"; exit 2 ;; esac
    src="abstract/exhibits/$dir"
    for f in "$src/$dir.png" "$src/alt.txt" "$src/caption.md"; do
      [ -s "$f" ] || { echo "abstract: chosen exhibit file missing: $f"; exit 2; }
    done
    cp "$src/$dir.png" "$OUT/abstract/$kind.png"
    if [ "$kind" = figure1 ]; then
      cp "$src/alt.txt" "$OUT/abstract/figure1.alt.txt"
    else
      { cat "$src/caption.md"; echo
        echo "The table is abstract/table1.png, copied from $src/$dir.png; its cells and their"
        echo "sources are listed in $src/data-sources.md, and its alt text is $src/alt.txt."; } \
        > "$OUT/abstract/table1.md"
    fi
    echo "abstract: $kind is the chosen exhibit $src"
  done < "$EXHIBITS"
fi

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
