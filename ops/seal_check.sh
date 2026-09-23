#!/bin/sh
# ops/seal_check.sh -- SOP step W1.14. The body of `make seal-check`.
#
# The cheap, data-free half of the seal invariants: it reads no row, opens no
# database and issues no request, so it is safe to run in any phase, including
# phase 01 where reading a single 2026 datum is forbidden.
#
# SOP W9.7 extends this script with layers 3 and 4 of the sealed guard. It
# replaces this file; the Makefile target already delegates here and is not
# edited again.
#
# Checks:
#   1. ABS_SEAL_UNLOCK is not set. SOP rule 0.5.1: only the owner ever sets it,
#      in one shell, after the W9.7 ceremony. An agent shell must never carry it.
#   2. every artifact under out/sealed/ has a sibling provenance.json.
#   3. nothing under out/sealed/ is tracked by git.
#
# Prints SEAL-CHECK OK (3/3) and exits 0, or reports every failure and exits 1.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fails=0

if [ -n "${ABS_SEAL_UNLOCK:-}" ]; then
  echo "SEAL FAIL 1/3: ABS_SEAL_UNLOCK is set in this environment" >&2
  fails=$((fails + 1))
fi

sealed="$root/out/sealed"
if [ -d "$sealed" ]; then
  for f in $(find "$sealed" -type f ! -name '.gitkeep' ! -name 'provenance.json' 2>/dev/null); do
    if [ ! -f "$(dirname "$f")/provenance.json" ]; then
      echo "SEAL FAIL 2/3: no sibling provenance.json for $f" >&2
      fails=$((fails + 1))
    fi
  done
fi

if [ -d "$root/.git" ]; then
  tracked=$(git -C "$root" ls-files out/sealed | grep -v '\.gitkeep$' | wc -l | tr -d ' ')
  if [ "$tracked" != "0" ]; then
    echo "SEAL FAIL 3/3: $tracked tracked file(s) under out/sealed/" >&2
    fails=$((fails + 1))
  fi
fi

if [ "$fails" -ne 0 ]; then
  echo "SEAL-CHECK FAILED ($fails failure(s))" >&2
  exit 1
fi

echo "SEAL-CHECK OK (3/3)"
