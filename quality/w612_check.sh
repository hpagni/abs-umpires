#!/usr/bin/env bash
# quality/w612_check.sh -- the scripted verify for SOP W6.12's package: the text to paste.
#
# It checks the package, not the submission. The form is sign-in gated and the submit is
# the owner's; this script never reaches the form.
#   1. the SOP word counter, verbatim, on submissions/ssac2027/submitted-abstract.txt:
#      the file exists, no <<SLOT>> is left, and it is at or under 470 words. The same
#      counter runs on the no-upload copy, submitted-abstract.inline-table.txt. Until
#      abstract/FORM-FIELDS.md answers the upload question both must pass; after it,
#      only the copy that will be pasted must.
#   2. the blind-review grep (WR-15) on both copies: hudson, pagni, ucla, hudpag,
#      github.com, hpagni, abs-umpires
#   3. SSAC format on the pasted text: title, the four section names in order, a 95%
#      interval in Results
#   4. the prose gate and the number gate (WR-07, against the ledger it was filled from)
#   5. the paste sheet and the submission README exist; the README carries both deadline
#      readings and the 12:00 Madrid target
#
# The dry run sets ABS_OUTDIR, ABS_TAG and ABS_LEDGER as scripts/abstract.sh reads them.
set -uo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2
TAG=${ABS_TAG:-}
OUT=${ABS_OUTDIR:-$root}
case "$OUT" in /*) ;; *) OUT="$root/$OUT" ;; esac
LEDGER=${ABS_LEDGER:-docs/numbers.json}
sfx() { if [ -n "$TAG" ]; then printf '.%s' "$TAG"; fi; }
S="$OUT/submissions/ssac2027"
PLAIN="$S/submitted-abstract$(sfx).txt"
INLINE="$S/submitted-abstract$(sfx).inline-table.txt"
fails=0
bad() { echo "W6.12 FAIL: $1"; fails=$((fails + 1)); }

upload=$(sed -n 's/.*upload field at all: `\([^`]*\)`.*/\1/p' abstract/FORM-FIELDS.md 2>/dev/null |
         tr -d '_ ' | tr '[:upper:]' '[:lower:]' | head -1)
case "$upload" in yes*) need="$PLAIN" ;; no*) need="$INLINE" ;; *) need="$PLAIN $INLINE" ;; esac
echo "upload field per abstract/FORM-FIELDS.md: ${upload:-unanswered}"

for f in $PLAIN $INLINE; do
  must=0
  case " $need " in *" $f "*) must=1 ;; esac
  echo
  echo "== ${f#"$root"/} ($([ $must -eq 1 ] && echo "must fit" || echo "advisory"))"
  # 1. The SOP W6.12 word counter, verbatim but for the path, which the dry run moves.
  ABS_SUBMITTED="$f" python3.12 - <<'PY'
import os, re, sys, pathlib
p = pathlib.Path(os.environ["ABS_SUBMITTED"])
if not p.exists():
    print('FAIL: submitted-abstract.txt missing; fill the template first'); sys.exit(1)
t = p.read_text()
if re.search(r'<<[A-Z_]+>>', t):
    print('FAIL: unfilled slot in submitted-abstract.txt'); sys.exit(1)
n = len(t.split())
print('words:', n)
sys.exit(0 if n <= 470 else 1)
PY
  rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ "$must" -eq 1 ]; then bad "word counter on ${f#"$root"/}"; else echo "advisory: over the cap"; fi
  fi
  [ -f "$f" ] || continue
  # 2. WR-15, the SOP grep, widened to the other author strings.
  if grep -inE 'hudson|pagni|ucla|hudpag|github\.com|hpagni|abs-umpires' "$f"; then
    bad "blind review: an author or repository string in ${f#"$root"/}"
  fi
  # 3. SSAC format.
  ABS_SUBMITTED="$f" python3.12 - <<'PY' || bad "SSAC format in ${f#"$root"/}"
import os, re, sys
t = open(os.environ["ABS_SUBMITTED"], encoding="utf-8").read()
heads = [x for x in t.split("\n") if x.strip() in ("Introduction", "Methods", "Results", "Conclusion")]
if heads != ["Introduction", "Methods", "Results", "Conclusion"]:
    print("FAIL: section names", heads); sys.exit(1)
res = t.split("\nResults\n", 1)[-1].split("\nConclusion\n", 1)[0]
if not re.search(r"\(95% CI -?[\d.]+ to -?[\d.]+\)", res):
    print("FAIL: no 95% interval in Results"); sys.exit(1)
print("format: title, four sections in order, Results carries intervals")
PY
done

echo
echo "== writing gates"
uv run --locked python quality/prose_lint.py "$PLAIN" "$INLINE" || bad "quality/prose_lint.py"
uv run --locked python quality/check_numbers.py --ledger "$LEDGER" "$PLAIN" "$INLINE" || bad "WR-07"

echo
echo "== package files"
[ -s "$S/paste-sheet$(sfx).md" ] || bad "missing paste sheet"
readme=submissions/ssac2027/README.md
if [ -s "$readme" ] && grep -q '05:59' "$readme" && grep -q '06:59' "$readme" && grep -q '12:00' "$readme"; then
  echo "README: both deadline readings and the 12:00 Madrid target"
else
  bad "$readme missing or without both deadline readings and the target"
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "W6.12 package OK: the text to paste fits, is blind, is in SSAC format and passes the gates"
  exit 0
fi
echo "W6.12 package FAILED: $fails check(s)"
exit 1
