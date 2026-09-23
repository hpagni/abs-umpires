#!/usr/bin/env bash
# ops/lint_prose.sh -- the prose gate. `make lint-prose` delegates here.
#
# Owner: SOP step W9.13. Phase 01 builds the three rules the SOP marks as hard
# failures and that need no artifact that does not exist yet:
#
#   WR-01  banned words. The literal list in SOP section W7.2 ("Ban list"),
#          matched whole-word and case-insensitively.
#   WR-03  one claim per sentence: a sentence over 35 words fails.
#   WR-05  a novelty sentence ("first", "no public work", "nobody", "the only")
#          with no citation on the same line or the next one.
#
# The rest of WR-02, WR-04, WR-06 to WR-20 stay with W9.13 in phase 06. They
# need the memo PDF, the numbers ledger, the review-window lock and the P8
# write-up, none of which exist at this commit. This file does not pretend to
# run them and prints, at the end of every run, which rules it did run.
#
# Scope, in the SOP's order: README.md, DECISIONS.md, docs/ and abstract/.
# CI (ops/ci-pending/ci.yml) narrows the scan to the changed files by setting
# ABS_PROSE_FILES, one path per line; that contract is honoured below.
#
# What is not scanned, and why: fenced code blocks and inline code spans, which
# are commands and not prose; blockquote lines, which quote a third party
# verbatim and cannot be rewritten to suit our own ban list; markdown table
# rows and link-reference lines, which are not sentences. Every skip is by
# construction, not by an allowlist of files.
#
#   bash ops/lint_prose.sh              scan the default scope
#   bash ops/lint_prose.sh --selftest   run the fixture test and scan nothing
#
# Exit 0 clean, 1 on any violation, 2 on a usage error.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
PY="${PYTHON:-python3}"

exec "$PY" - ${1+"$@"} <<'EOF_PY'
"""WR-01, WR-03 and WR-05 over the project's human-facing text."""

import os
import re
import sys
import tempfile

# SOP section W7.2, "Ban list", transcribed in the SOP's own order. The entries
# the SOP qualifies in prose ("robust (as a hype adjective)") are carried as the
# bare word; a false positive is fixed by rewording, which is the point.
BANNED = [
    "revolutionary", "groundbreaking", "game-changing", "game changer",
    "cutting-edge", "state-of-the-art", "best-in-class", "seamless",
    "seamlessly", "effortless", "effortlessly", "unlock", "unlocks",
    "leverage", "leveraging", "harness", "harnesses", "empower",
    "supercharge", "elevate", "transformative", "deep dive", "dive into",
    "delve", "unpack", "journey", "landscape", "realm", "tapestry", "lens",
    "boasts", "stands out", "sets apart", "powerful", "innovative",
    "exciting", "thrilled", "proud to", "passionate", "a testament to",
    "needless to say", "it is worth noting", "at the end of the day",
    "in today's world", "the world of", "holistic", "synergy",
    "best practices", "actionable insights", "key takeaway", "robustly",
    "massive", "huge", "incredible", "amazing", "simply put", "basically",
    "essentially", "fundamentally", "arguably", "very", "really", "quite",
    "comprehensive", "unprecedented", "first-of-its-kind", "myriad",
    "plethora", "crucial", "vital", "pivotal", "showcase", "testament",
]
# "robust (as a hype adjective)" is the one entry the SOP qualifies. A bare
# "robust" is legitimate in "robust standard errors", so it is matched only
# where no statistical noun follows it.
HYPE_ROBUST = re.compile(
    r"(?<![\w-])robust(?![\w-])(?!\s+(?:standard|se\b|variance|covariance|"
    r"sandwich|regression|estimator|estimation))",
    re.IGNORECASE,
)
BANNED = sorted(set(BANNED))

MAX_WORDS = 35  # WR-03
# WR-05 fires on a claim of priority, not on every use of the word "first".
# "Sign in first", "time to first byte" and "the first third of 2026" are not
# novelty claims, so the trigger word has to sit in a claim construction: the
# priority word followed, within three words, by a research noun.
CLAIM_NOUN = (
    r"(?:public|published|peer-reviewed|academic|open|work|works|study|studies|"
    r"paper|papers|analysis|analyses|estimate|estimates|model|models|dataset|"
    r"datasets|result|results|treatment|decomposition|replication|source|"
    r"sources|evidence|attempt|implementation)"
)
NOVELTY = {
    "first": r"(?<![\w-])first(?:-of-its-kind)?(?:\s+\S+){0,2}\s+" + CLAIM_NOUN
    + r"|(?<![\w-])first\s+to\s+\S+",
    "the only": r"(?<![\w-])the\s+only(?:\s+\S+){0,2}\s+" + CLAIM_NOUN,
    "no public work": r"(?<![\w-])no\s+public\s+work",
    "nobody": r"(?<![\w-])nobody(?![\w-])",
}
# A citation is a markdown link, a bare URL, a repository path, a bracketed
# reference key, a dated source, or a parenthetical carrying a four-digit year.
CITATION = re.compile(
    r"\]\([^)]+\)|https?://|`?(?:docs|lit|fixtures|research)/[\w./-]+|"
    r"\[[^\]]+\]\[|\b(?:19|20)\d{2}-\d{2}-\d{2}\b|"
    r"\([^)]*\b(?:19|20)\d{2}\b[^)]*\)"
)
DEFAULT_SCOPE = ("README.md", "DECISIONS.md", "docs", "abstract")


def prose_lines(text):
    """Yield (lineno, prose) with code, quotes and table rows removed."""
    fenced = False
    for n, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if fenced or raw.startswith("    ") or raw.startswith("\t"):
            continue
        if stripped.startswith(">") or stripped.startswith("|"):
            continue
        if re.match(r"^\[[^\]]+\]:\s", stripped):
            continue
        yield n, re.sub(r"`[^`]*`", " ", raw)


def sentences(line):
    """Split a prose line into sentences. Abbreviations are not split on."""
    guarded = re.sub(r"\b([A-Z])\.\s", r"\1<DOT> ", line)
    guarded = guarded.replace("e.g.", "e<DOT>g<DOT>").replace("i.e.", "i<DOT>e<DOT>")
    for part in re.split(r"(?<=[.!?])\s+", guarded):
        text = part.replace("<DOT>", ".").strip()
        if text:
            yield text


def words(sentence):
    bare = re.sub(r"^[#>*\-\d.\s]+", "", sentence)
    bare = re.sub(r"[*_`]", "", bare)
    return [w for w in bare.split() if re.search(r"[A-Za-z0-9]", w)]


def scan_text(path, text):
    findings = []
    lines = list(prose_lines(text))
    by_no = dict(lines)
    for lineno, line in lines:
        low = line.lower()
        if HYPE_ROBUST.search(line):
            findings.append((path, lineno, "WR-01", "banned word 'robust' as a hype adjective"))
        for word in BANNED:
            pattern = r"(?<![\w-])" + re.escape(word).replace(r"\ ", r"\s+") + r"(?![\w-])"
            if re.search(pattern, low):
                findings.append((path, lineno, "WR-01", f"banned word {word!r}"))
        for sentence in sentences(line):
            count = len(words(sentence))
            if count > MAX_WORDS:
                findings.append(
                    (path, lineno, "WR-03", f"sentence of {count} words, limit {MAX_WORDS}")
                )
            low_s = sentence.lower()
            hit = next((n for n, pat in NOVELTY.items() if re.search(pat, low_s)), None)
            if hit and not CITATION.search(sentence) and not CITATION.search(by_no.get(lineno + 1, "")):
                findings.append(
                    (path, lineno, "WR-05", f"novelty claim {hit!r} with no citation on this line or the next")
                )
    return findings


def scan_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return scan_text(path, fh.read())
    except OSError as exc:
        return [(path, 0, "WR-00", f"unreadable: {exc}")]


def targets():
    env = os.environ.get("ABS_PROSE_FILES", "").strip()
    roots = [p.strip() for p in env.split("\n") if p.strip()] if env else list(DEFAULT_SCOPE)
    out = []
    for root in roots:
        if os.path.isfile(root) and root.endswith(".md"):
            out.append(root)
        elif os.path.isdir(root):
            for base, _dirs, files in os.walk(root):
                out.extend(
                    os.path.join(base, f) for f in sorted(files) if f.endswith(".md")
                )
    return sorted(set(out))


def selftest():
    """Fixture test: one file that must fail each rule, one that must pass."""
    bad = (
        "# Fixture\n\n"
        "This groundbreaking result is exciting.\n\n"
        "This sentence exists only to run past the limit and it keeps going with "
        "one more clause and then another clause and then another clause and then "
        "another clause and then another clause and yet one more clause at the end.\n\n"
        "This is the first published estimate of the effect.\n"
    )
    good = (
        "# Fixture\n\n"
        "The estimate is 0.9 inches, with a 95% interval of [0.4, 1.4].\n\n"
        "This is the first published estimate of the effect (docs/prior-art.md).\n\n"
        "```\nthis groundbreaking block is code and is not scanned\n```\n\n"
        "> A quoted notice may say anything, including groundbreaking.\n"
    )
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        bad_path = os.path.join(tmp, "bad.md")
        good_path = os.path.join(tmp, "good.md")
        with open(bad_path, "w", encoding="utf-8") as fh:
            fh.write(bad)
        with open(good_path, "w", encoding="utf-8") as fh:
            fh.write(good)
        got = {rule for _p, _l, rule, _m in scan_file(bad_path)}
        for rule in ("WR-01", "WR-03", "WR-05"):
            if rule not in got:
                failures.append(f"selftest: the bad fixture did not trip {rule}")
        clean = scan_file(good_path)
        for item in clean:
            failures.append(f"selftest: the good fixture tripped {item[2]}: {item[3]}")
    for line in failures:
        print(line)
    print(
        "lint-prose selftest: {}".format("FAIL" if failures else "OK, 3 rules, 2 fixtures")
    )
    return 1 if failures else 0


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if argv[1:]:
        print("usage: bash ops/lint_prose.sh [--selftest]", file=sys.stderr)
        return 2
    if selftest() != 0:
        return 1
    files = targets()
    findings = []
    for path in files:
        findings.extend(scan_file(path))
    for path, lineno, rule, message in findings:
        print(f"{path}:{lineno}: {rule} {message}")
    print(
        "lint-prose: {} file(s), {} violation(s); rules run WR-01 WR-03 WR-05; "
        "WR-02 WR-04 WR-06..WR-20 are SOP W9.13, phase 06".format(len(files), len(findings))
    )
    return 1 if findings else 0


sys.exit(main(sys.argv))
EOF_PY
