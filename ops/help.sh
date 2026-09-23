#!/bin/sh
# ops/help.sh -- SOP step W1.14. The body of `make help`.
#
# Reads the target list out of the Makefile itself, so the two cannot drift.
# A target is listed when its target line carries a `## description` comment.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mf="$root/Makefile"

if [ ! -f "$mf" ]; then
  echo "help: $mf not found" >&2
  exit 1
fi

echo "abs-umpires. GNU Make 3.81. Every target delegates to one script."
echo
awk -F':[^#]*## ' '/^[a-z][a-z0-9-]*:[^=]*## /{printf "  %-20s %s\n", $1, $2}' "$mf"
echo
echo "A target that prints \"not built yet in this phase\" has a placeholder"
echo "script. The comment above it in the Makefile names the step that owns it."
