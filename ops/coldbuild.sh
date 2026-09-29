#!/usr/bin/env bash
# ops/coldbuild.sh -- SOP W6.11, RP-08: rebuild the abstract's numbers from a clean clone,
# compare them with docs/numbers.json, and freeze them with a guarded tag.
#
#   bash ops/coldbuild.sh                 clone origin, bootstrap, rebuild, compare
#   bash ops/coldbuild.sh --synthetic D   the dry run: clone, bootstrap, then rebuild the
#                                         ledger from the SYNTHETIC inputs under D (made
#                                         by tools/comms/synthetic_abstract_inputs.py)
#                                         and compare with D/numbers.SYNTHETIC.json
#   bash ops/coldbuild.sh --freeze [--dry-run]   tag numbers-frozen-ssac2027, guarded
#
# RP-08 as the SOP writes it: git clone ... /tmp/coldbuild && uv sync --locked &&
# Rscript -e 'renv::restore(prompt=FALSE)' && make warehouse && make all. The clone has
# no data/ (gitignored); it gets a symlink to this checkout's data/, read only by
# convention, and builds its own warehouse from it. Nothing is copied from out/, and the
# exporter's committed inputs (export_numbers.R --list-inputs) are deleted in the clone,
# so ABS_COLDBUILD_TARGETS must rebuild every one of them or the compare fails.
#
# Before the build the clone's docs/numbers.json is emptied to a skeleton, so every
# number the compare finds in the rebuilt ledger was produced in the clone, not carried.
# The compare covers each abstract slot and each table cell in abstract_slots.json and
# matches the printed strings, the text the abstract shows. It writes
# out/tables/coldbuild_compare.csv (slot, repo_value, coldbuild_value, match) and a
# .json sidecar with the shas it compared.
#
# GD-12: before prereg-v1 is pushed, no fit may touch 2025 or 2026 data. The real mode
# refuses to start until origin carries prereg-v1 and the commit it builds descends from it.
#
# Environment: ABS_COLDBUILD_DIR (default /tmp/coldbuild), ABS_COLDBUILD_SRC (default
# the origin URL; the dry run passes this checkout), ABS_COLDBUILD_REF (default HEAD's
# sha, which must be on the source), ABS_COLDBUILD_TARGETS (default "warehouse all").
#
# Exit 0 every number matches (or the freeze is done); 1 a mismatch, a missing number or
# a refused guard; 2 usage.
set -uo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2
DIR=${ABS_COLDBUILD_DIR:-/tmp/coldbuild}
TAG_FREEZE=numbers-frozen-ssac2027
PREREG=$(sed -n 's/^prereg_tag:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' config/seal.yml | tr -d ' "' | head -1)
say() { printf 'coldbuild: %s\n' "$*"; }
die() { printf 'coldbuild: REFUSED: %s\n' "$*" >&2; exit 1; }
sha256() { shasum -a 256 "$1" | cut -d' ' -f1; }

prereg_pushed() {
  local remote local_sha
  remote=$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags origin "refs/tags/$PREREG^{}" 2>/dev/null | cut -f1)
  [ -n "$remote" ] || remote=$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags origin "refs/tags/$PREREG" 2>/dev/null | cut -f1)
  local_sha=$(git rev-list -n 1 "$PREREG" 2>/dev/null || true)
  [ -n "$remote" ] && [ -n "$local_sha" ] && git merge-base --is-ancestor "$local_sha" "$1"
}

# ------------------------------------------------------------------ freeze
if [ "${1:-}" = "--freeze" ]; then
  dry=0; [ "${2:-}" = "--dry-run" ] && dry=1
  if git rev-parse -q --verify "refs/tags/$TAG_FREEZE" >/dev/null; then
    say "$TAG_FREEZE already exists at $(git rev-list -n 1 "$TAG_FREEZE"); nothing to do"
    exit 0
  fi
  head=$(git rev-parse HEAD)
  git diff --quiet && git diff --cached --quiet || die "the working tree has uncommitted changes"
  [ -z "$(git ls-files --others --exclude-standard -- abstract docs submissions tools quality)" ] ||
    die "untracked files under abstract/, docs/, submissions/, tools/ or quality/"
  prereg_pushed "$head" || die "$PREREG is not on origin, or HEAD does not descend from it (GD-12)"
  bash tools/comms/check_seal_order.sh || die "GD-12 fails: a fit receipt predates $PREREG"
  cmp=out/tables/coldbuild_compare.json
  [ -s "$cmp" ] || die "no $cmp; run the cold build first"
  ledger=$(sha256 docs/numbers.json)
  python3 - "$cmp" "$ledger" <<'PY' || die "the cold build did not reproduce this ledger"
import json, sys
c = json.load(open(sys.argv[1]))
ok = c.get("all_match") is True and c.get("repo_ledger_sha256") == sys.argv[2] and c.get("rows", 0) > 0
print(f"coldbuild: compare {c.get('matched')}/{c.get('rows')} rows, ledger sha256 "
      f"{'matches' if c.get('repo_ledger_sha256') == sys.argv[2] else 'DIFFERS'}")
sys.exit(0 if ok else 1)
PY
  rep=out/tables/abstract_fill_report.json
  [ -s "$rep" ] && [ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["ledger_sha256"])' "$rep")" = "$ledger" ] ||
    die "abstract/ssac2027_abstract.filled.md was not filled from this docs/numbers.json; run make abstract"
  cmd=(git tag -a "$TAG_FREEZE" -m "numbers frozen for the SSAC 2027 abstract" "$head")
  if [ "$dry" -eq 1 ]; then
    say "DRY RUN, every guard passed. Would run: ${cmd[*]} && git push origin refs/tags/$TAG_FREEZE"
    exit 0
  fi
  "${cmd[@]}" || die "git tag failed"
  git push origin "refs/tags/$TAG_FREEZE" || die "the tag is local only; push it by hand"
  mkdir -p submissions/ssac2027
  printf '{\n  "tag": "%s",\n  "sha": "%s",\n  "numbers_json_sha256": "%s",\n  "frozen_at_madrid": "%s"\n}\n' \
    "$TAG_FREEZE" "$head" "$ledger" "$(TZ=Europe/Madrid date -Iseconds)" > submissions/ssac2027/freeze.json
  say "tagged $head as $TAG_FREEZE and pushed; commit submissions/ssac2027/freeze.json"
  exit 0
fi

# ------------------------------------------------------------------ cold build
synth=""
case "${1:-}" in
  "") ;;
  --synthetic) synth=${2:?--synthetic needs the dry-run directory}; synth=$(cd "$synth" && pwd) ;;
  *) echo "usage: bash ops/coldbuild.sh [--synthetic DIR | --freeze [--dry-run]]" >&2; exit 2 ;;
esac
SRC=${ABS_COLDBUILD_SRC:-$(git remote get-url origin)}
REF=${ABS_COLDBUILD_REF:-$(git rev-parse HEAD)}
if [ -z "$synth" ]; then
  prereg_pushed "$REF" || die "$PREREG is not on origin, or $REF does not descend from it. No fit may touch 2025 or 2026 data before the tag (GD-12)"
fi
say "source $SRC at $REF into $DIR"
rm -rf "$DIR"
git clone -q "$SRC" "$DIR" || die "git clone failed"
git -C "$DIR" checkout -q "$REF" || die "$REF is not on the source; push it first"
cd "$DIR" || exit 2
python3 - docs/numbers.json <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["entries"] = []
d["_coldbuild"] = "emptied by ops/coldbuild.sh: every entry below was rebuilt in the clone"
json.dump(d, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
PY

say "bootstrap: uv sync --locked, renv::restore"
uv sync --locked --all-groups -q || die "uv sync failed"
Rscript -e 'renv::restore(prompt = FALSE)' >/dev/null || die "renv::restore failed"

out_ledger="$DIR/docs/numbers.json"
if [ -n "$synth" ]; then
  say "SYNTHETIC: no data, no warehouse, no fit; the ledger is rebuilt from $synth/in"
  repo_ledger="$synth/numbers.SYNTHETIC.json"
  out_ledger="$DIR/numbers.coldbuild.SYNTHETIC.json"
  Rscript tools/comms/export_numbers.R --inputs "$synth/in" --base "$synth/numbers-base.SYNTHETIC.json" \
    --out "$out_ledger" --tag SYNTHETIC --synthetic || die "export_numbers failed in the clone"
  compare="$synth/coldbuild_compare.SYNTHETIC.csv"
else
  [ -d "$root/data" ] || die "no data/ in $root to link"
  ln -s "$root/data" "$DIR/data"
  # The exporter's inputs are committed CSVs under out/. Left in the clone they would be
  # carried, not rebuilt, and the compare would pass on git's copy. Delete them, so each
  # number the compare finds was made by the targets below.
  inputs=$(Rscript tools/comms/export_numbers.R --list-inputs) || die "export_numbers --list-inputs failed"
  for f in $inputs; do rm -f "$f"; done
  say "deleted the exporter's inputs in the clone: $(printf '%s ' $inputs)"
  for t in ${ABS_COLDBUILD_TARGETS:-warehouse all}; do
    say "make $t"
    make "$t" || die "make $t failed in the clone"
  done
  Rscript tools/comms/export_numbers.R || die "export_numbers failed in the clone"
  repo_ledger="$root/docs/numbers.json"
  compare="$root/out/tables/coldbuild_compare.csv"
fi

cd "$root" || exit 2
mkdir -p "$(dirname "$compare")"
uv run --locked python - "$repo_ledger" "$out_ledger" "$compare" "$REF" <<'PY'
import csv, hashlib, json, sys
repo_p, cold_p, out_p, ref = sys.argv[1:5]
spec = json.load(open("tools/comms/abstract_slots.json", encoding="utf-8"))
# (row label, ledger entry): an abstract slot reads its ledger_slot when it has one.
slots = [(k if "ledger_slot" not in v else f"{k} ({v['ledger_slot']})", v.get("ledger_slot", k))
         for k, v in spec["slots"].items() if v["kind"] != "owner"]
slots += [(s, s) for s in (f"T1_{r[0]}_{c[0]}" for r in spec["table1"]["rows"] for c in spec["table1"]["cols"])]
def load(p):
    return {e["slot"]: e for e in json.load(open(p, encoding="utf-8")).get("entries", []) if "slot" in e}
def shown(e):
    if e is None:
        return ""
    if not e.get("print"):
        return str(e.get("value"))
    pr = e.get("print_contraction") or e["print"]
    return " ".join(str(pr.get(k, "")) for k in ("point", "lo95", "hi95")).strip()
repo, cold = load(repo_p), load(cold_p)
rows = [(s, shown(repo.get(k)), shown(cold.get(k))) for s, k in slots]
rows = [(s, a, b, bool(a) and a == b) for s, a, b in rows]
with open(out_p, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["slot", "repo_value", "coldbuild_value", "match"])
    w.writerows([(s, a, b, str(m).lower()) for s, a, b, m in rows])
matched = sum(m for *_, m in rows)
side = {"ref": ref, "repo_ledger": repo_p, "repo_ledger_sha256": hashlib.sha256(open(repo_p, "rb").read()).hexdigest(),
        "rows": len(rows), "matched": matched, "all_match": matched == len(rows)}
json.dump(side, open(out_p[:-4] + ".json", "w"), indent=2)
for s, a, b, m in rows:
    if not m:
        print(f"coldbuild: MISMATCH {s}: repo {a or 'absent'} | cold build {b or 'absent'}")
print(f"coldbuild: {matched}/{len(rows)} abstract numbers reproduced; {out_p}")
sys.exit(0 if matched == len(rows) else 1)
PY
