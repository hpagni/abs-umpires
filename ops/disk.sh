#!/bin/sh
# ops/disk.sh -- SOP step W1.14. The body of `make disk`.
#
# Reports free space on the data volume and the size of the directories that
# grow: data/, out/, warehouse/, .venv/, renv/. Read-only. No network.
# Risk R-25: free disk is 57 GiB, not 65, so this is reported, not assumed.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
vol=/System/Volumes/Data
[ -d "$vol" ] || vol=/

echo "free space"
df -h "$vol" | sed -n '1p;2p'
echo
echo "directory sizes under $root"
for d in data out warehouse .venv renv; do
  if [ -d "$root/$d" ]; then
    du -sh "$root/$d" 2>/dev/null || echo "  ?    $root/$d"
  fi
done
