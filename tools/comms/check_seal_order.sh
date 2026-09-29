#!/bin/sh
# tools/comms/check_seal_order.sh -- SOP W7.10, the seal-order tripwire (GD-12, D-67).
#
# The W7 path for GD-12. There is one implementation, ops/check_seal_order.sh (W1.8):
# it walks every fit receipt under out/ (out/**/provenance.json), open or held out, and
# requires its git_sha to descend from prereg-v1 as pushed to origin, read with
# `git ls-remote`, never from the local tag alone. This file runs it, so the W7 checks
# (W7.42's check_all.sh, scripts/abstract.sh) and the W1 guard cannot drift apart.
#
# The tripwire is proven to fire by tests/guard/test_seal_order_tripwire.py, which
# `make test-guard` and the CI guard job run: eight planted orderings in a scratch
# repository with its own bare origin, each with the exit status it must produce.
#
# Exit 0 the ordering holds; 1 it does not, and the abstract keeps the narrow
# pre-registration sentence (D-67); 2 usage.
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 2
exec sh "$root/ops/check_seal_order.sh" "$@"
