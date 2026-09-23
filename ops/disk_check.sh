#!/bin/sh
# ops/disk_check.sh -- SOP step W1.14. The body of `make disk-check`.
#
# Hard floor: 15 GiB free on the data volume. The number is the SOP's own
# (W1.1 preflight, and risk R-25), not a value read from any endpoint.
# ops/preflight.sh asserts the same floor before anything that touches disk;
# this target exists so the floor can be asserted on its own, cheaply.
#
# Exits 0 and prints DISK OK when the floor holds, 1 otherwise.
set -eu

floor_gib=15
vol=/System/Volumes/Data
[ -d "$vol" ] || vol=/

# df -k is POSIX and reports 1024-byte blocks on macOS.
avail_k=$(df -k "$vol" | awk 'NR==2 {print $4}')
avail_gib=$(( avail_k / 1024 / 1024 ))

if [ "$avail_gib" -lt "$floor_gib" ]; then
  echo "DISK FAIL: ${avail_gib} GiB free on $vol, floor is ${floor_gib} GiB" >&2
  exit 1
fi

echo "DISK OK: ${avail_gib} GiB free on $vol, floor ${floor_gib} GiB"
