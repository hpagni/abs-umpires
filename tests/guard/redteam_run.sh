#!/bin/sh
# tests/guard/redteam_run.sh -- GD-09, the red team. SOP step W9.7.
#
# The body behind `make prove-guard-redteam`. W1.14 owns the Makefile and
# already wrote the target; this script is the whole of what it runs.
#
# A guard that has never failed is a guard nobody has tested. This script
# plants real violations in the worktree, one at a time, asserts that the guard
# fails on each by file and line, reverts, and at the end requires the guard to
# come back green. It exits non-zero if the guard stays silent on any plant,
# which is the failure mode worth catching.
#
# WHAT IS PLANTED. Two SOP plants and nine evasions. The two SOP plants are the
# ones SOP line 1683 names, applied from tests/guard/redteam.patch: a held-out
# label comparison in a Chapter 1 R script and the held-out view in the Chapter
# 3 solver. The nine evasions are every plant that got past the phase 01
# scanner when an independent red team ran eleven of them:
#
#   E1 the label spelled in two pieces and compared through a variable
#   E2 the view name built by an f-string from a variable
#   E3 a raw fact read with FROM and the table on two lines, in a dbt model
#   E4 a raw fact read that a comment elsewhere in the file used to forgive
#   E5 a boundary-date comparison written as a later day, and as > the day before
#   E6 the held-out view in a notebook padded past two megabytes by one plot
#   E7 an importable symlink pointing out of the repository
#   E8 the complement, analysis_set against the open label, which selects
#      exactly the held-out rows without ever writing the held-out one
#   E9 the second fact table, which no rule named
#
# Every plant is written here from fragments, never as a literal, so this file
# passes GD-04 as stored, like every other file in the repository.
#
# HONESTY. Nothing below prints a guard result that the guard did not produce.
# Each assertion prints the line the guard actually emitted, quoted from its
# output, and the verdict is printed after the check, never before it.
#
# The worktree is left exactly as it was found, whatever happens in the middle:
# the two patched files are copied before anything is applied and restored from
# those copies by an EXIT trap, and every file this script creates is removed by
# the same trap.
#
# It reads no data row, opens no database and issues no request.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root" || exit 2

PATCH="tests/guard/redteam.patch"
R_FILE="R/ch1/20_surfaces.R"
PY_FILE="src/absump/ch3/dp_fast.py"
SCAN="tests/guard/gd04_scan.py"

# The banned strings, assembled from fragments so that this script does not
# carry the literals the guard bans (GD-04 reads this file like any other).
FRAG="seal"
HELD="${FRAG}ed"
VIEW="v_pitch_${HELD}"
FACT="fct""_pitch"
FACT2="fct""_challenge"
COL="analysis""_set"
NEQ="!""="

if [ -n "${ABS_SEAL_UNLOCK:-}" ]; then
  echo "[redteam] refusing: ABS_SEAL_UNLOCK is set in this shell" >&2
  exit 2
fi

for f in "$PATCH" "$R_FILE" "$PY_FILE" "$SCAN"; do
  if [ ! -f "$f" ]; then
    echo "[redteam] missing $f; the red team cannot plant a violation without it" >&2
    exit 2
  fi
done

# The boundary day, and the two days around it, read from the config the guard
# reads. No date is written in this file.
BOUNDARY=$(sed -n 's/^seal_start_date:[[:space:]]*"\{0,1\}\([0-9-]*\)"\{0,1\}.*/\1/p' config/seal.yml)
if [ -z "$BOUNDARY" ]; then
  echo "[redteam] could not read seal_start_date from config/seal.yml" >&2
  exit 2
fi
DAY_AFTER=$(date -j -v+1d -f "%Y-%m-%d" "$BOUNDARY" "+%Y-%m-%d" 2>/dev/null \
  || date -d "$BOUNDARY + 1 day" "+%Y-%m-%d")
DAY_BEFORE=$(date -j -v-1d -f "%Y-%m-%d" "$BOUNDARY" "+%Y-%m-%d" 2>/dev/null \
  || date -d "$BOUNDARY - 1 day" "+%Y-%m-%d")

work=$(mktemp -d "${TMPDIR:-/tmp}/redteam.XXXXXX") || exit 2
applied=0
created=""
fails=0
checks=0

restore() {
  if [ "$applied" -eq 1 ]; then
    cp "$work/r.orig" "$root/$R_FILE"
    cp "$work/py.orig" "$root/$PY_FILE"
    applied=0
  fi
  for path in $created; do
    rm -f "$root/$path"
  done
  created=""
  rm -rf "$work"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cp "$R_FILE" "$work/r.orig"
cp "$PY_FILE" "$work/py.orig"

revert_files() {
  cp "$work/r.orig" "$root/$R_FILE"
  cp "$work/py.orig" "$root/$PY_FILE"
  for path in $created; do
    rm -f "$root/$path"
  done
  created=""
}

# The guard, run the way the SOP names it. The exit code printed is make's, not
# pytest's: make reports 2 when a recipe fails, pytest reports 1. The number is
# whatever actually came back, never a number written here.
guard() {
  if command -v make >/dev/null 2>&1; then
    make test-guard > "$1" 2>&1
  else
    uv run --locked pytest tests/guard -q > "$1" 2>&1
  fi
}

# The scan alone, over one path, so that a hit is attributed to the plant and
# not to anything else in the tree.
scan_path() {
  if command -v uv >/dev/null 2>&1; then
    uv run --locked python "$SCAN" --path "$1" > "$2" 2>&1
  else
    python3 "$SCAN" --path "$1" > "$2" 2>&1
  fi
}

# The scan over the whole repository, for the checks that need a count.
scan_all() {
  if command -v uv >/dev/null 2>&1; then
    uv run --locked python "$SCAN" > "$1" 2>&1
  else
    python3 "$SCAN" > "$1" 2>&1
  fi
}

# One assertion. Runs the guard the way the SOP names it, then the scan over the
# planted path alone, and prints the line the guard actually emitted.
assert_caught() {
  label=$1
  path=$2
  code=${3:-GD-04}
  checks=$((checks + 1))
  guard "$work/guard.log"
  guard_exit=$?
  scan_path "$path" "$work/scan.log"
  hit=$(grep -m 1 "^${code} FAIL: ${path}:" "$work/scan.log" | sed "s/^.*${code} FAIL/${code} FAIL/")
  if [ "$guard_exit" -eq 0 ] || [ -z "$hit" ]; then
    printf '[redteam] %s -> NOT CAUGHT: make test-guard exit %s, no %s line for %s\n' \
      "$label" "$guard_exit" "$code" "$path" >&2
    sed -n '1,6p' "$work/scan.log" >&2
    fails=$((fails + 1))
  else
    printf '[redteam] %s -> make test-guard exit %s   %s\n' "$label" "$guard_exit" "$hit"
  fi
}

note() {
  printf '[redteam] %s\n' "$1"
}

# A plant is written to a path nothing else uses, and the script refuses rather
# than overwrite a real file that has appeared there since it was written. The
# revert deletes what the plant created, so an overwrite would destroy work.
refuse_if_present() {
  if [ -e "$1" ] || [ -L "$1" ]; then
    echo "[redteam] refusing: $1 already exists; the red team will not overwrite a real file" >&2
    exit 2
  fi
}

# ------------------------------------------------------- 0. green before anything
note "checking the guard is green before anything is planted"
guard "$work/rest.log"
rest_exit=$?
if [ "$rest_exit" -ne 0 ]; then
  echo "[redteam] FAIL: the guard is red at rest, before a single plant" >&2
  sed -n '1,20p' "$work/rest.log" >&2
  fails=$((fails + 1))
else
  note "make test-guard -> exit $rest_exit at rest, nothing planted"
fi
checks=$((checks + 1))

# ---------------------------------------- 1. the two plants SOP line 1683 names
note "applying $PATCH"
sed "s/@H@/${HELD}/g" "$PATCH" > "$work/rendered.patch"
if ! git apply "$work/rendered.patch" 2>"$work/apply.err"; then
  echo "[redteam] git apply failed; the patch no longer matches the files it plants into" >&2
  sed -n '1,10p' "$work/apply.err" >&2
  exit 1
fi
applied=1

# The planted line numbers are read back from the files, never written by hand,
# so this script stays correct when the stubs become the real script and solver.
r_line=$(grep -n -F "${COL} == '${HELD}'" "$R_FILE" | head -n 1 | cut -d: -f1)
py_line=$(grep -n -F "$VIEW" "$PY_FILE" | head -n 1 | cut -d: -f1)
if [ -z "$r_line" ] || [ -z "$py_line" ]; then
  echo "[redteam] the patch applied but planted nothing the scan bans" >&2
  exit 1
fi

guard "$work/patched.log"
patched_exit=$?
checks=$((checks + 2))
for pair in "${R_FILE}:${r_line}" "${PY_FILE}:${py_line}"; do
  hit=$(grep -m 1 -F "GD-04 FAIL: ${pair} " "$work/patched.log" | sed 's/^.*GD-04 FAIL/GD-04 FAIL/')
  if [ "$patched_exit" -eq 0 ] || [ -z "$hit" ]; then
    printf '[redteam] SOP plant at %s -> NOT CAUGHT: make test-guard exit %s\n' \
      "$pair" "$patched_exit" >&2
    fails=$((fails + 1))
  else
    printf '[redteam] SOP plant -> make test-guard exit %s   %s\n' "$patched_exit" "$hit"
  fi
done
revert_files
applied=0
note "reverted the two SOP plants"

# ------------------------------------------------- 2. the nine evasions, one at a time
# E1. The label spelled in two pieces, parked in a variable, compared there.
{
  printf '\n# late-window label, spelled in two pieces so the string does not repeat\n'
  printf 'HELD <- paste0("%s", "ed")\n' "$FRAG"
  printf 'late_frame <- function(d) dplyr::filter(d, %s == HELD)\n' "$COL"
} >> "$R_FILE"
assert_caught "E1 label in two pieces, compared through a variable" "$R_FILE"
revert_files

# E2. The view name built by an f-string from a variable.
{
  printf '\n\ndef _probe(con: Any) -> Any:\n'
  printf '    split = "%s"\n' "$HELD"
  printf '    view = f"v_pitch_{split}"\n'
  printf '    return con.execute(f"SELECT * FROM {view}").pl()\n'
} >> "$PY_FILE"
assert_caught "E2 view name built by an f-string" "$PY_FILE"
revert_files

# E3. FROM and the table on two lines, in a dbt model.
E3="dbt/models/marts/v_pitch_all__redteam.sql"
refuse_if_present "$E3"
{
  printf -- "-- every pitch in the season, one row per pitch.\n"
  printf "{{ config(materialized='view') }}\n\n"
  printf "SELECT\n    game_pk,\n    plate_x,\n    description\nFROM\n    %s\n" "$FACT"
} > "$E3"
created="$created $E3"
assert_caught "E3 FROM and the table on two lines" "$E3"
revert_files

# E4. A raw read that a comment elsewhere in the file used to forgive.
E4="dbt/models/marts/late_counts__redteam.sql"
refuse_if_present "$E4"
{
  printf -- "-- Sibling of v_pitch_open, which restricts %s = 'open'. This one counts\n" "$COL"
  printf -- "-- every pitch so the totals in the memo reconcile.\n"
  printf "{{ config(materialized='table') }}\n\n"
  printf "SELECT game_pk, count(*) AS pitches FROM %s GROUP BY 1\n" "$FACT"
} > "$E4"
created="$created $E4"
assert_caught "E4 a comment used to forgive the read" "$E4"
revert_files

# E5. A later day, and > the day before the boundary. Same rows, other spelling.
{
  printf '\n\ndef _late(con: Any) -> Any:\n'
  printf '    return con.execute(\n'
  printf '        "SELECT * FROM v_pitch_open "\n'
  printf '        "WHERE official_date >= DATE %s%s%s "\n' "'" "$DAY_AFTER" "'"
  printf '        "   OR official_date > DATE %s%s%s"\n' "'" "$DAY_BEFORE" "'"
  printf '    ).pl()\n'
} >> "$PY_FILE"
assert_caught "E5 a later boundary day, and > the day before" "$PY_FILE"
revert_files

# E6. The same notebook that is caught small, padded past two megabytes by one plot.
E6="notebooks/ch1_explore__redteam.ipynb"
refuse_if_present "$E6"
made_notebooks=0
if [ ! -d notebooks ]; then
  mkdir -p notebooks
  made_notebooks=1
fi
blob=$(head -c 1600000 /dev/urandom | base64 | tr -d '\n')
{
  printf '{\n "cells": [\n  {\n   "cell_type": "code",\n   "outputs": [\n'
  printf '    {"output_type": "display_data",\n     "data": {"image/png": "%s"}}\n' "$blob"
  printf '   ],\n   "source": [\n'
  printf '    "rows = con.execute(\\"SELECT * FROM %s\\").pl()\\n"\n' "$VIEW"
  printf '   ]\n  }\n ],\n "nbformat": 4,\n "nbformat_minor": 5\n}\n'
} > "$E6"
created="$created $E6"
assert_caught "E6 the view in a notebook past two megabytes" "$E6"
revert_files
if [ "$made_notebooks" -eq 1 ]; then
  rmdir notebooks 2>/dev/null
fi

# E7. An importable symlink pointing out of the repository.
E7="src/absump/ch3/probe__redteam.py"
refuse_if_present "$E7"
printf 'def probe(con):\n    return con.execute("SELECT * FROM %s").pl()\n' "$VIEW" \
  > "$work/probe_target.py"
ln -s "$work/probe_target.py" "$E7"
created="$created $E7"
assert_caught "E7 an importable symlink out of the repository" "$E7"
revert_files

# E8. The complement: the routing column against the open label.
{
  printf '\n\ndef _complement(con: Any) -> Any:\n'
  printf '    return con.execute(\n'
  printf '        "SELECT plate_x FROM v_pitch_open WHERE %s %s %sopen%s"\n' "$COL" "$NEQ" "'" "'"
  printf '    ).pl()\n'
} >> "$PY_FILE"
assert_caught "E8 the complement of the open label" "$PY_FILE"
revert_files

# E9. The second fact table, which no rule named.
E9="dbt/models/marts/challenge_all__redteam.sql"
refuse_if_present "$E9"
{
  printf "{{ config(materialized='view') }}\n\n"
  printf "SELECT * FROM %s\n" "$FACT2"
} > "$E9"
created="$created $E9"
assert_caught "E9 the second fact table" "$E9"
revert_files

# ------------------------------- 2b. the nine spellings the R2 red team got past
# Each one was MISSED by the R2 scanner and is planted here so it cannot come
# back. No banned literal is written in this file: every fragment is built at
# run time out of $HELD, $FRAG, $VIEW, $FACT and $BOUNDARY.
PRE=${BOUNDARY%?}
LAST=${BOUNDARY#"$PRE"}

# E10. The label as a quoted literal in chapter code, with no read beside it.
#      GD-05 as the SOP writes it: SOP-final.md line 1757.
{
  printf '\n\ndef _split() -> str:\n'
  printf '    split = "%s"\n' "$HELD"
  printf '    return split\n'
} >> "$PY_FILE"
assert_caught "E10 the label alone in ch3, no read on the line" "$PY_FILE" "GD-05"
revert_files

# E11. The held-out partition read straight off disk, by path.
E11="src/absump/ch3/parquet__redteam.py"
refuse_if_present "$E11"
printf 'def rows(con):\n    return con.execute("SELECT * FROM read_parquet(%sdata/%s/pitch/*.parquet%s)").pl()\n' \
  "'" "$HELD" "'" > "$E11"
created="$created $E11"
assert_caught "E11 the held-out partition read by path" "$E11" "GD-05"
revert_files

# E12. The boundary day built from two fragments, in python.
{
  printf '\n\nFIRST = "%s" + "%s"\n' "$PRE" "$LAST"
  printf 'def _window(con: Any) -> Any:\n'
  printf '    return con.execute("SELECT * FROM staging_pitch WHERE official_date >= " + FIRST).pl()\n'
} >> "$PY_FILE"
assert_caught "E12 the boundary day in two fragments, python" "$PY_FILE"
revert_files

# E13. The same day built by paste() in R.
Y=$(printf '%s' "$BOUNDARY" | cut -d- -f1)
M=$(printf '%s' "$BOUNDARY" | cut -d- -f2)
D=$(printf '%s' "$BOUNDARY" | cut -d- -f3)
{
  printf '\n# the cut day, assembled so the literal does not appear\n'
  printf 'cut_day <- as.Date(paste("%s", "%s", "%s", sep = "-"))\n' "$Y" "$M" "$D"
  printf 'late <- function(d) dplyr::filter(d, official_date >= cut_day)\n'
} >> "$R_FILE"
assert_caught "E13 the boundary day built by paste(), R" "$R_FILE"
revert_files

# E14. A pull window in a config, with no comparison anywhere near it.
E14="config/backfill__redteam.yml"
refuse_if_present "$E14"
{
  printf 'backfill:\n'
  printf '  start: "%s-09-15"\n' "$Y"
  printf '  end: "%s-09-30"\n' "$Y"
} > "$E14"
created="$created $E14"
assert_caught "E14 a pull window through the seal, in a config" "$E14"
revert_files

# E15. A held-out game copied into a fixture. A datum, not a query.
E15="tests/fixtures/late_game__redteam.json"
refuse_if_present "$E15"
printf '{"gamePk": 825412, "officialDate": "%s", "venue": "Wrigley Field"}\n' "$DAY_AFTER" > "$E15"
created="$created $E15"
assert_caught "E15 a held-out game copied into a fixture" "$E15"
revert_files

# E16. The query carried as base64 and decoded at run time.
E16="notebooks/encoded__redteam.ipynb"
refuse_if_present "$E16"
made_notebooks2=0
if [ ! -d notebooks ]; then
  mkdir -p notebooks
  made_notebooks2=1
fi
B64=$(printf 'SELECT * FROM %s' "$VIEW" | base64 | tr -d '\n')
{
  printf '{\n "cells": [\n  {\n   "cell_type": "code",\n   "outputs": [],\n   "source": [\n'
  printf '    "q = base64.b64decode(\\"%s\\").decode()\\n",\n' "$B64"
  printf '    "rows = con.execute(q).pl()\\n"\n'
  printf '   ]\n  }\n ],\n "nbformat": 4,\n "nbformat_minor": 5\n}\n'
} > "$E16"
created="$created $E16"
assert_caught "E16 the query carried as base64 in a notebook" "$E16"
revert_files

# E17. A plot blob whose base64 run abuts the view name in an output cell.
E17="notebooks/abutting__redteam.ipynb"
refuse_if_present "$E17"
abut=$(head -c 700 /dev/urandom | base64 | tr -d '\n' | tr -d '+/=')
{
  printf '{\n "cells": [\n  {\n   "cell_type": "code",\n   "outputs": [\n'
  printf '    {"output_type": "stream", "text": "%s%s"}\n' "$abut" "$VIEW"
  printf '   ],\n   "source": []\n  }\n ],\n "nbformat": 4,\n "nbformat_minor": 5\n}\n'
} > "$E17"
created="$created $E17"
assert_caught "E17 a blob run abutting the view name" "$E17"
revert_files
if [ "$made_notebooks2" -eq 1 ]; then
  rmdir notebooks 2>/dev/null
fi

# E18. The label assembled with jinja's concat operator, in a dbt model.
E18="dbt/models/marts/jinja_label__redteam.sql"
refuse_if_present "$E18"
{
  printf "{%% set held = '%s' ~ 'ed' %%}\n" "$FRAG"
  printf "{{ config(materialized='view') }}\n\n"
  printf "SELECT game_pk FROM {{ ref('stg_pitch') }} WHERE %s = '{{ held }}'\n" "$COL"
} > "$E18"
created="$created $E18"
assert_caught "E18 the label assembled with jinja's ~ operator" "$E18"
revert_files

# E19. The raw fact table parked in a jinja variable and read through it.
E19="dbt/models/marts/jinja_table__redteam.sql"
refuse_if_present "$E19"
{
  printf "{%% set tbl = '%s' %%}\n" "$FACT"
  printf "{{ config(materialized='table') }}\n\n"
  printf "SELECT game_pk, plate_x FROM {{ tbl }}\n"
} > "$E19"
created="$created $E19"
assert_caught "E19 the fact table parked in a jinja variable" "$E19"
revert_files

# E20. A runnable script under an excluded prefix. The R2 finding: the two
#      evidence directories were excluded by path, and one already held a
#      mode-755 installer.
E20="quality/receipts/probe__redteam.sh"
refuse_if_present "$E20"
printf '#!/bin/sh\nduckdb -c "SELECT plate_x FROM %s"\n' "$FACT" > "$E20"
chmod +x "$E20"
created="$created $E20"
assert_caught "E20 an executable under an excluded prefix" "$E20"
revert_files

# ------------------------------------------------------- 3. green after the revert
guard "$work/clean.log"
clean_exit=$?
checks=$((checks + 1))
scan_all "$work/clean_scan.log"
if [ "$clean_exit" -ne 0 ]; then
  printf '[redteam] FAIL: the guard did not come back green after the revert (exit %s)\n' \
    "$clean_exit" >&2
  sed -n '1,20p' "$work/clean.log" >&2
  fails=$((fails + 1))
else
  printf '[redteam] make test-guard -> exit %s   %s\n' "$clean_exit" \
    "$(tail -n 1 "$work/clean_scan.log")"
fi

if [ "$fails" -ne 0 ]; then
  printf 'GD-09 FAIL: %s of %s check(s) failed; the guard does not fail when it should\n' \
    "$fails" "$checks" >&2
  exit 1
fi

printf 'GD-09 pass: %s of %s checks; the guard fails when it should and is green when it should\n' \
  "$checks" "$checks"
exit 0
