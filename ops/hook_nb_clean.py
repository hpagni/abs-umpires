#!/usr/bin/env python3
"""ops/hook_nb_clean.py -- the `nb-clean` pre-commit hook. SOP step W1.13.

Strips outputs from staged Jupyter notebooks before they reach a public repo.

Three reasons this is not optional here. A cell output can carry a token or a
signed URL that gitleaks will not recognise. A cell output can carry a slice of
2026 data, which phase 01 forbids and which D-03 keeps out of git for good. And
an execution count changes on every run, so an unstripped notebook produces a
diff on every commit and the review of a real change drowns in it.

What is stripped, per code cell: `outputs` is emptied, `execution_count` is set
to null, and the churn keys under cell `metadata` are dropped. At the notebook
level the `widgets` metadata blob is dropped, because it is a serialised widget
state that can be megabytes and is never source. Nothing else is touched:
kernelspec, language_info, cell source and markdown cells survive unchanged.

The file is rewritten in nbformat's own style, `indent=1` with a trailing
newline, so end-of-file-fixer and trailing-whitespace have nothing left to do.

Usage:
  ops/hook_nb_clean.py [NOTEBOOK ...]

Exit 0 when every notebook was already clean, 1 when one was rewritten. Exit 1
on a rewrite is the pre-commit convention for a fixing hook: the commit stops so
the author restages the cleaned file and sees what changed.

Standard library only, and 3.9-compatible: `language: script` runs this with the
system python3, not with the project venv.
"""

import json
import sys

# Cell metadata that records how a cell was run, not what it is.
CELL_METADATA_CHURN = (
    "collapsed",
    "execution",
    "ExecuteTime",
    "scrolled",
)


def clean_notebook(nb):
    """Strip outputs in place. Return True if anything changed."""
    changed = False

    metadata = nb.get("metadata")
    if isinstance(metadata, dict) and "widgets" in metadata:
        del metadata["widgets"]
        changed = True

    for cell in nb.get("cells", []):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        if cell.get("outputs") or "outputs" not in cell:
            cell["outputs"] = []
            changed = True
        if cell.get("execution_count") is not None:
            cell["execution_count"] = None
            changed = True
        cell_metadata = cell.get("metadata")
        if isinstance(cell_metadata, dict):
            for key in CELL_METADATA_CHURN:
                if key in cell_metadata:
                    del cell_metadata[key]
                    changed = True

    return changed


def process(path):
    """Clean one notebook. Return True if it was rewritten."""
    with open(path, encoding="utf-8") as handle:
        original = handle.read()

    try:
        nb = json.loads(original)
    except ValueError as exc:
        sys.stderr.write(f"NB CLEAN FAIL: {path} is not readable JSON: {exc}\n")
        raise SystemExit(1) from exc

    clean_notebook(nb)
    rewritten = json.dumps(nb, indent=1, ensure_ascii=False, sort_keys=True) + "\n"

    if rewritten == original:
        return False

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(rewritten)
    return True


def main(argv):
    rewritten = [path for path in argv if process(path)]
    if rewritten:
        sys.stderr.write(f"NB CLEAN: stripped outputs from {len(rewritten)} notebook(s).\n")
        for path in rewritten:
            sys.stderr.write(f"  {path}\n")
        sys.stderr.write("Restage them and commit again.\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
