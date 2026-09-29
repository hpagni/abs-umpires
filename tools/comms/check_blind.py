"""WR-15 and WR-19, the blind-review check. SOP section 6.6; W7.42 runs it by this name.

A front end, not a second linter. SOP section 2.8 keeps one prose linter, so both
rules live in quality/prose_lint.py and this file only runs that linter and keeps
the two blind-review rules:

    WR-15  the files whose text is submitted to SSAC (the abstract, its variants,
           table1, the figure's alt text and submissions/ssac2027/submitted-abstract*.txt)
           carry none of hudson, pagni, ucla, github.com, hpagni, abs-umpires.
    WR-19  while quality/review-window.lock exists, no file reachable from the
           repository root, or one link from it, names the author.

    uv run --locked python tools/comms/check_blind.py [path ...]

Exit 0 clean, 1 on a blind-review violation, 2 on a usage error.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "quality"))

import prose_lint as L  # noqa: E402

BLIND = ("wr15", "wr19")


def main(argv) -> int:
    paths = argv[1:]
    if any(a.startswith("-") for a in paths):
        print("usage: tools/comms/check_blind.py [path ...]", file=sys.stderr)
        return 2
    files, findings, notes, source = L.run(ROOT, paths, False)
    hits = [f for f in findings if f.check in BLIND]
    for note in notes:
        if "WR-15" in note or "WR-19" in note:
            print(note)
    for f in sorted(hits, key=lambda f: (f.path, f.line)):
        print(f.render())
    window = "open" if os.path.exists(os.path.join(ROOT, L.REVIEW_LOCK)) else "closed"
    print(
        f"check_blind: {len(files)} file(s) from the {source}, {len(hits)} blind-review "
        f"violation(s); review window {window}"
    )
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
