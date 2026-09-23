#!/usr/bin/env python3
"""Fold quality/steps.d/*.yml into quality/steps.yml, keyed on step id.

SOP section 0.1: every step is registered in quality/steps.yml with an owner and
a verify command. Eight builders register steps in parallel. They must not edit
quality/steps.yml directly, because two concurrent edits lose one of them.

Each builder writes its own file, quality/steps.d/<name>.yml, holding only its own
blocks. This tool merges them:

  sources, in order   quality/steps.yml, if it exists, then quality/steps.d/*.yml
                      sorted by file name
  block               a line matching "- id: <id>" and the lines under it, up to
                      the next block or the end of file
  leading comments    a run of blank and "#" lines before a "- id:" line attaches
                      to the block that follows it, so a comment written above a
                      step travels with that step
  preamble            the text before the first "- id:" line of quality/steps.yml
                      is the file header and is kept verbatim at the top. The same
                      text in a quality/steps.d file attaches to that file's first
                      block instead, so nothing is dropped
  key                 the id. A later source replaces an earlier block with the
                      same id. No other id is ever dropped
  order               the output is sorted by id, W<workstream> then <number> as
                      integers, so W1.2 precedes W1.13

Keyed on id the merge is idempotent: the output re-parses to the same blocks in
the same order, so a second run changes no bytes.

The write is atomic, through a temporary file in the same directory and os.replace,
under an exclusive lock on quality/steps.d/.merge.lock, so two builders running at
once cannot lose each other's work.

Usage:
  python3 quality/merge_steps.py            merge and write quality/steps.yml
  python3 quality/merge_steps.py --check    report what would change, write nothing

--check exits 0 when the file is already merged and 1 when it would change.
"""

import argparse
import fcntl
import os
import re
import sys
import tempfile

ID_LINE = re.compile(r"^-\s+id:\s*(\S+)")
ID_SHAPE = re.compile(r"^W(\d+)\.(\d+)$")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEPS = os.path.join(ROOT, "quality", "steps.yml")
STEPS_D = os.path.join(ROOT, "quality", "steps.d")
LOCK = os.path.join(STEPS_D, ".merge.lock")


def _is_filler(line):
    """True for a blank line or a comment line."""
    s = line.strip()
    return s == "" or s.startswith("#")


def _trim(lines):
    """Drop leading and trailing blank lines. Comments are content, not filler."""
    a, b = 0, len(lines)
    while a < b and lines[a].strip() == "":
        a += 1
    while b > a and lines[b - 1].strip() == "":
        b -= 1
    return lines[a:b]


def parse(text, header_is_preamble):
    """Split one source into (preamble_lines, [(id, block_lines), ...]).

    header_is_preamble decides where the text before the first block goes. True
    for quality/steps.yml, where it is the file header. False for a steps.d file,
    where it attaches to that file's first block.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    starts = [i for i, ln in enumerate(lines) if ID_LINE.match(ln)]
    if not starts:
        return _trim(lines), []

    # Walk back over blank and comment lines, but never past the previous block.
    bounds = []
    for n, i in enumerate(starts):
        floor = starts[n - 1] + 1 if n else 0
        j = i
        while j > floor and _is_filler(lines[j - 1]):
            j -= 1
        bounds.append(j)

    if header_is_preamble:
        preamble = _trim(lines[: starts[0]])
        bounds[0] = starts[0]
    else:
        preamble = []
        bounds[0] = 0

    blocks = []
    for n, start in enumerate(bounds):
        end = bounds[n + 1] if n + 1 < len(bounds) else len(lines)
        body = _trim(lines[start:end])
        if body:
            blocks.append((ID_LINE.match(lines[starts[n]]).group(1), body))
    return preamble, blocks


def sort_key(step_id):
    """W<workstream>.<number> as integers. Anything else sorts after, by string."""
    m = ID_SHAPE.match(step_id)
    if m:
        return (0, int(m.group(1)), int(m.group(2)), "")
    return (1, 0, 0, step_id)


def merge(paths):
    """Read the sources in order and return (preamble, ordered blocks, replacements)."""
    preamble = []
    by_id = {}
    replaced = []
    for path, is_steps_yml in paths:
        with open(path, encoding="utf-8") as fh:
            pre, blocks = parse(fh.read(), is_steps_yml)
        if is_steps_yml:
            preamble = pre
        if not blocks:
            sys.stderr.write(f"merge_steps: no step block in {path}\n")
            continue
        for step_id, body in blocks:
            prior = by_id.get(step_id)
            if prior is not None and prior[1] != body:
                replaced.append((step_id, prior[0], path))
            by_id[step_id] = (path, body)
    ordered = sorted(by_id.items(), key=lambda kv: sort_key(kv[0]))
    return preamble, [(k, v[1]) for k, v in ordered], replaced


def render(preamble, blocks):
    """One trailing newline per line, one blank line between parts."""
    parts = []
    if preamble:
        parts.append("\n".join(preamble) + "\n")
    for _, body in blocks:
        parts.append("\n".join(body) + "\n")
    return "\n".join(parts)


def sources():
    paths = []
    if os.path.exists(STEPS):
        paths.append((STEPS, True))
    if os.path.isdir(STEPS_D):
        for name in sorted(os.listdir(STEPS_D)):
            if name.endswith(".yml"):
                paths.append((os.path.join(STEPS_D, name), False))
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description="Merge quality/steps.d/*.yml into quality/steps.yml.")
    ap.add_argument(
        "--check",
        action="store_true",
        help="report what would change, write nothing, exit 1 if it would change",
    )
    args = ap.parse_args(argv)

    os.makedirs(STEPS_D, exist_ok=True)
    with open(LOCK, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)

        paths = sources()
        if not paths:
            sys.stderr.write("merge_steps: no quality/steps.yml and no quality/steps.d/*.yml\n")
            return 1

        preamble, blocks, replaced = merge(paths)
        new = render(preamble, blocks)

        old = None
        if os.path.exists(STEPS):
            with open(STEPS, encoding="utf-8") as fh:
                old = fh.read()

        for step_id, was, now in replaced:
            sys.stderr.write(
                f"merge_steps: {step_id} replaced, "
                f"{os.path.relpath(was, ROOT)} -> {os.path.relpath(now, ROOT)}\n"
            )

        changed = new != old
        if args.check:
            print(
                f"merge_steps: {len(paths)} source file(s), {len(blocks)} step id(s), "
                f"{'would change' if changed else 'no change'}"
            )
            return 1 if changed else 0

        if changed:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STEPS), prefix=".steps.yml.")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(new)
                os.replace(tmp, STEPS)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        print(
            f"merge_steps: {len(paths)} source file(s), {len(blocks)} step id(s), "
            f"{'rewrote quality/steps.yml' if changed else 'no change'}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
