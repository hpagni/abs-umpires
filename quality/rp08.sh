#!/usr/bin/env bash
# quality/rp08.sh -- the verify for SOP W6.11 (RP-08). It reads the cold build's evidence;
# it does not rerun the build, which takes the length of the full pipeline.
#
# Passes only when ops/coldbuild.sh has written out/tables/coldbuild_compare.csv with
# every row matched, and its sidecar says the ledger it compared is the docs/numbers.json
# on disk now, byte for byte. A ledger regenerated after the cold build fails this, so
# the cold build must be rerun. The freeze (ops/coldbuild.sh --freeze) runs the same test.
#
# Exit 0 reproduced; 1 not reproduced, stale, or not run.
set -uo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2
cmp=out/tables/coldbuild_compare
[ -s "$cmp.csv" ] && [ -s "$cmp.json" ] || { echo "RP-08 FAIL: no $cmp.csv; run bash ops/coldbuild.sh"; exit 1; }
python3 - "$cmp" <<'PY'
import csv, hashlib, json, sys
base = sys.argv[1]
side = json.load(open(base + ".json"))
rows = list(csv.DictReader(open(base + ".csv", encoding="utf-8")))
now = hashlib.sha256(open("docs/numbers.json", "rb").read()).hexdigest()
bad = [r["slot"] for r in rows if r["match"] != "true"]
fresh = side.get("repo_ledger_sha256") == now
print(f"RP-08: {len(rows) - len(bad)}/{len(rows)} rows match at {side.get('ref', '?')[:12]}; "
      f"ledger {'unchanged since the cold build' if fresh else 'CHANGED since the cold build'}")
if bad:
    print("RP-08 FAIL: " + ", ".join(bad))
sys.exit(0 if rows and not bad and fresh else 1)
PY
