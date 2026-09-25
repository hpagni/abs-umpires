"""The number gate: every number in the prose traces to a source.

Owner: SOP step W7.3, the number gate of the W7.1..W7.5 writing standard. W7.2's
checklist rule 6 and W9's WR-07 name this file as their check, and W9.13 runs it.
SOP section 2.8 settles the two earlier designs on one gate here, reading three
sources:

    docs/numbers.json          the generated ledger. `tools/comms/export_numbers.R`
                               writes it from `app/data/*.rds` and `out/tables/*.csv`.
                               `out/tables/headline.csv` is one of those inputs, not a
                               fourth source.
    docs/priorart-numbers.txt  numbers quoted from published work.
    docs/numbers-allow.txt     numbers that are neither, such as budgets and form limits.

WR-07 scope is `abstract/` and `docs/memo/`. A path argument replaces that scope.

What vouches for a number:
  * In the ledger, numeric values only: every number in the JSON, and every string
    that is one number and nothing else. Keys that begin with `_` are notes. Step ids,
    paths and descriptions vouch for nothing, so `"produced_by": "W2.16"` does not
    make 2.16 traceable.
  * In each text file, one number per line, then `#` and a source or reason. SOP
    section 6.6 makes the source comment mandatory for prior-art numbers, and rule 6
    asks a reason for each allowed number. A line that breaks this form fails.

What counts as a number in the prose: a run of digits with optional thousands commas,
decimals, exponent and percent sign, and a sign when the sign is not a dash between
two words. These are labels, not numbers, and are not read: dates, years 1900 to
2039, clock times, URLs, code points, versions like 4.5.2, digits glued to letters
or underscores (MTV1, ch1, Q1, W7.3), all-caps ids with a hyphen (D-16, WR-07,
COVID-19), path segments (lit/04), footnote marks, list numbers, a heading number
before a capitalised title (`## 4.2 Results`), and cross-references such as
`Section 3`, `Table 2` or `Figure 1`. Tables, figures and pages take whole numbers
only, so `the figures 0.826` is read. Code, HTML comments,
front matter and link targets are not prose. Tables, block quotes, list items and
alt text are prose and are read. In HTML, script, style, code, pre, svg and math
are skipped, and indentation means nothing.

Matching: commas, trailing zeros and the percent sign are ignored, so 1,200 and
1200.0 agree. An unsigned number matches a source value of either sign, because
"fell by 0.3" writes the size of -0.3. A signed number must match its sign. There is
no rounding tolerance: the ledger must hold the number as printed.

SOP section 6.6: the gate only sees digits, and rule 6 wants numbers above nine as
digits in claim sentences. Whether a sentence is a claim is a reading judgement, so
a number above nine written as a word prints a `warn` line for the hand check before
each submission. It does not change the exit code.

    uv run --locked python quality/check_numbers.py [path ...]
    uv run --locked python quality/check_numbers.py --selftest

Exit 0 when every number traces and every source line is well formed, 1 on an
untraced number or a bad source, 2 on a usage error or a path that does not exist.
Every run starts with the self-test, so a broken gate cannot pass.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join("docs", "numbers.json")
PRIOR_ART = os.path.join("docs", "priorart-numbers.txt")
ALLOW = os.path.join("docs", "numbers-allow.txt")
DEFAULT_SCOPE = (os.path.join("abstract"), os.path.join("docs", "memo"))
HTML_EXT = (".html", ".htm")
TEXT_EXT = (".md", ".markdown", ".txt", ".qmd", ".rmd")
LABEL = "WR-07"
MINUS = "\u2212"

_DIGITS = r"(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?%?"
# A candidate literal. Whether a leading sign is a sign, and whether the digits are
# a label, is decided in `literals` from the characters around the match.
NUMBER = re.compile(r"[-+" + MINUS + r"]?" + _DIGITS)
# A source-file line body is one of these and nothing else.
ONE_NUMBER = NUMBER

_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
)
# Spans that are labels or markup, blanked out before numbers are read off a line.
NOT_PROSE = re.compile(
    r"`[^`]*`"  # inline code
    r"|\]\([^)]*\)"  # link or image target
    r"|\[\^[^\]]*\]"  # footnote mark
    r"|<[^>]+@[^>]+>|\b[\w.+-]+@[\w-]+\.[\w.]+"  # e-mail address
    r"|<?\bhttps?://[^\s>)]+>?|\bwww\.[^\s>)]+"  # URL
    r"|\bU\+[0-9A-Fa-f]{4,6}\b"  # a Unicode code point
    r"|\b\d{4}-\d{2}-\d{2}(?:T[\d:.+Z-]*)?\b"  # ISO date or timestamp
    r"|\b(?:19|20)\d{2}[-\u2013/](?:(?:19|20)\d{2}|\d{2})\b"  # season range, year-month
    r"|\b\d{1,2}\s+" + _MONTH + r"(?![a-z])"  # 1 October
    r"|\b" + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?\b(?!,\d{3})"  # October 1
    r"|\b(?:19\d{2}|20[0-3]\d)\b(?![.,]\d)"  # a bare year
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b"  # a clock time
    r"|\b\d+(?:\.\d+){2,}\b"  # a version, 4.5.2
    # A cross-reference, or a range of them. Sections and chapters take dotted numbers;
    # tables, figures and pages take whole numbers only, so "the figures 0.826" is read.
    r"|(?i:(?:\bsections?|\bchapters?|\bappendix|\bappendices|\bversion|\bv\.|\u00a7)"
    r"\s*\d+(?:\.\d+)*(?:\s*[-\u2013]\s*\d+(?:\.\d+)*)?)"
    r"|(?i:(?:\btables?|\bfigures?|\bfigs?\.|\bpages?|\bequations?|\beqs?\.|\bfootnotes?"
    r"|\bparts?|\brules?|\bsteps?|\bitems?)\s*\d+(?:\s*[-\u2013]\s*\d+)?(?![.,]?\d))"
)
# Numbers above nine written as words. SOP section 6.6, rule 6: printed for the hand
# check, never counted as a failure.
SPELLED = re.compile(
    r"\b(ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"million|billion|dozen)\b",
    re.I,
)
ALL_CAPS_TAIL = re.compile(r"(?:^|[^\w])[A-Z][A-Z0-9]*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])(?:\s+|$)")
# A heading number is followed by a capitalised title, as in "## 4.2 Results".
NUMBERED_TITLE = r"\d+(?:\.\d+)*\.?(?=\s+[A-Z*_`\[]|\s*$)"
HEADING_NUMBER = re.compile(r"^(#{1,6}\s+)" + NUMBERED_TITLE)
LIST_NUMBER = re.compile(r"^(\s*)\d+[.)](?=\s|$)")
REFERENCE_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+\S")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
TAG = re.compile(r"<(/?)([A-Za-z][\w:-]*)([^>]*)>")
ATTR_TEXT = re.compile(r"""\b(?:alt|title)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)


def normalise(token: str) -> str:
    """One spelling per value, so that 1,200 and 1200 and 1200.0 agree."""
    token = token.strip().replace(",", "").replace(MINUS, "-").rstrip("%").lstrip("+")
    try:
        value = float(token)
    except ValueError:
        return token
    if not math.isfinite(value):
        return token
    if value == int(value):
        return str(int(value))
    return repr(value)


def literals(line: str):
    """Yield (literal, signed) for every number in one line of prose."""
    line = NOT_PROSE.sub(" ", line)
    for match in NUMBER.finditer(line):
        start, text = match.start(), match.group(0)
        signed = text[0] in "+-" + MINUS
        before = line[start - 1] if start > 0 else ""
        if signed and before and (before.isalnum() or before in "_)]."):
            # A hyphen after a word or a digit joins or spans, as in 10-12 or D-16.
            text, start, signed = text[1:], start + 1, False
            before = line[start - 1]
        if before.isalpha() or before == "_":
            continue  # glued to a word: MTV1, ch1, Q1, v2, W7.3
        if text.startswith(".") and (before.isalnum() or before == "."):
            continue  # the tail of a dotted label
        if before == "." and start >= 2 and line[start - 2].isalnum():
            continue  # the tail of a dotted label, W7.1..7.5
        if before and before in "-\u2013" and ALL_CAPS_TAIL.search(line[: start - 1]):
            continue  # an all-caps id: WR-07, BR-1, COVID-19
        if before == "/" and start >= 2 and (line[start - 2].isalpha() or line[start - 2] == "_"):
            continue  # a path segment: lit/04
        after = line[match.end()] if match.end() < len(line) else ""
        if after == "_":
            continue  # glued to an identifier: 2_pass
        yield text, signed


def _tag_text(match) -> str:
    """An inline HTML tag in Markdown reads as its alt and title text."""
    return " " + " ".join(a or b for a, b in ATTR_TEXT.findall(match.group(3))) + " "


def markdown_lines(text: str):
    """Yield (lineno, prose) for the prose lines of a Markdown or plain-text file."""
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    lines = text.split("\n")
    skip_to = 0
    if lines and lines[0].strip() == "---":  # front matter
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                skip_to = i + 1
                break
    fence = None
    prev_blank, in_list, in_code = True, False, False
    for index, raw in enumerate(lines):
        lineno = index + 1
        if index < skip_to:
            continue
        if fence:
            if raw.strip().startswith(fence):
                fence = None
            continue
        found = FENCE.match(raw)
        if found:
            fence = found.group(1)[0] * 3
            prev_blank = False
            continue
        if not raw.strip():
            prev_blank = True
            continue
        indented = raw.startswith("    ") or raw.startswith("\t")
        if indented and (in_code or (prev_blank and not in_list)):
            in_code, prev_blank = True, False  # an indented code block
            continue
        in_code = False
        if not indented:
            if LIST_ITEM.match(raw):
                in_list = True
            elif prev_blank:
                in_list = False
        prev_blank = False
        if REFERENCE_DEF.match(raw):
            continue
        line = raw.strip()
        while line.startswith(">"):
            line = line[1:].lstrip()
        line = HEADING_NUMBER.sub(r"\1", line)
        line = LIST_NUMBER.sub(r"\1", line)
        line = TAG.sub(_tag_text, line)
        yield lineno, line.replace("|", " ")


class _HtmlText(HTMLParser):
    """Collect (lineno, text) from the human-visible text of an HTML file."""

    SKIP = frozenset({"script", "style", "code", "pre", "kbd", "samp", "template", "svg", "math"})
    HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list = []
        self.skip = 0
        self.heading_start = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        lineno = self.getpos()[0]
        for name, value in attrs:
            if name in ("alt", "title") and value:
                self.out.append((lineno, value))
        if tag in self.HEADINGS:
            self.heading_start = True

    def handle_startendtag(self, tag, attrs):
        if tag in self.SKIP:
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip or not data.strip():
            return
        if self.heading_start:
            data = re.sub(r"^\s*" + NUMBERED_TITLE, " ", data)
            self.heading_start = False
        lineno = self.getpos()[0]
        for offset, piece in enumerate(data.split("\n")):
            if piece.strip():
                self.out.append((lineno + offset, piece))


def html_lines(text: str):
    parser = _HtmlText()
    parser.feed(text)
    parser.close()
    return parser.out


def prose_lines(path: str, text: str):
    if path.lower().endswith(HTML_EXT):
        return html_lines(text)
    return list(markdown_lines(text))


def ledger_numbers(data) -> set:
    """Every numeric value in the ledger. Notes, ids, paths and descriptions do not count."""
    values: set = set()
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(v for k, v in item.items() if not str(k).startswith("_"))
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, bool) or item is None:
            continue
        elif isinstance(item, (int, float)):
            if math.isfinite(item):
                values.add(normalise(repr(item)))
        elif isinstance(item, str) and ONE_NUMBER.fullmatch(item.strip()):
            values.add(normalise(item))
    return values


def list_numbers(path: str, rel: str):
    """Read one of the two text sources: (values, problems)."""
    values: set = set()
    problems: list = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            body, hashmark, comment = raw.rstrip("\n").partition("#")
            body = body.strip()
            if not body:
                continue
            if not ONE_NUMBER.fullmatch(body):
                problems.append((rel, lineno, f"source line must be one number, got {body!r}"))
                continue
            if not hashmark or not comment.strip():
                problems.append((rel, lineno, f"{body} has no source or reason after #"))
            values.add(normalise(body))
    return values, problems


def ledger_values(root: str = ROOT):
    """(values, notes, problems) from the three sources under `root`."""
    values: set = set()
    notes: list = []
    problems: list = []
    path = os.path.join(root, LEDGER)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                values |= ledger_numbers(json.load(fh))
        except (OSError, ValueError) as exc:
            problems.append((LEDGER, 0, f"the ledger does not parse as JSON: {exc}"))
    else:
        notes.append(f"{LEDGER} is absent, so no generated number can be traced")
    for rel in (PRIOR_ART, ALLOW):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            notes.append(f"{rel} is absent")
            continue
        found, bad = list_numbers(path, rel)
        values |= found
        problems.extend(bad)
    return values, notes, problems


def traced(literal: str, signed: bool, values: set) -> bool:
    value = normalise(literal)
    if value in values:
        return True
    return not signed and ("-" + value) in values


def scan_text(path: str, text: str, values: set):
    """(untraced, warnings) for one file's text."""
    untraced, warnings = [], []
    for lineno, line in prose_lines(path, text):
        for literal, signed in literals(line):
            if not traced(literal, signed, values):
                untraced.append((path, lineno, literal))
        for word in SPELLED.findall(NOT_PROSE.sub(" ", line)):
            warnings.append((path, lineno, word))
    return untraced, warnings


def scan_file(path: str, values: set):
    with open(path, encoding="utf-8") as fh:
        return scan_text(path, fh.read(), values)


def targets(paths, root: str = ROOT, explicit: bool = True):
    """(files, missing): files to scan, and named paths that do not exist."""
    out, missing = [], []
    for rel in paths:
        full = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if os.path.isfile(full):
            if explicit or full.lower().endswith(HTML_EXT + TEXT_EXT):
                out.append(full)
        elif os.path.isdir(full):
            for base, _dirs, files in os.walk(full):
                out.extend(
                    os.path.join(base, f)
                    for f in sorted(files)
                    if f.lower().endswith(HTML_EXT + TEXT_EXT)
                )
        elif explicit:
            missing.append(rel)
    return sorted(set(out)), missing


def run(args, root: str = ROOT, emit=print) -> int:
    """The gate itself, on `args` or the default scope under `root`."""
    files, missing = targets(args or list(DEFAULT_SCOPE), root, explicit=bool(args))
    if missing:
        for rel in missing:
            emit(f"check_numbers: {rel} does not exist")
        return 2
    values, notes, problems = ledger_values(root)
    for note in notes:
        emit(f"check_numbers: {note}")
    for rel, lineno, message in problems:
        emit(f"{rel}:{lineno}: {LABEL} {message}")
    untraced, warnings = [], []
    for path in files:
        bad, warn = scan_file(path, values)
        untraced.extend(bad)
        warnings.extend(warn)
    for path, lineno, literal in untraced:
        emit(f"{os.path.relpath(path, root)}:{lineno}: {LABEL} {literal} is in no traceable source")
    for path, lineno, word in warnings:
        emit(
            f"{os.path.relpath(path, root)}:{lineno}: {LABEL} warn: {word!r} is a number above "
            "nine in words; rule 6 wants digits in a claim sentence, so check it by hand"
        )
    emit(
        f"check_numbers: {len(files)} file(s), {len(values)} traceable value(s), "
        f"{len(untraced)} untraced literal(s), {len(problems)} bad source line(s), "
        f"{len(warnings)} word-number warning(s)"
    )
    return 1 if untraced or problems else 0


# ------------------------------------------------------------------------ self-test

_LEDGER_FIXTURE = {
    "_what": "fixture ledger, step W7.3, 2.16 and 8.5 appear only in notes",
    "_schema": 8.5,
    "entries": [
        {
            "slot": "BUFFER",
            "value": 0.75,
            "units": "inches",
            "produced_by": "W2.16",
            "source": "out/tables/t8.5.csv",
            "what": "buffer after 2.16 seasons",
        },
        {"slot": "N", "value": "1,200", "units": "counts", "produced_by": "W6.3"},
        {"slot": "SHIFT", "value": -0.3, "units": "pp"},
        {"slot": "CI", "value": {"lo": 2, "hi": 44}, "units": "counts"},
        {"slot": "PENDING", "value": None},
    ],
}
_PRIOR_ART = "99.75  # Clemens, challenged-pitch accuracy, read 2026-09-22\n10,155 # same source\n"
_ALLOW = "# a comment line\n\n500  # the word limit\n"
# name: (text, the literals the gate must flag, exactly)
_CASES = {
    "good.md": (
        "---\ndate: 2026-09-25\nversion: 7.77\n---\n"
        "## 3 Results\n\n"
        "The buffer is 0.75 inches over 1,200 pitches, and 1200.0 is the same count.\n"
        "The rate fell by 0.3 pp and moved -0.3 pp; prior work reports 99.75% on 10155.\n"
        "Written 2026-09-23 at 12:00, on 1 October 2026 and October 1, in 2022-24.\n"
        "See Section 3, Table 21, Figure 13, page 44, sections 5-6, step W7.3,\n"
        "D-16, WR-07, BR-1 and COVID-19.\n"
        "Labels: MTV1, ch12, Q13., P8, v31, lit/04, R 4.5.2, U+2014, x_77 and W7.1..7.5.\n"
        "The range 2-44 holds, and so does 2\u201344.[^13]\n"
        "`8675309 is code` and [a link](https://x.org/777/88.5) and <!-- 31337 -->.\n"
        '<img src="f.png" width="640" alt="a buffer of 0.75 inches">\n\n'
        "    8675309 in an indented code block\n\n"
        "```\n8675309 fenced\n```\n\n"
        "[13]: https://example.org/66\n"
        "1. a list item with 2 pitches\n"
        "| measure | value |\n|---|---|\n| pitches | 1,200 |\n\n"
        "> A quoted 99.75 from prior work.\n",
        set(),
    ),
    "bad_basic.md": ("# Memo\n\nThe effect is 3.14 inches.\n", {"3.14"}),
    "bad_heading.md": ("## 3.14 inches of shift\n\n## 2 Results\n", {"3.14"}),
    "bad_plural_label.md": (
        "The figures 3.14 and 0.75 moved, as did Table 2.5.\n",
        {"3.14", "2.5"},
    ),
    "bad_label_tail.md": ("Table 2 and 3.14 inches, then 0.3 pp. 777 more.\n", {"3.14", "777"}),
    "bad_line_start.md": ("-0.75 inches opens this line.\n", {"-0.75"}),
    "bad_metadata.md": ("The effect is 2.16 inches and 8.5 pp.\n", {"2.16", "8.5"}),
    "bad_sign.md": (
        "It moved -0.75 inches and \u22120.75 inches, then +0.3 pp.\n",
        {"-0.75", "\u22120.75", "+0.3"},
    ),
    "bad_range.md": ("Between 2-777 pitches.\n", {"777"}),
    "bad_list_continuation.md": (
        "- a list item that runs on\n    to a second line with 3.14 in it\n\n"
        "- another item\n\n    a continuation paragraph with 6.28\n",
        {"3.14", "6.28"},
    ),
    "bad_lazy_continuation.md": ("A line\n     continued with 3.14 after it.\n", {"3.14"}),
    "bad_table.md": ("| a | b |\n|---|---|\n| x | 3.14 |\n", {"3.14"}),
    "bad_quote.md": ("> A quote with 3.14 in it.\n", {"3.14"}),
    "bad_year_like.md": ("There were 2,019 of them and 1.5e-9 of error.\n", {"2,019", "1.5e-9"}),
    "good.html": (
        "<html>\n  <head>\n    <title>Memo</title>\n"
        "    <style>p { font-size: 9.5pt; margin: 12px; }</style>\n"
        "    <script>var x = 31337;</script>\n  </head>\n  <body>\n"
        "    <h2>4. Results</h2>\n"
        "    <p>The buffer is 0.75 inches over 1,200 pitches.</p>\n"
        "    <p>Code <code>8675309</code> and <svg><text>0.5</text></svg> are skipped.</p>\n"
        "    <!-- 31337 -->\n"
        '    <img src="f.png" width="640" alt="0.75 inches">\n'
        "  </body>\n</html>\n",
        set(),
    ),
    "bad_indented.html": (
        "<body>\n    <p>\n        The contour moved 3.14 inches.\n    </p>\n</body>\n",
        {"3.14"},
    ),
    "bad_alt.html": ('<p><img src="f.png" alt="a shift of 3.14 inches"></p>\n', {"3.14"}),
}


def selftest() -> int:
    """Fixture test of every path through the gate. Exit 0 when all cases hold."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        memo = os.path.join(tmp, "docs", "memo")
        os.makedirs(memo)
        os.makedirs(os.path.join(tmp, "abstract"))
        with open(os.path.join(tmp, LEDGER), "w", encoding="utf-8") as fh:
            json.dump(_LEDGER_FIXTURE, fh)
        with open(os.path.join(tmp, PRIOR_ART), "w", encoding="utf-8") as fh:
            fh.write(_PRIOR_ART)
        with open(os.path.join(tmp, ALLOW), "w", encoding="utf-8") as fh:
            fh.write(_ALLOW)
        values, notes, problems = ledger_values(tmp)
        if notes or problems:
            failures.append(f"the fixture sources should be clean, got {notes} {problems}")
        want = {"0.75", "1200", "-0.3", "2", "44", "99.75", "10155", "500"}
        if values != want:
            failures.append(f"traceable values {sorted(values)} differ from {sorted(want)}")
        for name, (text, flagged) in _CASES.items():
            path = os.path.join(memo, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            bad, _warn = scan_file(path, values)
            got = {literal for _p, _l, literal in bad}
            if got != flagged:
                failures.append(f"{name}: flagged {sorted(got)}, expected {sorted(flagged)}")
        # A number above nine in words warns and does not fail; nine does not warn.
        words = "Twelve pitches, twenty games, a hundred calls and nine more.\n"
        _bad, warn = scan_text("w.md", words, values)
        if [w for _p, _l, w in warn] != ["Twelve", "twenty", "hundred"] or _bad:
            failures.append(f"word-number warnings were {warn}, expected three")
        # Source lines: one number, then a comment.
        with open(os.path.join(tmp, ALLOW), "a", encoding="utf-8") as fh:
            fh.write("33\n1 2 # two numbers\nabc # no number\n")
        _v, _n, problems = ledger_values(tmp)
        if len(problems) != 3:
            failures.append(f"three bad source lines gave {len(problems)} problem(s): {problems}")
        with open(os.path.join(tmp, LEDGER), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        _v, _n, problems = ledger_values(tmp)
        if not any(rel == LEDGER for rel, _l, _m in problems):
            failures.append("a ledger that does not parse was not reported")
        empty, notes, _p = ledger_values(os.path.join(tmp, "nothing"))
        if len(notes) != 3 or empty:
            failures.append("missing sources were not reported as missing")
        # The command line: default scope, a named file, a missing path.
        quiet = lambda _line: None  # noqa: E731
        os.remove(os.path.join(tmp, LEDGER))
        with open(os.path.join(tmp, ALLOW), "w", encoding="utf-8") as fh:
            fh.write(_ALLOW)
        with open(os.path.join(tmp, LEDGER), "w", encoding="utf-8") as fh:
            json.dump(_LEDGER_FIXTURE, fh)
        for name in list(_CASES):
            if name.startswith("bad"):
                os.remove(os.path.join(memo, name))
        with open(os.path.join(tmp, "abstract", "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("An abstract with 1,200 pitches.\n")
        runs = (
            ([], 0),
            ([os.path.join("docs", "memo", "good.md")], 0),
            ([os.path.join("docs", "memo", "nope.md")], 2),
        )
        for args, code in runs:
            got = run(args, tmp, quiet)
            if got != code:
                failures.append(f"run {args or 'default scope'} exited {got}, expected {code}")
        with open(os.path.join(tmp, "abstract", "a.txt"), "a", encoding="utf-8") as fh:
            fh.write("And 3.14 more.\n")
        if run([], tmp, quiet) != 1:
            failures.append("an untraced number in abstract/a.txt did not fail the default scope")
    for line in failures:
        print(f"check_numbers selftest: {line}")
    count = len(_CASES) + 10
    print(f"check_numbers selftest: {'FAIL' if failures else 'OK'}, {count} cases")
    return 1 if failures else 0


def main(argv) -> int:
    args = argv[1:]
    if args == ["--selftest"]:
        return selftest()
    if any(a.startswith("-") for a in args):
        print("usage: python quality/check_numbers.py [path ...] | --selftest", file=sys.stderr)
        return 2
    if selftest() != 0:
        return 1
    return run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
