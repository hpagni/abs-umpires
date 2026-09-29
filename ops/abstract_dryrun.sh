#!/usr/bin/env bash
# ops/abstract_dryrun.sh -- the SSAC abstract machinery on an obviously SYNTHETIC ledger.
# SOP W6.10 to W6.12, fleet phase 06. It fits nothing and reads no data file.
#
# Everything lands under out/dev/abstract_dryrun/ (gitignored), and every file it writes
# carries SYNTHETIC in its name. It:
#   1. writes round-number result CSVs (tools/comms/synthetic_abstract_inputs.py)
#   2. exports them to numbers.SYNTHETIC.json from an empty base (export_numbers.R)
#   3. runs quality/w610_check.sh and quality/w612_check.sh on each D-66 variant; checks
#      that every slot of the main variant prints its synthetic truth and no decoy (3b);
#      before prereg-v1, requires export_numbers.R and scripts/abstract.sh to refuse a
#      real run with exit 4 (3c, GD-12)
#   4. proves each gate fires: it plants one fault per copy and requires a failure
#   5. with --coldbuild, runs ops/coldbuild.sh --synthetic on a clone of HEAD, then
#      plants a changed input and requires the compare to fail
#
#   bash ops/abstract_dryrun.sh [--coldbuild]
#
# Exit 0 when every check passes and every planted fault is caught.
set -uo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2
D=out/dev/abstract_dryrun
L=$D/numbers.SYNTHETIC.json
fails=0
bad() { echo "DRY RUN FAIL: $1"; fails=$((fails + 1)); }
hdr() { printf '\n######## %s\n' "$1"; }

hdr "1-2. synthetic inputs and ledger"
rm -rf "$D"
uv run --locked python tools/comms/synthetic_abstract_inputs.py --out "$D" || exit 1
Rscript tools/comms/export_numbers.R --inputs "$D/in" --base "$D/numbers-base.SYNTHETIC.json" \
  --out "$L" --tag SYNTHETIC --synthetic || exit 1

for v in main null-buffer sign-reversal; do
  hdr "3. variant $v: W6.10 and the W6.12 package"
  env ABS_LEDGER="$L" ABS_TAG=SYNTHETIC ABS_OUTDIR="$D/$v" ABS_VARIANT="$v" \
    ABS_CALLS="$D/owner-calls.SYNTHETIC.json" bash quality/w610_check.sh > "$D/$v.w610.log" 2>&1 \
    || bad "w610_check on $v (see $D/$v.w610.log)"
  grep -E '^fill_slots|^words:|^W6.10|^build_submission' "$D/$v.w610.log"
  env ABS_LEDGER="$L" ABS_TAG=SYNTHETIC ABS_OUTDIR="$D/$v" bash quality/w612_check.sh \
    > "$D/$v.w612.log" 2>&1 || bad "w612_check on $v (see $D/$v.w612.log)"
  grep -E '^words:|^W6.12|^upload' "$D/$v.w612.log"
done

hdr "3b. synthetic recovery: every slot prints its truth, no decoy is printed"
uv run --locked python tools/comms/synthetic_abstract_inputs.py \
  --verify "$D/main/abstract/ssac2027_abstract.SYNTHETIC.filled.md" || bad "synthetic recovery on the main variant"

hdr "3c. GD-12: the real entry points refuse while HEAD does not descend from the prereg tag"
prereg=$(sed -n 's/^prereg_tag:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' config/seal.yml | tr -d ' "' | head -1)
if git merge-base --is-ancestor "$prereg" HEAD 2>/dev/null; then
  echo "HEAD descends from $prereg; the refusal proof does not apply"
else
  mkdir -p "$D/gd12/in/out/tables"
  cp "$D/in/out/tables/abstract_slots_ch1.SYNTHETIC.csv" "$D/gd12/in/out/tables/abstract_slots_ch1.csv"
  Rscript tools/comms/export_numbers.R --inputs "$D/gd12/in" --base "$D/numbers-base.SYNTHETIC.json" \
    --out "$D/gd12/numbers.json" > "$D/gd12/export.log" 2>&1
  rc=$?
  if [ "$rc" -eq 4 ] && grep -q "REFUSED (GD-12)" "$D/gd12/export.log"; then
    echo "refused export_numbers.R on an unmarked fit-result input: exit $rc"
  else
    bad "export_numbers.R did not refuse a fit-result input before $prereg (exit $rc)"
  fi
  bash scripts/abstract.sh > "$D/gd12/abstract.log" 2>&1
  rc=$?
  if [ "$rc" -eq 4 ] && grep -q "REFUSED (GD-12)" "$D/gd12/abstract.log"; then
    echo "refused scripts/abstract.sh (make abstract) on docs/numbers.json: exit $rc"
  else
    bad "scripts/abstract.sh did not refuse before $prereg (exit $rc)"
  fi
fi

hdr "4. planted faults: each must be caught"
M=$D/main
F=$M/abstract/ssac2027_abstract.SYNTHETIC.filled.md
T=$M/submissions/ssac2027/submitted-abstract.SYNTHETIC.txt
plant() {  # name, file to copy, python replace (old, new), gate command with {} for the copy
  local name=$1 src=$2 old=$3 new=$4 gate=$5 rule=$6 rel copy
  rel=${src#"$M"/}
  copy="$D/proofs/$name/$rel"
  mkdir -p "$(dirname "$copy")"
  OLD="$old" NEW="$new" python3 -c 'import os,sys; t=open(sys.argv[1]).read(); o=os.environ["OLD"]; assert o in t, o; open(sys.argv[2],"w").write(t.replace(o, os.environ["NEW"], 1))' "$src" "$copy" || { bad "$name: could not plant"; return; }
  out=$(eval "${gate//\{\}/$copy}" 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q -- "$rule"; then
    echo "caught  $name: exit $rc, $rule"
  else
    bad "$name was NOT caught (exit $rc, no $rule)"
  fi
}
counter='ABS_SUBMITTED={} python3.12 -c "import os,re,sys;t=open(os.environ[\"ABS_SUBMITTED\"]).read();n=len(t.split());print(\"FAIL: unfilled slot\" if re.search(r\"<<[A-Z_]+>>\",t) else \"words: %d\" % n);sys.exit(1 if re.search(r\"<<[A-Z_]+>>\",t) or n>470 else 0)"'
pad=$(printf 'padding %.0s' $(seq 1 12))
plant over-cap "$T" "Games from 22 September" "$pad Games from 22 September" "$counter" "words: 4"
plant unfilled-slot "$T" "10.0 (95% CI 5.0 to 15.0)" "<<D_BUF>>" "$counter" "unfilled slot"
plant wr20-buffer "$F" "two inches outside the zone edge" "two inches of the zone edge" \
  "uv run --locked python quality/prose_lint.py {}" "WR-20"
plant wr15-author "$F" "We fit called-strike" "Hudson Pagni at UCLA fit called-strike" \
  "uv run --locked python tools/comms/check_blind.py {}" "WR-15"
plant wr07-number "$F" "10.0 (95% CI 5.0" "10.5 (95% CI 5.0" \
  "uv run --locked python quality/check_numbers.py --ledger $L {}" "10.5 is in no traceable source"
plant wr03-sop-sentence "$F" "(95% CI 15.0 to 25.0). The 2022-to-2024 pre-trend is" \
  "(95% CI 15.0 to 25.0), against a 2022-to-2024 pre-trend of" \
  "uv run --locked python quality/prose_lint.py {}" "WR-03"
plant wr18-no-limitation "$F" "and its limitation is that no real number exists" "and it states no weakness since no real number exists" \
  "uv run --locked python quality/prose_lint.py {}" "WR-18"
plant wr09-em-dash "$F" "and 2025 was itself" "and 2025 — itself" \
  "uv run --locked python quality/prose_lint.py {}" "WR-09"

hdr "4b. the cut ladder, in SOP order, on the main variant at lower caps"
for cap in 450 440 400; do
  Rscript tools/comms/fill_slots.R --ledger "$L" --calls "$D/owner-calls.SYNTHETIC.json" --cap "$cap" \
    --out "$D/proofs/ladder/ssac2027_abstract.SYNTHETIC.cap$cap.filled.md" \
    --report "$D/proofs/ladder/fill_report.SYNTHETIC.cap$cap.json" | head -1
  echo "cap $cap exit ${PIPESTATUS[0]}; cuts: $(python3 -c 'import json,sys;print([c["rung"] for c in json.load(open(sys.argv[1]))["cuts"] if c.get("applied")])' "$D/proofs/ladder/fill_report.SYNTHETIC.cap$cap.json")"
done

if [ "${1:-}" = "--coldbuild" ]; then
  hdr "5. RP-08 on a clean clone of HEAD, synthetic inputs"
  ABS_COLDBUILD_SRC="$root" ABS_COLDBUILD_DIR="$root/$D/coldbuild.SYNTHETIC" \
    bash ops/coldbuild.sh --synthetic "$D" || bad "coldbuild --synthetic did not reproduce the synthetic ledger"
  cp -R "$D/in" "$D/in.orig"
  sed -i '' 's/^D_ABS,-20.0/D_ABS,-21.0/' "$D/in/out/tables/abstract_slots_ch1.SYNTHETIC.csv"
  if ABS_COLDBUILD_SRC="$root" ABS_COLDBUILD_DIR="$root/$D/coldbuild.SYNTHETIC" \
     bash ops/coldbuild.sh --synthetic "$D" > "$D/coldbuild.planted.log" 2>&1; then
    bad "a changed D_ABS input was NOT caught by the RP-08 compare"
  else
    echo "caught  rp08-mismatch: $(grep MISMATCH "$D/coldbuild.planted.log" | head -2 | tr '\n' ' ')"
  fi
  rm -rf "$D/in" && mv "$D/in.orig" "$D/in"
fi

echo
[ "$fails" -eq 0 ] && { echo "DRY RUN OK: every check passed and every planted fault was caught"; exit 0; }
echo "DRY RUN: $fails problem(s)"; exit 1
