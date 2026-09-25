#!/usr/bin/env python3
"""WR-20, the buffer rule check.

Owner: SOP step W7.4, the W7.1..W7.5 writing-standard cluster, fleet phase 04.

The rule, SOP section 6 verbatim:

    WR-20 any sentence containing "buffer" and "two inches" must also contain
    "outside", applied to `abstract/`, `PREREGISTRATION.md`,
    `docs/prior-art.md`, `docs/memo/` and `docs/ch1.md`.

Why it exists (SOP, "The buffer rule, stated once, exactly"): the December
2024 umpire labor agreement cut the grading buffer from two inches outside
the zone edge to three-quarters of an inch on either side of it. The old
buffer sat outside the zone only. A sentence that drops "outside" describes a
symmetric change, and a symmetric change does not imply the interior effect
the study is built to detect.

Scope. With no path: the five SOP paths, plus docs/prereg/. The SOP names
PREREGISTRATION.md; the pre-registration annexes live in docs/prereg/, and
quality/prose_lint.py (PREREG_PATHS) and docs/writing-checklist.md rule 2
both read the pre-registration as PREREGISTRATION.md plus docs/prereg/.
Every file under a scoped directory is read, whatever its extension. UTF-8
is read, and UTF-16 or UTF-32 with a byte-order mark. A binary file, such as
a PDF or a PNG, is skipped and counted; the memo PDF's source is
docs/memo/memo.html, which is read. A file with a text extension (.md,
.html, .txt and the like) that cannot be decoded fails the check. A scoped
path that does not exist yet is reported as absent, not failed.

ABS_PROSE_FILES, one path per line, is the CI contract quality/prose_lint.py
honours. When it is set and no path is given, this check reads the listed
files that fall inside its scope. Paths given as arguments are read as named,
inside the scope or not, and a named path that does not exist is a usage
error.

What counts as a sentence. The rule says "any sentence", so this check reads
more than the prose linter does. It reads prose, headings, list items, block
quotes, fenced and indented code, HTML comments, front matter, image alt
text, and the alt, title and aria-label attributes of HTML tags. Each of
those is a unit. A markdown table row is one unit, read together with the
table's header row. An HTML table row is one unit. Units never run into each
other: a list item, a heading, a table row, an HTML block element or a blank
line ends one. Within a unit, sentences are split by quality/prose_lint.py's
split_sentences, the project's one sentence model, and split once more where
a sentence end is followed by a lower-case word that is not an abbreviation.

Matching. Markup a reader does not see is removed first: emphasis, code
backticks, link targets, inline tags and backslash escapes. HTML entities
are decoded. Text is folded with Unicode NFKC. Zero-width characters and soft
hyphens are dropped. Every run of whitespace, including a line break and a
no-break space, becomes one space. The three terms are then matched as
case-insensitive substrings, so "buffers" and "pre_buffer" contain "buffer".
An HTML comment is taken out of its sentence and read as its own unit, since
a reader never sees it.

Notes. A sentence with "buffer", no "outside", and a two-inch phrasing other
than the literal "two inches" ("two-inch", "2 inches", "2 in") is printed as
a note. A note never changes the exit code: the SOP's literal is "two
inches", and the SOP's own abstract template says "the two-inch buffer".

    uv run --locked python quality/checks/wr20.py [path ...]
    uv run --locked python quality/checks/wr20.py --selftest
    uv run --locked python quality/checks/wr20.py --root DIR [path ...]

--root reads DIR as the repository root. The selftest uses it on a
temporary tree.

Exit 0 when no sentence breaks the rule, 1 when one does, 2 on a usage error.
"""

from __future__ import annotations

import codecs
import html
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

sys.dont_write_bytecode = True  # importing prose_lint must not write into quality/

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
import prose_lint  # noqa: E402  the one sentence model, SOP section 2.8

LABEL = "WR-20"
RULE = 'any sentence containing "buffer" and "two inches" must also contain "outside"'
SOP_SCOPE = ("abstract/", "PREREGISTRATION.md", "docs/prior-art.md", "docs/memo/", "docs/ch1.md")
SOP_SCOPE_TEXT = (
    "applied to `abstract/`, `PREREGISTRATION.md`, `docs/prior-art.md`, "
    "`docs/memo/` and `docs/ch1.md`"
)
PREREG_ANNEX = "docs/prereg/"
DEFAULT_SCOPE = (*SOP_SCOPE, PREREG_ANNEX)
SOP_FILE = "sop/SOP-final.md"

BUFFER, TWO_INCHES, OUTSIDE = "buffer", "two inches", "outside"
VARIANT = re.compile(
    r"\btwo(?:[-\u2010-\u2015]|\s)?inch(?:es)?\b"
    r"|(?<![\w.])2(?:\.0)?(?:[-\u2010-\u2015]|\s)?(?:inch(?:es)?|in\b(?!\s*\d))"
    r"|(?<![\w.])2(?:\.0)?\s?(?:\"|\u2033|\u201d)"
)

MARKUP_EXT = (".html", ".htm", ".xhtml", ".svg", ".xml")
MARKDOWN_EXT = (".md", ".markdown", ".qmd", ".rmd", ".mdx")
TEX_EXT = (".tex",)
# A file with one of these extensions that cannot be decoded is a failure, not a skip.
TEXT_EXT = (*MARKUP_EXT, *MARKDOWN_EXT, *TEX_EXT, ".txt", ".rst", ".csv", ".json", ".yml")

PARA = "\u2029"  # a unit break inside a line
ZERO_WIDTH = re.compile("[\u00ad\u180e\u200b\u200c\u200d\u2060\ufeff]")
NEWLINE_ENTITY = re.compile(r"&#0*(?:10|13);|&#[xX]0*[aAdD];|&NewLine;")
BLOCK_TAGS = frozenset(
    re.findall(
        r"\S+",
        "address article aside blockquote body caption center dd details dialog div dl dt "
        "fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 head header hr html legend "
        "li main nav noscript ol option p pre script section style summary table tbody tfoot "
        "thead title tr ul",
    )
)
TAG = re.compile(r"<(/?)([A-Za-z][\w:.-]*)((?:\"[^\"]*\"|'[^']*'|[^'\">])*)>", re.DOTALL)
ATTR = re.compile(
    r"(?<![\w-])(alt|title|aria-label)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))",
    re.IGNORECASE,
)
COMMENT = re.compile(r"<!--(.*?)(?:-->|\Z)", re.DOTALL)
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
ATX = re.compile(r"^\s{0,3}#{1,6}(?:\s+(.*?))?(?:\s+#+)?\s*$")
UNDERLINE = re.compile(r"^\s{0,3}(?:=+|-+)\s*$")
HRULE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s+(.*)$")
QUOTE = re.compile(r"^\s{0,3}>")
QUOTE_MARKS = re.compile(r"^(?:\s{0,3}>\s?)+")
DELIM_ROW = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
LINK_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s")
PIPE = re.compile(r"(?<!\\)\|")

# A second split, after prose_lint's: a sentence end followed by a lower-case word.
# The word before the stop must not be one of these abbreviations or units.
LOWER_SPLIT = re.compile(r"[.!?]+[\"'\u201d\u2019)\]]*\s+(?=[a-z])")
NO_SPLIT = frozenset(
    re.findall(
        r"\S+",
        "e.g i.e etc vs cf al approx ca in ft sq pp p no fig figs eq dr mr ms st mph cm mm "
        "min max resp incl",
    )
)


# ------------------------------------------------------------------ text helpers


def _sub(pattern, text, repl, flags=0):
    """re.sub that keeps every newline of a replaced span, so line numbers hold."""
    rx = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, flags)

    def _one(m):
        body = repl(m) if callable(repl) else m.expand(repl)
        lost = m.group(0).count("\n") - body.count("\n")
        return body + "\n" * lost if lost > 0 else body

    return rx.sub(_one, text)


def _unescape(text: str) -> str:
    """Decode HTML entities without adding a newline."""
    return "\n".join(html.unescape(NEWLINE_ENTITY.sub(" ", x)) for x in text.split("\n"))


def _tags(text: str) -> str:
    """Block tags become unit breaks, attribute text becomes its own unit, other tags go."""
    text = _sub(r"<![^>]*>|<\?[^>]*\?>", text, "")

    def one(m):
        name = m.group(2).lower()
        vals = [a or b or c for _, a, b, c in ATTR.findall(m.group(3))]
        vals = [v for v in vals if v.strip()]
        out = PARA + " ".join(vals) + PARA if vals else ""
        if name == "br" or name == "wbr":
            return out or (" " if name == "br" else "")
        if name in BLOCK_TAGS:
            return PARA + out + PARA
        return out

    return _sub(TAG, text, one)


def _md_inline(text: str) -> str:
    """Markdown as a reader sees it. Every substitution keeps its newlines."""
    t = _sub(r"!\[([^\]]*)\]\([^)]*\)", text, r"\1")
    t = _sub(r"\[([^\]]*)\]\([^)]*\)", t, r"\1")
    t = _sub(r"\[([^\]]*)\]\[[^\]]*\]", t, r"\1")
    t = _sub(r"<(?:https?|mailto|ftp):[^>\s]*>", t, "")
    t = _tags(t)
    t = t.replace("`", "")
    t = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|<>~\"'])", r"\1", t)
    t = t.replace("*", "").replace("~~", "")
    t = re.sub(r"(?<!\w)_+|_+(?!\w)", "", t)
    return _unescape(t)


def _tex_inline(text: str) -> str:
    t = re.sub(r"(?<!\\)~|\\[,;: !]", " ", text)
    t = re.sub(r"\\[A-Za-z]+\*?", "", t)
    return t.replace("{", "").replace("}", "")


def norm(text: str) -> str:
    """The form the three terms are matched in: NFKC, no zero-width, one space, lower case."""
    t = unicodedata.normalize("NFKC", text)
    t = ZERO_WIDTH.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------ units


def _split_para(line: int, text: str):
    """Split a cleaned unit on PARA. Yields (line, text) with the line of each part."""
    pos = 0
    for part in text.split(PARA):
        lead = len(part) - len(part.lstrip())
        if part.strip():
            yield line + text[: pos + lead].count("\n"), part.strip()
        pos += len(part) + 1


def _comments(text: str, units: list):
    """Move each HTML comment into its own unit; blank it out of the text."""

    def one(m):
        line = 1 + text[: m.start()].count("\n")
        units.append((line, m.group(1), "comment"))
        return ""

    return _sub(COMMENT, text, one)


def md_units(text: str):
    """(line, raw text, kind) units of a markdown file."""
    units: list = []
    text = _comments(text, units)
    lines = text.split("\n")
    cur: list = []  # [start line, [raw lines], kind]
    header: list = []
    in_table = False

    def flush():
        if cur and any(x.strip() for x in cur[1]):
            units.append((cur[0], "\n".join(cur[1]), cur[2]))
        cur.clear()

    def start(n, first, kind):
        flush()
        cur.extend([n, [first], kind])

    start_at = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                for j in range(1, i):
                    if lines[j].strip():
                        units.append((j + 1, lines[j], "front"))
                start_at = i + 1
                break

    fence = None
    for idx in range(start_at, len(lines)):
        n, raw = idx + 1, lines[idx]
        s = raw.strip()
        if fence:
            if s.startswith(fence) and not s.strip(fence[0]):
                fence = None
                flush()
            elif not s:
                flush()
            elif cur and cur[2] == "code":
                cur[1].append(raw)
            else:
                start(n, raw, "code")
            continue
        m = FENCE.match(raw)
        if m:
            flush()
            fence = m.group(1)[0] * 3
            continue
        if not s:
            flush()
            in_table, header = False, []
            continue
        nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
        if DELIM_ROW.match(s) and "-" in s and ("|" in s or in_table):
            in_table = True
            continue
        if "|" in s and (
            in_table or s.startswith("|") or (DELIM_ROW.match(nxt.strip()) and "|" in nxt)
        ):
            cells = [c.strip() for c in PIPE.split(s.strip().strip("|"))]
            if not in_table and not header:
                header = cells
                start(n, "; ".join(cells), "table")
            else:
                start(n, "; ".join(header + cells), "table")
            in_table = True
            flush()
            continue
        in_table, header = False, []
        if LINK_DEF.match(s):
            continue
        h = ATX.match(raw)
        if h:
            start(n, h.group(1) or "", "heading")
            flush()
            continue
        if UNDERLINE.match(raw) or HRULE.match(raw):
            flush()
            continue
        if QUOTE.match(raw):
            body = QUOTE_MARKS.sub("", raw)
            if not body.strip():
                flush()
                continue
            h = ATX.match(body)
            li = LIST_ITEM.match(body)
            if h:
                start(n, h.group(1) or "", "heading")
                flush()
            elif li:
                start(n, li.group(1), "quote")
            elif cur and cur[2] == "quote":
                cur[1].append(body)
            else:
                start(n, body, "quote")
            continue
        li = LIST_ITEM.match(raw)
        if li and not (cur and cur[2] != "item" and re.match(r"^\s*(?!1[.)])\d", raw)):
            start(n, li.group(1), "item")  # only "1." may interrupt a paragraph, as in CommonMark
            continue
        if cur:
            cur[1].append(raw)
        else:
            start(n, raw, "para")
    flush()
    return units


def markup_units(text: str):
    """(line, raw text, kind) units of an HTML, SVG or XML file."""
    units: list = []
    text = _comments(text, units)
    text = _unescape(_tags(text))
    for line, part in _split_para(1, text):
        units.append((line, part, "html"))
    return units


def text_units(text: str, tex: bool):
    """(line, raw text, kind) units of a plain text or TeX file: blank lines end a unit."""
    units, cur, first = [], [], 0
    for n, raw in enumerate([*text.split("\n"), ""], 1):
        if raw.strip():
            if not cur:
                first = n
            cur.append(raw)
        elif cur:
            units.append((first, "\n".join(cur), "text"))
            cur = []
    if tex:
        units = [(ln, _tex_inline(re.sub(r"(?<!\\)%.*", "", t)), k) for ln, t, k in units]
        units += [
            (n, m.group(1), "comment")
            for n, raw in enumerate(text.split("\n"), 1)
            for m in [re.search(r"(?<!\\)%(.*)", raw)]
            if m and m.group(1).strip()
        ]
    return units


def clean_units(relpath: str, text: str):
    """Every unit of one file as (line, cleaned text)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    low = relpath.lower()
    if low.endswith(MARKUP_EXT):
        raw = markup_units(text)
    elif low.endswith(MARKDOWN_EXT):
        raw = md_units(text)
    else:
        raw = text_units(text, low.endswith(TEX_EXT))
    out = []
    for line, body, kind in raw:
        if kind in ("html", "text", "code", "front"):
            cleaned = body  # already clean, or read as written: code and front matter
        elif kind == "comment" and not low.endswith(MARKDOWN_EXT):
            cleaned = _unescape(_tags(body))
        else:
            cleaned = _md_inline(body)
        out.extend(_split_para(line, cleaned))
    return out


# ------------------------------------------------------------------ sentences


def sentences(unit: str):
    """(start, end) spans: prose_lint.split_sentences, then the lower-case split."""
    for a, b in prose_lint.split_sentences(unit):
        start = a
        for m in LOWER_SPLIT.finditer(unit, a, b):
            word = re.search(r"([A-Za-z][A-Za-z.]*)$", unit[start : m.start()])
            if word and (word.group(1).lower().rstrip(".") in NO_SPLIT or len(word.group(1)) == 1):
                continue  # an abbreviation, a unit or an initial
            yield start, m.end()
            start = m.end()
        if unit[start:b].strip():
            yield start, b


def scan_text(relpath: str, text: str):
    """Returns (hits, violations, notes). Each item is (line, sentence)."""
    hits, bad, notes = [], [], []
    for line, unit in clean_units(relpath, text):
        for a, b in sentences(unit):
            raw = unit[a:b]
            s = norm(raw)
            low = s.lower()
            if not s or BUFFER not in low:
                continue
            at = line + unit[: a + len(raw) - len(raw.lstrip())].count("\n")
            if TWO_INCHES in low:
                hits.append((at, s))
                if OUTSIDE not in low:
                    bad.append((at, s))
            elif OUTSIDE not in low:
                v = VARIANT.search(low)
                if v:
                    notes.append((at, s, v.group(0)))
    return hits, bad, notes


# ------------------------------------------------------------------ files


def rel(path: str, root: str) -> str:
    return os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")


def in_scope(relpath: str) -> bool:
    return any(relpath == p or (p.endswith("/") and relpath.startswith(p)) for p in DEFAULT_SCOPE)


def _walk(full: str):
    out = []
    for base, dirs, files in os.walk(full):
        dirs[:] = sorted(d for d in dirs if d not in (".git", "__pycache__"))
        out.extend(os.path.join(base, f) for f in sorted(files))
    return out


def targets(root: str, paths):
    """Returns (files, absent, source). Raises FileNotFoundError on a named path that is gone."""
    env = os.environ.get("ABS_PROSE_FILES", "").strip()
    files, absent = [], []
    if paths:
        source = "arguments"
        for item in paths:
            full = item if os.path.isabs(item) else os.path.join(root, item)
            if not os.path.exists(full) and os.path.exists(item):
                full = os.path.abspath(item)
            if os.path.isfile(full):
                files.append(full)
            elif os.path.isdir(full):
                files.extend(_walk(full))
            else:
                raise FileNotFoundError(item)
    elif env:
        source = "ABS_PROSE_FILES"
        for item in (x.strip() for x in env.split("\n")):
            full = item if os.path.isabs(item) else os.path.join(root, item)
            found = [full] if os.path.isfile(full) else _walk(full) if os.path.isdir(full) else []
            files.extend(f for f in found if item and in_scope(rel(f, root)))
    else:
        source = "default scope"
        for item in DEFAULT_SCOPE:
            full = os.path.join(root, item)
            if os.path.isfile(full):
                files.append(full)
            elif os.path.isdir(full):
                files.extend(_walk(full))
            else:
                absent.append(item)
    return sorted(set(files)), absent, source


def read_text(full: str):
    """The file as text, or None when it is not text: UTF-8, or UTF-16 or UTF-32 with a BOM."""
    try:
        with open(full, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    for bom, codec in (
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
    ):
        if data.startswith(bom):
            try:
                return data.decode(codec)
            except UnicodeDecodeError:
                return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def run(root: str, paths):
    files, absent, source = targets(root, paths)
    hits, bad, notes, skipped, unreadable = [], [], [], [], []
    for full in files:
        relpath = rel(full, root)
        text = read_text(full)
        if text is None and relpath.lower().endswith(TEXT_EXT):
            unreadable.append(relpath)
            continue
        if text is None:
            skipped.append(relpath)
            continue
        h, b, n = scan_text(relpath, text)
        hits += [(relpath, *x) for x in h]
        bad += [(relpath, *x) for x in b]
        notes += [(relpath, *x) for x in n]
    return files, absent, source, hits, bad, notes, skipped, unreadable


def _cut(s: str, n: int = 160) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def report(result, out) -> int:
    files, absent, source, hits, bad, notes, skipped, unreadable = result
    for p in unreadable:
        print(
            f"{p}:0: {LABEL}: a text file that cannot be decoded, so it cannot be checked", file=out
        )
    for p, line, s in bad:
        print(
            f'{p}:{line}: {LABEL}: "buffer" and "two inches" without "outside": {_cut(s)}', file=out
        )
    for p, line, s, v in notes:
        print(
            f'{p}:{line}: {LABEL} note, not a failure: "buffer" with "{v}" and no "outside": '
            f"{_cut(s)}",
            file=out,
        )
    print(
        f"wr20: {len(files) - len(skipped)} file(s) from the {source}, {len(hits)} sentence(s) "
        f'with "buffer" and "two inches", {len(bad)} without "outside"; {len(notes)} note(s); '
        f"{len(unreadable)} undecodable; {len(skipped)} non-text file(s) skipped; "
        f"absent: {', '.join(absent) or 'none'}",
        file=out,
    )
    return 1 if bad or unreadable else 0


# ------------------------------------------------------------------ selftest

S_OK = (
    "The December 2024 umpire labor agreement cut the grading buffer from two inches "
    "outside the zone edge to three-quarters of an inch on either side of it."
)

# (name, relpath, text, violations expected, sentences with both terms expected)
CASES = [
    ("SOP sentence passes", "docs/prior-art.md", S_OK + "\n", 0, 1),
    (
        "M1 plain violation",
        "PREREGISTRATION.md",
        "The pre-2025 buffer was two inches wide.\n",
        1,
        1,
    ),
    (
        "M2 docs/prereg annex",
        "docs/prereg/ch1.md",
        "The pre-2025 buffer was two inches wide.\n",
        1,
        1,
    ),
    (
        "M3 unpunctuated bullets",
        "docs/prior-art.md",
        "- Before 2025 the grading buffer was two inches\n- It sat outside the zone edge\n",
        1,
        1,
    ),
    (
        "M4 closing quote then Outside",
        "docs/prior-art.md",
        'The old agreement set the buffer at "two inches." Outside pitches were graded apart.\n',
        1,
        1,
    ),
    (
        "M5 &#160; in HTML",
        "docs/memo/memo.html",
        "<p>The pre-2025 buffer was two&#160;inches wide.</p>\n",
        1,
        1,
    ),
    (
        "M6 heading then outside",
        "docs/prior-art.md",
        "## The two inches buffer\nIt sat outside the zone edge.\n",
        1,
        1,
    ),
    ("M7 capitals", "docs/prior-art.md", "The BUFFER was Two Inches wide.\n", 1, 1),
    ("M8 line wrap", "docs/prior-art.md", "The pre-2025 buffer was two\ninches wide.\n", 1, 1),
    (
        "M9 two paragraphs, no period",
        "docs/memo/memo.html",
        "<p>The pre-2025 buffer was two inches</p>\n<p>Outside the edge it was graded apart.</p>\n",
        1,
        1,
    ),
    (
        "M10 &#xA0; in HTML",
        "docs/memo/memo.html",
        "<p>The pre-2025 buffer was two&#xA0;inches wide.</p>\n",
        1,
        1,
    ),
    ("&nbsp; in markdown", "abstract/a.md", "The buffer was two&nbsp;inches wide.\n", 1, 1),
    ("U+00A0 in markdown", "abstract/a.md", "The buffer was two\u00a0inches wide.\n", 1, 1),
    ("U+202F in markdown", "abstract/a.md", "The buffer was two\u202finches wide.\n", 1, 1),
    ("zero-width space", "abstract/a.md", "The buf\u200bfer was two inches wide.\n", 1, 1),
    ("soft hyphen", "abstract/a.md", "The buf\u00adfer was two inches wide.\n", 1, 1),
    ("fullwidth letters", "abstract/a.md", "The \uff42uffer was two inches wide.\n", 1, 1),
    (
        "emphasis inside the phrase",
        "abstract/a.md",
        "The buffer was **two** _inches_ wide.\n",
        1,
        1,
    ),
    ("code spans", "abstract/a.md", "The `buffer` was `two` `inches` wide.\n", 1, 1),
    (
        "inline tag inside the phrase",
        "abstract/a.md",
        "The buffer was <b>two</b> <i>inches</i> wide.\n",
        1,
        1,
    ),
    ("link text", "abstract/a.md", "The [buffer](https://x.org/a) was two inches wide.\n", 1, 1),
    (
        "outside only in the link target",
        "abstract/a.md",
        "The buffer was [two inches](https://x.org/outside) wide.\n",
        1,
        1,
    ),
    (
        "outside only in a comment",
        "abstract/a.md",
        "The buffer was two inches <!-- outside --> wide.\n",
        1,
        1,
    ),
    (
        "comment is its own unit",
        "abstract/a.md",
        "Text.\n<!-- The buffer was two inches wide. -->\n",
        1,
        1,
    ),
    (
        "markdown table row with header",
        "abstract/a.md",
        "| Years | Buffer |\n|---|---|\n| 2022-2024 | two inches |\n",
        1,
        1,
    ),
    (
        "markdown table row with outside",
        "abstract/a.md",
        "| Years | Buffer |\n|---|---|\n| 2022-2024 | two inches outside the edge |\n",
        0,
        1,
    ),
    ("block quote", "abstract/a.md", "> The buffer was two inches wide.\n", 1, 1),
    ("fenced code", "abstract/a.md", "```\nThe buffer was two inches wide.\n```\n", 1, 1),
    ("front matter", "abstract/a.md", "---\ntitle: The buffer was two inches\n---\nText.\n", 1, 1),
    ("image alt text", "abstract/a.md", "![The buffer was two inches wide](f.png)\n", 1, 1),
    (
        "HTML alt attribute",
        "docs/memo/memo.html",
        '<p>Figure.</p><img src="f.png" alt="The buffer was two inches wide.">\n',
        1,
        1,
    ),
    (
        "HTML list items",
        "docs/memo/memo.html",
        "<ul><li>The buffer was two inches</li><li>outside the edge</li></ul>\n",
        1,
        1,
    ),
    ("br is a space", "docs/memo/memo.html", "<p>The buffer was two<br>inches wide.</p>\n", 1, 1),
    (
        "br keeps the sentence",
        "docs/memo/memo.html",
        "<p>The buffer was two inches<br>outside the edge.</p>\n",
        0,
        1,
    ),
    (
        "SVG text",
        "docs/memo/figs/f.svg",
        '<svg><text x="1">The buffer was two inches wide.</text></svg>\n',
        1,
        1,
    ),
    ("plain text file", "docs/memo/notes.txt", "The buffer was two inches wide.\n", 1, 1),
    ("TeX tilde", "docs/memo/memo.tex", "The buffer was two~inches wide.\n", 1, 1),
    (
        "lower-case start after a stop",
        "abstract/a.md",
        "The buffer was two inches. outside pitches were graded apart.\n",
        1,
        1,
    ),
    (
        "abbreviation keeps the sentence",
        "abstract/a.md",
        "The buffer, e.g. two inches outside the edge, is gone.\n",
        0,
        1,
    ),
    (
        "unit abbreviation keeps the sentence",
        "abstract/a.md",
        "The buffer is 0.75 in. on each side, not two inches outside.\n",
        0,
        1,
    ),
    (
        "two sentences, one with outside",
        "abstract/a.md",
        S_OK + " The buffer was two inches wide.\n",
        1,
        2,
    ),
    (
        "plural and identifier",
        "abstract/a.md",
        "The pre_buffer regime had buffers of two inches.\n",
        1,
        1,
    ),
    (
        "two-inch is a note, not a failure",
        "abstract/a.md",
        "Three regimes: 2022-2024 under the two-inch buffer.\n",
        0,
        0,
    ),
    ("non-breaking hyphen is a note", "abstract/a.md", "The two\u2011inch buffer.\n", 0, 0),
    ("buffer alone", "abstract/a.md", "The buffer changed in 2025.\n", 0, 0),
    ("two inches alone", "abstract/a.md", "The edge moved two inches.\n", 0, 0),
    (
        "outside in another sentence",
        "abstract/a.md",
        "It sat outside the zone. The buffer was two inches.\n",
        1,
        1,
    ),
    ("CRLF line ends", "abstract/a.md", "The buffer was two\r\ninches wide.\r\n", 1, 1),
    (
        "list continuation keeps outside",
        "abstract/a.md",
        "- The buffer was two inches\n  outside the zone edge.\n",
        0,
        1,
    ),
]


def _selftest_cli(failures: list):
    """The command line end to end on a temporary tree."""
    me = os.path.abspath(__file__)
    env = {k: v for k, v in os.environ.items() if k != "ABS_PROSE_FILES"}

    def cli(tmp, *args, extra=None):
        e = dict(env, **(extra or {}))
        r = subprocess.run(
            [sys.executable, me, "--root", tmp, *args], capture_output=True, text=True, env=e
        )
        return r.returncode, r.stdout + r.stderr

    with tempfile.TemporaryDirectory() as tmp:
        for d in ("abstract", "docs/memo/figs", "docs/prereg", "docs/other"):
            os.makedirs(os.path.join(tmp, d))

        def w(p, t, mode="w"):
            with open(os.path.join(tmp, p), mode) as fh:
                fh.write(t)

        w("abstract/a.md", S_OK + "\n")
        w("docs/prior-art.md", S_OK + "\n")
        w("docs/memo/figs/f.png", b"\x89PNG\r\n\x1a\n\0\0", "wb")
        w("docs/other/x.md", "The buffer was two inches wide.\n")  # outside the scope
        code, out = cli(tmp)
        last = out.strip().split("\n")[-1]
        if code != 0 or "2 sentence(s)" not in last or "1 non-text file(s) skipped" not in last:
            failures.append(f"cli: clean tree should exit 0 with 2 hits, got {code}: {last}")
        if "absent: PREREGISTRATION.md, docs/ch1.md" not in last:
            failures.append(f"cli: absent scope paths not reported: {last}")
        if "docs/other/x.md" in out:
            failures.append("cli: a file outside the scope was read")
        w("docs/prereg/ch1.md", "The pre-2025 buffer was two inches wide.\n")
        code, out = cli(tmp)
        if code != 1 or "docs/prereg/ch1.md:1: WR-20:" not in out:
            failures.append(f"cli: a docs/prereg violation should exit 1, got {code}: {out}")
        os.remove(os.path.join(tmp, "docs/prereg/ch1.md"))
        w("PREREGISTRATION.md", "Intro.\n\nThe buffer was\ntwo inches wide.\n")
        code, out = cli(tmp)
        if code != 1 or "PREREGISTRATION.md:3: WR-20:" not in out:
            failures.append(f"cli: line number of a wrapped violation should be 3, got: {out}")
        code, out = cli(tmp, extra={"ABS_PROSE_FILES": "docs/other/x.md\nabstract/a.md\n"})
        if code != 0 or "1 file(s) from the ABS_PROSE_FILES" not in out:
            failures.append(
                f"cli: ABS_PROSE_FILES must read only in-scope files, got {code}: {out}"
            )
        code, out = cli(tmp, "docs/other/x.md")
        if code != 1 or "docs/other/x.md:1: WR-20:" not in out:
            failures.append(f"cli: a named path is read as named, got {code}: {out}")
        w("docs/memo/notes.txt", "The buffer was\ntwo inches wide.\n")
        code, out = cli(tmp)
        if code != 1 or "docs/memo/notes.txt:1: WR-20:" not in out:
            failures.append(f"cli: a .txt file under docs/memo/ must be read, got {code}: {out}")
        os.remove(os.path.join(tmp, "docs/memo/notes.txt"))
        w("docs/memo/memo.html", "<p>The buffer was two inches.</p>\n".encode("utf-16"), "wb")
        code, out = cli(tmp)
        if code != 1 or "docs/memo/memo.html:1: WR-20:" not in out:
            failures.append(f"cli: a UTF-16 file must be decoded and read, got {code}: {out}")
        w("docs/memo/memo.html", "<p>Caf\u00e9.</p>\n".encode("latin-1"), "wb")
        code, out = cli(tmp)
        if code != 1 or "docs/memo/memo.html:0: WR-20:" not in out:
            failures.append(f"cli: an undecodable text file must fail, got {code}: {out}")
        os.remove(os.path.join(tmp, "docs/memo/memo.html"))
        code, out = cli(tmp, "no/such/file.md")
        if code != 2:
            failures.append(f"cli: a named path that is gone should exit 2, got {code}")
        code, out = cli(tmp, "--bogus")
        if code != 2:
            failures.append(f"cli: an unknown flag should exit 2, got {code}")
        w("docs/memo/memo.html", "<p>The buffer was two-inch wide.</p>\n")
        os.remove(os.path.join(tmp, "PREREGISTRATION.md"))
        code, out = cli(tmp)
        if code != 0 or "note, not a failure" not in out or "1 note(s)" not in out:
            failures.append(f"cli: a variant should print a note and exit 0, got {code}: {out}")


def _selftest_sop(root: str, failures: list) -> str:
    if PREREG_ANNEX not in prose_lint.PREREG_PATHS:
        failures.append(f"prose_lint.PREREG_PATHS no longer holds {PREREG_ANNEX}")
    if DEFAULT_SCOPE[: len(SOP_SCOPE)] != SOP_SCOPE:
        failures.append("the default scope does not start with the SOP scope")
    built = "applied to " + ", ".join(f"`{p}`" for p in SOP_SCOPE[:-1])
    if f"{built} and `{SOP_SCOPE[-1]}`" != SOP_SCOPE_TEXT:
        failures.append("SOP_SCOPE and SOP_SCOPE_TEXT disagree")
    path = os.path.join(root, SOP_FILE)
    if not os.path.isfile(path):
        return "sop/SOP-final.md absent, SOP text not compared"
    with open(path, encoding="utf-8") as fh:
        sop = fh.read()
    want = [
        f"**WR-20 {RULE}**, {SOP_SCOPE_TEXT}",
        'contains "buffer" and "two inches" must also contain "outside"',
        f"prose-lint rule (WR-20) {SOP_SCOPE_TEXT}",
    ]
    for w in want:
        if w not in sop:
            failures.append(f"sop/SOP-final.md no longer states: {w}")
    return f"rule text and scope found in sop/SOP-final.md, {len(want)} strings"


def selftest(root: str = ROOT) -> int:
    failures = []
    for name, relpath, text, n_bad, n_hit in CASES:
        hits, bad, _ = scan_text(relpath, text)
        if len(bad) != n_bad or len(hits) != n_hit:
            failures.append(
                f"case {name!r}: expected {n_bad} violation(s) and {n_hit} hit(s), got "
                f"{len(bad)} and {len(hits)}: {bad or hits}"
            )
    _selftest_cli(failures)
    sop_note = _selftest_sop(root, failures)
    for f in failures:
        print("wr20 selftest FAIL: " + f)
    if failures:
        print(f"wr20 selftest: {len(failures)} failure(s)")
        return 1
    print(f"wr20 selftest: {len(CASES)} cases and 12 command-line checks pass; {sop_note}")
    return 0


# ------------------------------------------------------------------ main


def main(argv) -> int:
    root, paths, i = ROOT, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--selftest":
            return selftest(root)
        if a == "--root" and i + 1 < len(argv):
            root, i = os.path.abspath(argv[i + 1]), i + 2
            continue
        if a in ("-h", "--help"):
            print(__doc__)
            return 0
        if a.startswith("-"):
            print(f"wr20: unknown flag {a}", file=sys.stderr)
            return 2
        paths.append(a)
        i += 1
    try:
        result = run(root, paths)
    except FileNotFoundError as exc:
        print(f"wr20: no such path: {exc}", file=sys.stderr)
        return 2
    return report(result, sys.stdout)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
