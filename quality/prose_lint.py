"""The prose linter: one implementation for every human-facing text in the repo.

Owner: SOP step W7.1, the W7.1..W7.5 writing-standard cluster, fleet phase 04.

SOP section 2.8 settles two competing linters on this file. It implements the
union of three rule sets:

    W7.2 rules 1 to 11 and the ban list (docs/writing-checklist.md, W7.2)
    W9 WR-01 to WR-08 (SOP section 6.6)
    W8's P8 ban list, applied to docs/p8/** only

Rule by rule, with the SOP threshold and where it applies:

    rule 1           a sentence over 34 words fails; a file whose median
                     sentence is over 22 words fails. Every file.
    WR-03            a sentence over 35 words. Every file. Reported on the
                     rule 1 line, since every WR-03 hit is also a rule 1 hit.
    rule 2, WR-02    a question mark in prose. Exempt only on a line that
                     begins Q1. to Qn. or H1. to Hn. in the pre-registration
                     (PREREGISTRATION.md and docs/prereg/**).
    rule 3, WR-01    the ban list, whole word, case-insensitive. Every file.
    P8 ban list      the P8-only entries, and `roi` in a heading. docs/p8/**.
    rule 4, WR-09    an em dash (U+2014), or `' - '` used as a sentence dash.
    rule 5           a result number (a decimal or a percentage) in a sentence
                     with no bound: 95%, 90%, [, the plus-minus sign, or n = .
                     The result artifacts only (RESULT_FILES below). A
                     labelled number (section 9.1, Python 3.12) and a
                     defining percentage (the 50% contour) are not results.
    rule 6, WR-07    every number traceable. Not run here: SOP section 2.8
                     puts the one number gate at quality/check_numbers.py.
    rule 7, WR-10    no first person in docs/memo/memo.html.
    rule 8, WR-11    the attribution string. --ship only.
    rule 9, WR-12    the prior-art credit. --ship only.
    rule 10          no unfilled {{slot}} and no "coming soon" page. Every
                     file. Under --ship a named artifact that is absent fails.
    rule 11          the direction sentence. --ship only.
    WR-04            "significantly" with no p-value, interval or effect size
                     in the same sentence. Every file.
    WR-05            a novelty sentence with no citation on the same line or
                     the next one. Every file.
    WR-06            a percentage with no denominator. A warning.
    WR-08            passive voice in more than 20% of a file's sentences.
                     A warning.

Rules 8, 9 and 11 ask whether a finished artifact carries a required string.
The artifacts they name are not written yet, so they run under --ship, which
the W7.42 ship gate passes. Every other rule runs on every scan.

Which files rules 5, 8, 9 and 11 cover is not in SOP-final. The sets below
come from the W7 draft that SOP-final condensed into W7.2 (rule 5: memo,
README, portfolio page, resume entry, SSAC abstract; rule 9: memo, README,
portfolio page; rule 11: README and portfolio page). Rule 8 names "every
artifact that shows a number derived from MLB data", read here as the rule 5
set. The app's Methods panel is in rule 9's draft set; it is R code, not a
prose file, and this linter does not read it.

Rule 11 and WR-19 disagree: the direction sentence names the author, and
WR-19 forbids naming the author anywhere in README.md or docs/** while
quality/review-window.lock exists. When the lock exists, rule 11 is not
checked on those paths, and the run says so on its own line.

The ban list. quality/banned.txt is the list (W7.2 writes it). Format: one
entry per line; `#` starts a comment; a line `[p8]` starts the P8-only
section and `[all]` ends it, or a single entry may carry a `p8:` prefix. An
entry may carry a qualifier in parentheses; `robust (as a hype adjective)`
and `roi in any heading` are the two the SOP uses. The SOP W7.2 list is
also built into this file as a floor. The enforced list is the file plus the
floor, and a file that omits a floor entry is itself a finding, so the two
cannot drift apart without a red run. When the file is absent the floor is
used and the run says so.

What is not prose, and is not scanned: fenced and indented code, inline code
spans, blockquotes (a third party's words, quoted verbatim), markdown tables,
link reference lines, HTML comments, and in HTML the script, style, pre,
code, blockquote and table elements.

Scope. With no path: README.md, DECISIONS.md, PREREGISTRATION.md, docs/ and
abstract/, every .md and .html file. ABS_PROSE_FILES, one path per line, is
the CI contract: it replaces the default scope, and a listed path that no
longer exists is skipped as a deletion.

    uv run --locked python quality/prose_lint.py [--ship] [path ...]
    uv run --locked python quality/prose_lint.py --selftest
    uv run --locked python quality/prose_lint.py --list-rules

Exit 0 clean, 1 on any violation, 2 on a usage error. Warnings never change
the exit code.
"""

from __future__ import annotations

import bisect
import html
import os
import re
import statistics
import sys
import tempfile
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANNED_FILE = "quality/banned.txt"
REVIEW_LOCK = "quality/review-window.lock"
DEFAULT_SCOPE = ("README.md", "DECISIONS.md", "PREREGISTRATION.md", "docs", "abstract")
PROSE_EXT = (".md", ".html", ".htm")

MEMO = "docs/memo/memo.html"
README = "README.md"
PORTFOLIO = "docs/portfolio/abs-umpires.md"
RESUME = "docs/resume/entry.html"
ABSTRACT = "abstract/ssac2027_abstract.md"
RESULT_FILES = (MEMO, README, PORTFOLIO, RESUME, ABSTRACT)  # rule 5
ATTRIBUTION_FILES = RESULT_FILES  # rule 8
PRIOR_ART_FILES = (MEMO, README, PORTFOLIO)  # rule 9
DIRECTION_FILES = (README, PORTFOLIO)  # rule 11
FIRST_PERSON_FILES = (MEMO,)  # rule 7, WR-10
PREREG_PATHS = ("PREREGISTRATION.md", "docs/prereg/")  # rule 2 exemption
P8_PREFIX = "docs/p8/"
WR19_REACH = ("README.md", "LICENSE", "CITATION.cff", "docs/", "app/", ".github/")

MAX_WORDS_RULE1 = 34  # rule 1: "one claim per sentence (<=34 words"
MAX_MEDIAN_RULE1 = 22  # rule 1: "file median <=22"
MAX_WORDS_WR03 = 35  # WR-03: "sentence over 35 words"
MAX_PASSIVE_WR08 = 0.20  # WR-08: "passive-voice density above 20% (warn)"

ATTRIBUTION = "Data: MLB Advanced Media and Baseball Savant."  # rule 8
PRIOR_ART_TOKENS = ("use-it-or-lose-it", "99.75%", "10,155", "2026-08-17")  # rule 9
DIRECTION = (  # rule 11
    "research questions, validation design, acceptance criteria and result calls "
    "are Hudson's; Claude Code implemented against them"
)

# SOP section W7.2, "Ban list", in the SOP's order, entry for entry. The P8
# entries follow "P8-only additions applied to `docs/p8/**`".
SOP_BAN = (
    "revolutionary",
    "groundbreaking",
    "game-changing",
    "game changer",
    "cutting-edge",
    "state-of-the-art",
    "best-in-class",
    "seamless",
    "seamlessly",
    "effortless",
    "effortlessly",
    "unlock",
    "unlocks",
    "leverage",
    "leveraging",
    "harness",
    "harnesses",
    "empower",
    "supercharge",
    "elevate",
    "transformative",
    "deep dive",
    "dive into",
    "delve",
    "unpack",
    "journey",
    "landscape",
    "realm",
    "tapestry",
    "lens",
    "boasts",
    "stands out",
    "sets apart",
    "powerful",
    "innovative",
    "exciting",
    "thrilled",
    "proud to",
    "passionate",
    "a testament to",
    "needless to say",
    "it is worth noting",
    "at the end of the day",
    "in today's world",
    "the world of",
    "holistic",
    "synergy",
    "best practices",
    "actionable insights",
    "key takeaway",
    "robust (as a hype adjective)",
    "robustly",
    "massive",
    "huge",
    "incredible",
    "amazing",
    "simply put",
    "basically",
    "essentially",
    "fundamentally",
    "arguably",
    "very",
    "really",
    "quite",
    "comprehensive",
    "unprecedented",
    "first-of-its-kind",
    "myriad",
    "plethora",
    "crucial",
    "vital",
    "pivotal",
    "showcase",
    "testament",
)
SOP_BAN_P8 = (
    "edge",
    "profitable",
    "beat the book",
    "units",
    "alpha",
    "crushing",
    "sharp",
    "+EV",
    "roi in any heading",
)

# "robust" is banned only as a hype adjective; "robust standard errors" is a
# statistical term and stays legal.
HYPE_ROBUST = re.compile(
    r"(?<![\w-])robust(?![\w-])(?!\s+(?:standard|se\b|variance|covariance|"
    r"sandwich|regression|estimator|estimation|inference|check|checks))",
    re.IGNORECASE,
)

# WR-05. A priority word counts only inside a claim construction, so "sign in
# first" and "the first third of 2026" are not novelty claims.
CLAIM_NOUN = (
    r"(?:public|published|peer-reviewed|academic|open|work|works|study|studies|"
    r"paper|papers|analysis|analyses|estimate|estimates|model|models|dataset|"
    r"datasets|result|results|treatment|decomposition|replication|source|"
    r"sources|evidence|attempt|implementation)"
)
NOVELTY = (
    (
        "first",
        re.compile(
            r"(?<![\w-])first(?:-of-its-kind)?(?:\s+\S+){0,2}\s+"
            + CLAIM_NOUN
            + r"(?![\w-])|(?<![\w-])first\s+to\s+\S+",
            re.IGNORECASE,
        ),
    ),
    (
        "the only",
        re.compile(
            r"(?<![\w-])the\s+only(?:\s+\S+){0,2}\s+" + CLAIM_NOUN + r"(?![\w-])", re.IGNORECASE
        ),
    ),
    ("no public work", re.compile(r"(?<![\w-])no\s+public\s+work", re.IGNORECASE)),
    ("nobody", re.compile(r"(?<![\w-])nobody(?![\w-])", re.IGNORECASE)),
)
# A citation: a markdown link, a URL, a repository path, a reference key, a
# dated source, or a parenthesis that carries a four-digit year.
CITATION = re.compile(
    r"\]\([^)]+\)|https?://|`?(?:docs|lit|fixtures|research)/[\w./-]+|"
    r"\[[^\]]+\]\[|\b(?:19|20)\d{2}-\d{2}-\d{2}\b|"
    r"\([^)]*\b(?:19|20)\d{2}\b[^)]*\)"
)

# Rule 5 and WR-06.
RESULT_NUMBER = re.compile(
    r"(?<![\w.,])[-+\u2212]?\d+(?:\.\d+)?\s?%|(?<![\w.,])[-+\u2212]?\d+\.\d+(?!\w|\.\d)"
)
# A number is not a result when a label names it (section 9.1, Python 3.12) or
# when a percentage defines a quantity (the 50% contour, a 95% interval).
NOT_A_RESULT_BEFORE = re.compile(
    r"(?i)\b(?:sections?|§|step|steps|version|release|table|figure|fig\.|rule|rules|item|"
    r"chapter|python|cmdstan|brms|duckdb)\s*$"
)
NOT_A_RESULT_AFTER = re.compile(
    r"(?i)^\s*(?:called-strike\s+)?(?:contour|quantile|percentile|threshold|level|interval|"
    r"credible|confidence|cutoff|probability)\b"
)
BOUND = re.compile(r"95%|90%|\[|±|\bn\s*=\s*\d")
PERCENT = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s?%")
DENOMINATOR = re.compile(r"(?i)\bn\s*=|\bof\b|\bout of\b|/|\bper\b|\bamong\b|\bacross\b|\bin\s+\d")

# WR-04: an adjacent p-value, interval or effect size.
SIGNIFICANTLY = re.compile(r"(?i)(?<![\w-])significantly(?![\w-])")
SIG_SUPPORT = re.compile(
    r"(?i)\bp\s*[<=>≤≥]\s*0?\.\d|\bp-value|\b(?:95|90|99)%|\binterval\b|\bCI\b|±|"
    r"\[\s*[-\u2212]?\d|\d+\.\d+"
)

# WR-08. Past participles that do not end in -ed, listed so "is often" and
# "is when" are not read as passive.
_IRREGULAR = (
    "built made done found shown seen given taken held run read set put kept left "
    "sent told won written drawn chosen known paid lost bought brought caught "
    "taught thought fit cut hit split spent struck understood undertaken "
    "overtaken mistaken broken driven forgotten hidden proven spoken stolen "
    "frozen beaten forbidden withdrawn thrown grown shaken"
)
PASSIVE = re.compile(
    r"(?i)\b(?:am|is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?"
    r"(?:\w{2,}ed|" + "|".join(_IRREGULAR.split()) + r")\b"
)

FIRST_PERSON = re.compile(r"(?i:\b(?:we|our|my|us)\b)|(?<!Type )\bI\b")
SENTENCE_DASH = re.compile(r"(\S) - (\S)")
SLOT = re.compile(r"\{\{")
COMING_SOON = re.compile(r"(?i)(?<![\"'\u201c\u2018])\bcoming soon\b")
QH_LINE = re.compile(r"^[\s*_#>]*[QH]\d+\.")

CODE_TOKEN = "⟨code⟩"
URL_TOKEN = "⟨url⟩"
PARA = "\u2029"  # a block break inside a line, used by the HTML reader
HEAD = "\u2061"  # marks the start of an HTML heading

# check key -> labels printed on the finding line.
LABELS = {
    "r1-len": "rule 1",
    "r1-median": "rule 1",
    "r2": "rule 2, WR-02",
    "r3": "rule 3, WR-01",
    "r3-config": "rule 3, WR-01",
    "p8": "P8 ban list",
    "r4-emdash": "rule 4, WR-09",
    "r4-dash": "rule 4, WR-09",
    "r5": "rule 5",
    "r7": "rule 7, WR-10",
    "r8": "rule 8, WR-11",
    "r9": "rule 9, WR-12",
    "r10": "rule 10",
    "r10-missing": "rule 10",
    "r11": "rule 11",
    "wr04": "WR-04",
    "wr05": "WR-05",
    "wr06": "WR-06",
    "wr08": "WR-08",
    "read": "read",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    check: str
    message: str
    severity: str = "error"  # or "warn"
    extra: tuple = ()

    def render(self) -> str:
        label = ", ".join((LABELS[self.check], *self.extra))
        tail = " (warn)" if self.severity == "warn" else ""
        return f"{self.path}:{self.line}: {label}: {self.message}{tail}"


@dataclass(frozen=True)
class Ban:
    term: str  # lower case
    scope: str  # "all" or "p8"
    kind: str  # "word", "hype" or "heading"


@dataclass
class Seg:
    line: int
    text: str
    heading: bool = False
    new_block: bool = False


@dataclass
class Block:
    lines: list = field(default_factory=list)  # source line of each joined segment
    raw: list = field(default_factory=list)
    heading: bool = False


# ------------------------------------------------------------------ the ban list


def parse_ban_entry(entry: str, scope: str):
    """Return (Ban, note). note is None unless the qualifier is unknown."""
    text = entry.replace("`", "").strip()
    qual = ""
    m = re.match(r"^(.+?)\s*\((.+)\)$", text)
    if m:
        text, qual = m.group(1).strip(), m.group(2).strip().lower()
    else:
        m = re.match(r"^(.+?)\s+(in any heading)$", text, re.IGNORECASE)
        if m:
            text, qual = m.group(1).strip(), m.group(2).lower()
    term = text.lower()
    if "heading" in qual:
        return Ban(term, scope, "heading"), None
    if term == "robust" and "hype" in qual:
        return Ban(term, scope, "hype"), None
    note = f"unknown qualifier {qual!r} on {entry!r}, matched as a bare word" if qual else None
    return Ban(term, scope, "word"), note


def floor_bans():
    bans = [parse_ban_entry(e, "all")[0] for e in SOP_BAN]
    bans += [parse_ban_entry(e, "p8")[0] for e in SOP_BAN_P8]
    return bans


def parse_ban_file(text: str):
    """Parse quality/banned.txt. Returns (bans, notes)."""
    bans, notes, scope = [], [], "all"
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.split("#", 1)[0].strip() if not raw.strip().startswith("#") else ""
        if not line:
            continue
        low = line.lower()
        if low in ("[p8]", "[all]"):
            scope = low[1:-1]
            continue
        entry_scope = scope
        if low.startswith("p8:"):
            entry_scope, line = "p8", line[3:].strip()
        ban, note = parse_ban_entry(line, entry_scope)
        bans.append(ban)
        if note:
            notes.append(f"{BANNED_FILE}:{n}: {note}")
    return bans, notes


def load_bans(root: str):
    """The enforced ban list: quality/banned.txt plus the SOP floor."""
    floor = floor_bans()
    path = os.path.join(root, BANNED_FILE)
    findings, notes = [], []
    if not os.path.isfile(path):
        notes.append(
            f"ban list: {BANNED_FILE} is absent; using the SOP W7.2 list built into "
            f"quality/prose_lint.py ({len(SOP_BAN)} entries, {len(SOP_BAN_P8)} P8-only)"
        )
        return floor, findings, notes
    with open(path, encoding="utf-8") as fh:
        listed, parse_notes = parse_ban_file(fh.read())
    notes.extend(parse_notes)
    have = set(listed)
    for ban in floor:
        if ban not in have:
            where = "the [p8] section of " if ban.scope == "p8" else ""
            findings.append(
                Finding(
                    BANNED_FILE,
                    0,
                    "r3-config",
                    f"SOP W7.2 entry {ban.term!r} ({ban.kind}) is missing from "
                    f"{where}{BANNED_FILE}",
                )
            )
    merged = list(dict.fromkeys(listed + floor))
    notes.append(
        f"ban list: {BANNED_FILE}, {len(listed)} entries, {len(merged)} enforced with the SOP floor"
    )
    return merged, findings, notes


def ban_pattern(terms):
    if not terms:
        return None
    alts = sorted(set(terms), key=len, reverse=True)
    body = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in alts)
    return re.compile(r"(?<![\w-])(" + body + r")(?![\w-])", re.IGNORECASE)


@dataclass
class Context:
    root: str
    bans: list
    ship: bool = False
    review_open: bool = False

    def __post_init__(self):
        words = [b.term for b in self.bans if b.kind == "word"]
        self.word_all = ban_pattern(
            [b.term for b in self.bans if b.kind == "word" and b.scope == "all"]
        )
        self.word_p8 = ban_pattern(
            [b.term for b in self.bans if b.kind == "word" and b.scope == "p8"]
        )
        self.hype_all = any(b.kind == "hype" and b.scope == "all" for b in self.bans)
        self.hype_p8 = any(b.kind == "hype" and b.scope == "p8" for b in self.bans)
        self.head_all = ban_pattern(
            [b.term for b in self.bans if b.kind == "heading" and b.scope == "all"]
        )
        self.head_p8 = ban_pattern(
            [b.term for b in self.bans if b.kind == "heading" and b.scope == "p8"]
        )
        self.n_terms = len(words)


# ------------------------------------------------------------------ reading prose


def keep_newlines(pattern, text, flags=0, repl=""):
    """re.sub that keeps every newline of a removed span, so line numbers hold."""

    def _sub(m):
        body = repl(m) if callable(repl) else repl
        return body + "\n" * m.group(0).count("\n")

    return re.sub(pattern, _sub, text, flags=flags)


def md_segments(text: str):
    text = keep_newlines(r"<!--.*?-->", text, re.DOTALL)
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                start = i + 1
                break
    segs, fence, in_list, prev_blank, indent_code = [], None, False, True, False
    for idx in range(start, len(lines)):
        n, raw = idx + 1, lines[idx]
        s = raw.strip()
        if fence:
            if s.startswith(fence):
                fence = None
            continue
        m = re.match(r"^\s{0,3}(`{3,}|~{3,})", raw)
        if m:
            fence = m.group(1)[:3]
            segs.append(None)
            continue
        if not s:
            segs.append(None)
            prev_blank = True
            continue
        indented = raw.startswith("    ") or raw.startswith("\t")
        if indent_code and indented:
            continue
        indent_code = False
        if indented and not in_list and prev_blank:
            indent_code = True
            segs.append(None)
            continue
        prev_blank = False
        if s.startswith(">") or s.startswith("|"):
            segs.append(None)
            continue
        if re.match(r"^\[[^\]]+\]:\s", s) or re.match(r"^=+$", s):
            continue
        if re.match(r"^(?:[-*_]\s*){3,}$", s):
            segs.append(None)
            continue
        h = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", s)
        if h:
            in_list = False
            segs.append(None)
            segs.append(Seg(n, h.group(1), heading=True, new_block=True))
            segs.append(None)
            continue
        li = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", raw)
        if li:
            in_list = True
            segs.append(Seg(n, li.group(1), new_block=True))
            continue
        if not indented:
            in_list = False
        segs.append(Seg(n, s))
    return segs


BLOCK_TAGS = (
    "p|div|li|ul|ol|dl|dt|dd|tr|td|th|section|article|header|footer|nav|main|"
    "aside|figure|figcaption|br|hr|title|body|html|head|caption|details|summary"
)


def html_segments(text: str):
    text = keep_newlines(r"<!--.*?-->", text, re.DOTALL)
    for tag in ("script", "style", "pre", "code", "template", "svg", "math", "blockquote", "table"):
        text = keep_newlines(rf"<{tag}\b.*?</{tag}\s*>", text, re.DOTALL | re.IGNORECASE)
    text = keep_newlines(
        r"<a\b[^>]*?href\s*=\s*[\"']([^\"']*)[\"'][^>]*>(.*?)</a\s*>",
        text,
        re.DOTALL | re.IGNORECASE,
        repl=lambda m: f"[{m.group(2)}]({m.group(1)})".replace("\n", " "),
    )
    text = re.sub(r"<h[1-6]\b[^>]*>", PARA + HEAD, text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]\s*>", PARA, text, flags=re.IGNORECASE)
    text = keep_newlines(rf"</?(?:{BLOCK_TAGS})\b[^>]*>", text, re.IGNORECASE, repl=PARA)
    text = keep_newlines(r"<[^>]+>", text)
    text = html.unescape(text)
    segs, in_head = [], False
    for n, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            segs.append(None)
            continue
        for i, part in enumerate(line.split(PARA)):
            if i > 0:
                segs.append(None)
                in_head = False
            if part.startswith(HEAD):
                in_head, part = True, part[len(HEAD) :]
            part = part.replace(HEAD, "").strip()
            if part:
                segs.append(Seg(n, part, heading=in_head))
    return segs


def to_blocks(segs):
    blocks, cur = [], None
    for seg in segs:
        if seg is None:
            cur = None
            continue
        if cur is None or seg.new_block or seg.heading != cur.heading:
            cur = Block(heading=seg.heading)
            blocks.append(cur)
        cur.lines.append(seg.line)
        cur.raw.append(seg.text)
    return blocks


def inline_clean(text: str) -> str:
    """Prose as a reader sees it. Every substitution keeps its newlines."""
    t = text.replace("\u00a0", " ").replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("“", '"').replace("”", '"')
    t = keep_newlines(r"`+[^`]*`+", t, re.DOTALL, repl=CODE_TOKEN)
    t = keep_newlines(r"!\[([^\]]*)\]\([^)]*\)", t, repl=lambda m: m.group(1))
    t = keep_newlines(r"\[([^\]]*)\]\([^)]*\)", t, repl=lambda m: m.group(1))
    t = keep_newlines(r"\[([^\]]*)\]\[[^\]]*\]", t, repl=lambda m: m.group(1))
    t = keep_newlines(r"<https?://[^>]+>", t, repl=URL_TOKEN)
    t = re.sub(r"https?://[^\s)>\]]+", URL_TOKEN, t)
    t = keep_newlines(r"<[^>]+>", t)
    t = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|])", r"\1", t)
    t = re.sub(
        r"\*\*|__|(?<![\w*])\*(?=\S)|(?<=\S)\*(?![\w*])|(?<!\w)_(?=\S)|(?<=\S)_(?!\w)", "", t
    )
    return "\n".join(html.unescape(x).replace("\n", " ") for x in t.split("\n"))


ABBREV = re.compile(
    r"\b(?:e\.g|i\.e|et al|vs|cf|Fig|Figs|Eq|No|Dr|Mr|Ms|St|approx|pp)\.|\b(?:[A-Z]\.){2,}"
)
SPLIT = re.compile(r"[.!?]+[\"')\]]*\s+(?=⟨code⟩|⟨url⟩|\([a-z0-9]{1,4}\)\s|[\"'(\[*_]*[A-Z0-9])")


def split_sentences(text: str):
    """Yield (start, end) spans of sentences in text."""
    guarded = ABBREV.sub(lambda m: m.group(0).replace(".", "\u2024"), text)
    start = 0
    for m in SPLIT.finditer(guarded):
        yield start, m.end()
        start = m.end()
    if text[start:].strip():
        yield start, len(text)


def count_words(sentence: str) -> int:
    bare = re.sub(r"[*_`#>]", "", sentence)
    return sum(1 for w in bare.split() if re.search(r"[A-Za-z0-9]", w))


# ------------------------------------------------------------------ the rules


def rel(path: str, root: str) -> str:
    return os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")


def in_set(relpath: str, paths) -> bool:
    return any(relpath == p or (p.endswith("/") and relpath.startswith(p)) for p in paths)


def scan_text(relpath: str, text: str, ctx: Context):
    """All rules over one file's text. relpath is repo-relative with '/'."""
    is_html = relpath.lower().endswith((".html", ".htm"))
    segs = html_segments(text) if is_html else md_segments(text)
    blocks = to_blocks(segs)
    source_lines = text.split("\n")
    p8 = relpath.startswith(P8_PREFIX)
    prereg = in_set(relpath, PREREG_PATHS)
    out = []
    sentence_words, passive = [], 0
    plain_parts = []

    def add(line, check, message, severity="error", extra=()):
        out.append(Finding(relpath, line, check, message, severity, extra))

    for block in blocks:
        raw_joined = "\n".join(block.raw)
        clean = inline_clean(raw_joined)
        plain_parts.append(re.sub(r"[`*]", "", raw_joined))
        nl = [i for i, ch in enumerate(clean) if ch == "\n"]

        def line_at(offset, _nl=nl, _lines=block.lines):
            return _lines[bisect.bisect_left(_nl, offset)]

        # Line rules: 2, 4, 7, 10.
        for k, (line_no, seg_clean) in enumerate(zip(block.lines, clean.split("\n"), strict=True)):
            if "?" in seg_clean and not (prereg and QH_LINE.match(block.raw[k])):
                add(
                    line_no,
                    "r2",
                    "question mark outside a Q<n>. or H<n>. line of the pre-registration",
                )
            if "\u2014" in seg_clean:
                add(line_no, "r4-emdash", "em dash (U+2014)")
            for m in SENTENCE_DASH.finditer(seg_clean):
                if not (m.group(1).isdigit() and m.group(2).isdigit()):
                    add(line_no, "r4-dash", "' - ' used as a sentence dash")
            if in_set(relpath, FIRST_PERSON_FILES):
                for m in FIRST_PERSON.finditer(seg_clean):
                    add(line_no, "r7", f"first person {m.group(0)!r} in the memo")
            if SLOT.search(seg_clean):
                add(line_no, "r10", "unfilled {{slot}}")
            if COMING_SOON.search(seg_clean):
                add(line_no, "r10", "'coming soon'")

        # The ban lists, on the joined block so a phrase broken across lines is caught.
        for pat, check in ((ctx.word_all, "r3"), (ctx.word_p8 if p8 else None, "p8")):
            if pat:
                for m in pat.finditer(clean):
                    add(line_at(m.start()), check, f"banned word {m.group(1).lower()!r}")
        if ctx.hype_all or (p8 and ctx.hype_p8):
            for m in HYPE_ROBUST.finditer(clean):
                add(
                    line_at(m.start()),
                    "r3" if ctx.hype_all else "p8",
                    "banned word 'robust' as a hype adjective",
                )
        if block.heading:
            for pat, check in ((ctx.head_all, "r3"), (ctx.head_p8 if p8 else None, "p8")):
                if pat:
                    for m in pat.finditer(clean):
                        add(
                            line_at(m.start()),
                            check,
                            f"banned word {m.group(1).lower()!r} in a heading",
                        )

        # Sentence rules.
        for start, end in split_sentences(clean):
            sentence = clean[start:end].strip()
            if not sentence:
                continue
            first, last = line_at(start), line_at(max(start, end - 1))
            low = sentence.lower()
            for name, pat in NOVELTY:
                if pat.search(low):
                    span = "\n".join(source_lines[first - 1 : last + 1])
                    if not CITATION.search(span):
                        add(
                            first,
                            "wr05",
                            f"novelty claim {name!r} with no citation on this line or the next",
                        )
                    break
            if block.heading:
                continue
            words = count_words(sentence)
            sentence_words.append(words)
            if words > MAX_WORDS_RULE1:
                extra = ("WR-03",) if words > MAX_WORDS_WR03 else ()
                add(
                    first,
                    "r1-len",
                    f"sentence of {words} words; rule 1 allows {MAX_WORDS_RULE1}, "
                    f"WR-03 fails over {MAX_WORDS_WR03}",
                    extra=extra,
                )
            if PASSIVE.search(sentence):
                passive += 1
            if SIGNIFICANTLY.search(sentence) and not SIG_SUPPORT.search(sentence):
                add(
                    first,
                    "wr04",
                    "'significantly' with no p-value, interval or effect size in the sentence",
                )
            if in_set(relpath, RESULT_FILES) and not BOUND.search(sentence):
                for m in RESULT_NUMBER.finditer(sentence):
                    before = sentence[max(0, m.start() - 12) : m.start()]
                    after = sentence[m.end() : m.end() + 40]
                    if not (
                        NOT_A_RESULT_BEFORE.search(before)
                        or ("%" in m.group(0) and NOT_A_RESULT_AFTER.search(after))
                    ):
                        add(
                            first,
                            "r5",
                            f"result number {m.group(0).strip()!r} with no bound "
                            "(95%, 90%, [, ±, n = )",
                        )
                        break
            pcts = [
                m
                for m in PERCENT.finditer(sentence)
                if m.group(0).replace(" ", "") not in ("95%", "90%")
            ]
            if pcts and not DENOMINATOR.search(sentence):
                add(first, "wr06", f"percentage {pcts[0].group(0)!r} with no denominator", "warn")

    if sentence_words:
        med = statistics.median(sentence_words)
        if med > MAX_MEDIAN_RULE1:
            add(
                0,
                "r1-median",
                f"median sentence length {med:g} words over {len(sentence_words)} sentences; "
                f"rule 1 allows {MAX_MEDIAN_RULE1}",
            )
        share = passive / len(sentence_words)
        if share > MAX_PASSIVE_WR08:
            add(
                0,
                "wr08",
                f"passive voice in {passive} of {len(sentence_words)} sentences, "
                f"{share:.0%}, above {MAX_PASSIVE_WR08:.0%}",
                "warn",
            )

    notes = []
    if ctx.ship:
        plain = re.sub(r"\s+", " ", " ".join(plain_parts)).replace("\u2019", "'")
        if in_set(relpath, ATTRIBUTION_FILES) and ATTRIBUTION not in plain:
            add(0, "r8", f"attribution string missing: {ATTRIBUTION}")
        if in_set(relpath, PRIOR_ART_FILES):
            missing = [
                t
                for t in PRIOR_ART_TOKENS
                if t not in plain and not (t == "10,155" and "10155" in plain)
            ]
            if missing:
                add(0, "r9", "prior-art credit incomplete, missing: " + ", ".join(missing))
        if in_set(relpath, DIRECTION_FILES):
            if ctx.review_open and in_set(relpath, WR19_REACH):
                notes.append(
                    f"{relpath}: rule 11 not checked; {REVIEW_LOCK} exists and WR-19 "
                    "forbids naming the author here"
                )
            elif DIRECTION.lower() not in plain.lower():
                add(0, "r11", "direction sentence missing: " + DIRECTION)
    return out, notes


# ------------------------------------------------------------------ files


def targets(root: str, paths):
    """Resolve the scan list. Returns (files, findings, source)."""
    findings = []
    env = os.environ.get("ABS_PROSE_FILES", "").strip()
    if paths:
        roots, source, skip_missing = list(paths), "arguments", False
    elif env:
        roots, source, skip_missing = (
            [p.strip() for p in env.split("\n") if p.strip()],
            "ABS_PROSE_FILES",
            True,
        )
    else:
        roots, source, skip_missing = list(DEFAULT_SCOPE), "default scope", True
    out = []
    for item in roots:
        full = item if os.path.isabs(item) else os.path.join(root, item)
        if paths and not os.path.exists(full) and os.path.exists(item):
            full = os.path.abspath(item)  # a path given relative to the caller's directory
        if os.path.isfile(full):
            if not paths and not full.lower().endswith(PROSE_EXT):
                continue
            out.append(full)
        elif os.path.isdir(full):
            for base, dirs, files in os.walk(full):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                out.extend(
                    os.path.join(base, f) for f in sorted(files) if f.lower().endswith(PROSE_EXT)
                )
        elif not skip_missing:
            findings.append(Finding(rel(full, root), 0, "r10-missing", "named file does not exist"))
    return sorted(set(out)), findings, source


def run(root: str, paths, ship: bool):
    bans, findings, notes = load_bans(root)
    ctx = Context(
        root, bans, ship=ship, review_open=os.path.exists(os.path.join(root, REVIEW_LOCK))
    )
    files, missing, source = targets(root, paths)
    findings = list(findings) + missing
    for full in files:
        relpath = rel(full, root)
        try:
            with open(full, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(Finding(relpath, 0, "read", f"unreadable: {exc}"))
            continue
        found, file_notes = scan_text(relpath, text, ctx)
        findings.extend(found)
        notes.extend(file_notes)
    return files, findings, notes, source


def summary(files, findings, source, ship) -> str:
    errors = sum(1 for f in findings if f.severity == "error")
    warns = len(findings) - errors
    ship_part = "rules 8, 9, 11 run (--ship)" if ship else "rules 8, 9, 11 not run (no --ship)"
    return (
        f"prose-lint: {len(files)} file(s) from the {source}, {errors} violation(s), "
        f"{warns} warning(s). Ran rules 1 to 5, 7, 10, WR-01 to WR-06, WR-08, WR-09, WR-10 "
        f"and the P8 ban list; {ship_part}; "
        f"rule 6 and WR-07 are quality/check_numbers.py."
    )


RULE_TABLE = """\
check      labels            scope
rule 1     rule 1, WR-03     every file: sentence over 34 words; WR-03 over 35; file median over 22
rule 2     rule 2, WR-02     every file: '?' outside a Q<n>./H<n>. line of the pre-registration
rule 3     rule 3, WR-01     every file: quality/banned.txt plus the SOP W7.2 floor
P8         P8 ban list       docs/p8/**: the P8-only entries; roi in a heading
rule 4     rule 4, WR-09     every file: U+2014, or ' - ' as a sentence dash
rule 5     rule 5            memo, README, portfolio, resume, abstract: result with no bound
rule 6     rule 6, WR-07     quality/check_numbers.py, not this file
rule 7     rule 7, WR-10     docs/memo/memo.html: we, our, my, us, I
rule 8     rule 8, WR-11     --ship; memo, README, portfolio, resume entry, abstract
rule 9     rule 9, WR-12     --ship; memo, README, portfolio
rule 10    rule 10           every file: {{slot}}, 'coming soon'; --ship: a named artifact absent
rule 11    rule 11           --ship; README, portfolio; yields to WR-19 while the review lock exists
WR-04      WR-04             every file: 'significantly' with no p-value, interval or effect size
WR-05      WR-05             every file: novelty claim with no citation on the line or the next
WR-06      WR-06 (warn)      every file: percentage with no denominator
WR-08      WR-08 (warn)      every file: passive voice in over 20% of sentences"""


# ------------------------------------------------------------------ self-test


def _wordy(n: int) -> str:
    return " ".join(["Word"] + ["word"] * (n - 2) + ["end."])


def _cases():
    """(name, relpath, text, must_hit, must_not_hit, ship, review_open)."""
    ok_pad = " Short one here. Another short one."
    good_readme = (
        "# ABS umpires\n\n"
        "The called zone shrank by 0.9 square inches (95% interval [0.4, 1.4]).\n\n"
        "The antecedent is `AyanArora29/use-it-or-lose-it`. Its zone matched ABS on 99.75% of "
        "challenged pitches (n = 10,155).\n"
        "It described the buffer confound on 2026-08-17 ([lit/04](https://example.org/lit/04)).\n\n"
        "Data: MLB Advanced Media and Baseball Savant.\n\n"
        "Research questions, validation design, acceptance criteria and result calls are Hudson's; "
        "Claude Code implemented against them.\n"
    )
    return [
        ("ban word", "docs/a.md", "The result is groundbreaking.", {"r3"}, set(), False, False),
        (
            "ban phrase across a line break",
            "docs/a.md",
            "This is a deep\ndive.",
            {"r3"},
            set(),
            False,
            False,
        ),
        ("robust as hype", "docs/a.md", "The zone is robust.", {"r3"}, set(), False, False),
        (
            "robust as statistics",
            "docs/a.md",
            "The fit uses robust standard errors.",
            set(),
            {"r3"},
            False,
            False,
        ),
        (
            "ban word in code, quote and fence",
            "docs/a.md",
            "Run `groundbreaking` now.\n\n> A groundbreaking quote.\n\n```\ngroundbreaking\n```\n",
            set(),
            {"r3"},
            False,
            False,
        ),
        (
            "P8 word in docs/p8",
            "docs/p8/a.md",
            "The model has an edge.",
            {"p8"},
            set(),
            False,
            False,
        ),
        (
            "P8 word outside docs/p8",
            "docs/a.md",
            "The edge of the zone moved.",
            set(),
            {"p8", "r3"},
            False,
            False,
        ),
        (
            "roi in a P8 heading",
            "docs/p8/a.md",
            "## The ROI\n\nText here.",
            {"p8"},
            set(),
            False,
            False,
        ),
        ("roi in P8 body text", "docs/p8/a.md", "The roi was logged.", set(), {"p8"}, False, False),
        (
            "34-word sentence",
            "docs/a.md",
            _wordy(34) + ok_pad,
            set(),
            {"r1-len", "r1-median"},
            False,
            False,
        ),
        ("35-word sentence", "docs/a.md", _wordy(35) + ok_pad, {"r1-len"}, set(), False, False),
        ("36-word sentence", "docs/a.md", _wordy(36) + ok_pad, {"r1-len"}, set(), False, False),
        (
            "median over 22",
            "docs/a.md",
            " ".join([_wordy(23)] * 3),
            {"r1-median"},
            {"r1-len"},
            False,
            False,
        ),
        (
            "median at 22",
            "docs/a.md",
            " ".join([_wordy(22)] * 3),
            set(),
            {"r1-median"},
            False,
            False,
        ),
        ("rhetorical question", "docs/a.md", "Why does this matter?", {"r2"}, set(), False, False),
        (
            "Q line in the pre-registration",
            "PREREGISTRATION.md",
            "Q1. Does the zone shrink?",
            set(),
            {"r2"},
            False,
            False,
        ),
        (
            "H line in a prereg annex",
            "docs/prereg/ch9.md",
            "- **H2.** Is the effect larger?",
            set(),
            {"r2"},
            False,
            False,
        ),
        (
            "Q line outside the pre-registration",
            "docs/a.md",
            "Q1. Does the zone shrink?",
            {"r2"},
            set(),
            False,
            False,
        ),
        (
            "question mark in URLs",
            "docs/a.md",
            "See https://x.org/a?b=1 for data. See [the page](https://x.org/?q=1) too.",
            set(),
            {"r2"},
            False,
            False,
        ),
        (
            "em dash",
            "docs/a.md",
            "The zone shrank \u2014 by one inch.",
            {"r4-emdash"},
            set(),
            False,
            False,
        ),
        (
            "sentence dash",
            "docs/a.md",
            "The zone shrank - by one inch.",
            {"r4-dash"},
            set(),
            False,
            False,
        ),
        (
            "list marker and numeric range",
            "docs/a.md",
            "- The zone shrank.\n- It moved 3 - 4 inches.",
            set(),
            {"r4-dash"},
            False,
            False,
        ),
        (
            "result with no bound",
            "README.md",
            "The zone shrank by 0.9 inches.",
            {"r5"},
            set(),
            False,
            False,
        ),
        (
            "result at a sentence end",
            "README.md",
            "The zone shrank by 0.9.",
            {"r5"},
            set(),
            False,
            False,
        ),
        (
            "result with a bound",
            "README.md",
            "The zone shrank by 0.9 inches (95% interval [0.4, 1.4]).",
            set(),
            {"r5"},
            False,
            False,
        ),
        ("version string", "README.md", "The runtime is R 4.5.2.", set(), {"r5"}, False, False),
        (
            "defining percentage and a runtime version",
            "README.md",
            "The scale is the 50% called-strike contour. Python 3.12 runs it.",
            set(),
            {"r5"},
            False,
            False,
        ),
        (
            "result outside the result files",
            "docs/a.md",
            "The zone shrank by 0.9 inches.",
            set(),
            {"r5"},
            False,
            False,
        ),
        (
            "first person in the memo",
            MEMO,
            "<p>We find a shift of 0.9 in (n = 400).</p>",
            {"r7"},
            set(),
            False,
            False,
        ),
        (
            "Type I and script in the memo",
            MEMO,
            "<script>var we = 1;</script><p>A Type I error rate of 0.05 (n = 400).</p>",
            set(),
            {"r7"},
            False,
            False,
        ),
        (
            "first person outside the memo",
            "docs/a.md",
            "We fit the model.",
            set(),
            {"r7"},
            False,
            False,
        ),
        ("coming soon", "docs/a.md", "The page is coming soon.", {"r10"}, set(), False, False),
        ("unfilled slot", "docs/a.md", "The value is {{abs_area}}.", {"r10"}, set(), False, False),
        (
            "quoted coming soon",
            "docs/a.md",
            'A "coming soon" page breaks the rule.',
            set(),
            {"r10"},
            False,
            False,
        ),
        (
            "significantly bare",
            "docs/a.md",
            "The zone shrank significantly.",
            {"wr04"},
            set(),
            False,
            False,
        ),
        (
            "significantly with p",
            "docs/a.md",
            "The zone shrank significantly (p < 0.01).",
            set(),
            {"wr04"},
            False,
            False,
        ),
        (
            "novelty with no citation",
            "docs/a.md",
            "This is the first published estimate of the effect.",
            {"wr05"},
            set(),
            False,
            False,
        ),
        (
            "novelty with a citation",
            "docs/a.md",
            "This is the first published estimate (docs/prior-art.md).",
            set(),
            {"wr05"},
            False,
            False,
        ),
        (
            "novelty cited on the next line",
            "docs/a.md",
            "This is the first published estimate.\nSee [the ledger](docs/prior-art.md).",
            set(),
            {"wr05"},
            False,
            False,
        ),
        (
            "sentence split before (b) and code",
            "docs/a.md",
            f"{_wordy(20)} (b) {_wordy(20)} `make prove` {_wordy(20)}",
            set(),
            {"r1-len"},
            False,
            False,
        ),
        (
            "first as an ordinal",
            "docs/a.md",
            "Sign in first. The first third of 2026 is open.",
            set(),
            {"wr05"},
            False,
            False,
        ),
        ("bare percentage", "docs/a.md", "The rate was 40%.", {"wr06"}, set(), False, False),
        (
            "percentage with a denominator",
            "docs/a.md",
            "The rate was 40% of 200 calls.",
            set(),
            {"wr06"},
            False,
            False,
        ),
        (
            "passive density",
            "docs/a.md",
            "The model was fitted. The zone was measured. Hudson ran it. It ran. It ended.",
            {"wr08"},
            set(),
            False,
            False,
        ),
        (
            "active prose",
            "docs/a.md",
            "Hudson fit the model. The zone shrank. It ended.",
            set(),
            {"wr08"},
            False,
            False,
        ),
        (
            "HTML heading and entities",
            RESUME,
            "<h2>Results &amp; methods</h2><p>The zone moved.</p>",
            set(),
            {"r3", "r2", "r5"},
            False,
            False,
        ),
        (
            "ship: bare README",
            "README.md",
            "# Title\n\nThe zone moved.",
            {"r8", "r9", "r11"},
            set(),
            True,
            False,
        ),
        ("ship: finished README", "README.md", good_readme, set(), set(LABELS), True, False),
        (
            "ship: README without the date",
            "README.md",
            good_readme.replace("2026-08-17", "17 August"),
            {"r9"},
            {"r8", "r11"},
            True,
            False,
        ),
        (
            "ship: README without attribution",
            "README.md",
            good_readme.replace("Baseball Savant.", "Savant."),
            {"r8"},
            {"r9", "r11"},
            True,
            False,
        ),
        (
            "ship: README without direction",
            "README.md",
            good_readme.replace("implemented against", "built"),
            {"r11"},
            {"r8", "r9"},
            True,
            False,
        ),
        (
            "ship: review window open",
            "README.md",
            "# Title\n\nThe zone moved.",
            {"r8", "r9"},
            {"r11"},
            True,
            True,
        ),
        (
            "no ship: README",
            "README.md",
            "# Title\n\nThe zone moved.",
            set(),
            {"r8", "r9", "r11"},
            False,
            False,
        ),
    ]


def _module_docstring_ok(ctx):
    """This file's own docstring obeys the rules it enforces."""
    found, _ = scan_text("docs/_prose_lint_docstring.md", __doc__, ctx)
    return [f for f in found if f.check in ("r2", "r3", "r4-emdash", "r4-dash", "wr05")]


def _sop_floor_check(root):
    """Compare the built-in floor with the SOP text, when the private SOP is on disk."""
    path = os.path.join(root, "sop", "SOP-final.md")
    if not os.path.isfile(path):
        return (
            None,
            "SOP transcription check skipped: sop/SOP-final.md is not on disk (clean clone)",
        )
    with open(path, encoding="utf-8") as fh:
        sop = fh.read()
    m = re.search(
        r"^\*\*Ban list\*\* \([^)]*\): (.*?)\. "
        r"P8-only additions applied to `docs/p8/\*\*`: (.*?)\.$",
        sop,
        re.MULTILINE,
    )
    if not m:
        return ["SOP ban-list paragraph not found in sop/SOP-final.md"], None
    general = [x.strip() for x in m.group(1).split(",")]
    p8 = [re.sub(r"^and ", "", x.strip()).replace("`", "") for x in m.group(2).split(",")]
    errs = []
    w72 = sop[sop.index("**W7.2 The writing checklist**") : sop.index("**Ban list**")]
    literal = {
        "rule 1 thresholds": f"≤{MAX_WORDS_RULE1} words, file median ≤{MAX_MEDIAN_RULE1}",
        "rule 8 string": f"`{ATTRIBUTION}`",
        "rule 11 sentence": DIRECTION,
        "rule 9 figures": "quoting 99.75% on 10,155 challenged pitches",
        "rule 9 date": "buffer confound to 2026-08-17",
        "rule 9 name": "naming `use-it-or-lose-it`",
    }
    errs += [f"{k} differs from SOP W7.2: {v!r}" for k, v in literal.items() if v not in w72]
    if tuple(PRIOR_ART_TOKENS) != ("use-it-or-lose-it", "99.75%", "10,155", "2026-08-17"):
        errs.append(f"rule 9 tokens differ from SOP W7.2: {PRIOR_ART_TOKENS}")
    for k, v in {
        "WR-03": f"WR-03 sentence over {MAX_WORDS_WR03} words",
        "WR-08": f"WR-08 passive-voice density above {MAX_PASSIVE_WR08:.0%} (warn)",
    }.items():
        if v not in sop:
            errs.append(f"{k} threshold differs from SOP section 6.6: {v!r}")
    if tuple(general) != SOP_BAN:
        errs.append(
            f"built-in ban list differs from SOP W7.2: {sorted(set(general) ^ set(SOP_BAN))}"
        )
    if tuple(p8) != SOP_BAN_P8:
        errs.append(f"built-in P8 list differs from SOP W7.2: {sorted(set(p8) ^ set(SOP_BAN_P8))}")
    return errs, (
        f"SOP transcription check: {len(general)} entries, {len(p8)} P8 entries and "
        f"{len(literal) + 3} thresholds and strings match sop/SOP-final.md"
    )


def selftest(root: str = ROOT) -> int:
    failures, cases = [], _cases()
    base = Context(root, floor_bans())
    covered = set()
    for name, relpath, text, hit, not_hit, ship, review in cases:
        ctx = Context(root, base.bans, ship=ship, review_open=review)
        found, _ = scan_text(relpath, text, ctx)
        got = {f.check for f in found}
        covered |= hit
        for check in sorted(hit - got):
            failures.append(f"case {name!r}: expected {check}, got {sorted(got) or 'nothing'}")
        for check in sorted(not_hit & got):
            failures.append(
                f"case {name!r}: {check} fired and must not: "
                + "; ".join(f.render() for f in found if f.check == check)
            )
        if name == "35-word sentence" and any("WR-03" in f.extra for f in found):
            failures.append(
                "case '35-word sentence': WR-03 fired at 35 words; it fails only over 35"
            )
        if name == "36-word sentence" and not any(
            "WR-03" in f.extra for f in found if f.check == "r1-len"
        ):
            failures.append("case '36-word sentence': WR-03 did not fire over 35 words")
        if name in ("bare percentage", "passive density") and any(
            f.severity != "warn" for f in found
        ):
            failures.append(f"case {name!r}: WR-06 and WR-08 must be warnings, not violations")

    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "quality"))
        os.makedirs(os.path.join(tmp, "docs", "p8"))
        # A ban file that drops one SOP entry, adds one, and puts the P8 words in their section.
        entries = [e for e in SOP_BAN if e != "delve"] + ["foo"]
        with open(os.path.join(tmp, BANNED_FILE), "w", encoding="utf-8") as fh:
            fh.write(
                "# test ban file\n" + "\n".join(entries) + "\n[p8]\n" + "\n".join(SOP_BAN_P8) + "\n"
            )
        bans, cfg, _ = load_bans(tmp)
        covered.add("r3-config")
        if not any(f.check == "r3-config" and "'delve'" in f.message for f in cfg) or len(cfg) != 1:
            failures.append(
                "ban file: expected one r3-config finding for 'delve', got "
                f"{[f.render() for f in cfg]}"
            )
        ctx = Context(tmp, bans)
        found, _ = scan_text("docs/a.md", "The foo moved. We delve here.", ctx)
        if {f.message for f in found if f.check == "r3"} != {
            "banned word 'foo'",
            "banned word 'delve'",
        }:
            failures.append("ban file: an added entry or the floor entry was not enforced")
        found, _ = scan_text("docs/a.md", "The edge moved.", ctx)
        if found:
            failures.append("ban file: a [p8] entry fired outside docs/p8")
        # A ban file written without the [p8] marker is reported, not silently accepted.
        with open(os.path.join(tmp, BANNED_FILE), "w", encoding="utf-8") as fh:
            fh.write("\n".join(SOP_BAN + SOP_BAN_P8) + "\n")
        _, cfg, _ = load_bans(tmp)
        if len(cfg) != len(SOP_BAN_P8):
            failures.append(
                f"ban file: P8 entries outside [p8] gave {len(cfg)} findings, "
                f"expected {len(SOP_BAN_P8)}"
            )
        os.remove(os.path.join(tmp, BANNED_FILE))

        # The command line, end to end, on a temporary tree.
        with open(os.path.join(tmp, "docs", "good.md"), "w", encoding="utf-8") as fh:
            fh.write("# Good\n\nThe zone moved by one inch.\n")
        with open(os.path.join(tmp, "docs", "bad.md"), "w", encoding="utf-8") as fh:
            fh.write("# Bad\n\nThis groundbreaking result is exciting.\n")
        saved = os.environ.pop("ABS_PROSE_FILES", None)
        try:
            codes = {
                "good": main(["prose_lint.py", "docs/good.md"], root=tmp, out=_Null()),
                "bad": main(["prose_lint.py", "docs/bad.md"], root=tmp, out=_Null()),
                "missing": main(
                    ["prose_lint.py", "--ship", "docs/memo/memo.html"], root=tmp, out=_Null()
                ),
                "usage": main(["prose_lint.py", "--nope"], root=tmp, out=_Null()),
            }
            os.environ["ABS_PROSE_FILES"] = "docs/good.md\ndocs/deleted.md"
            codes["env"] = main(["prose_lint.py"], root=tmp, out=_Null())
        finally:
            os.environ.pop("ABS_PROSE_FILES", None)
            if saved is not None:
                os.environ["ABS_PROSE_FILES"] = saved
        covered.add("r10-missing")
        want = {"good": 0, "bad": 1, "missing": 1, "usage": 2, "env": 0}
        if codes != want:
            failures.append(f"command line: exit codes {codes}, expected {want}")

    uncovered = sorted(set(LABELS) - covered - {"read"})
    if uncovered:
        failures.append(f"coverage: no case trips {uncovered}")
    for f in _module_docstring_ok(base):
        failures.append("this file's docstring breaks its own rule: " + f.render())
    errs, note = _sop_floor_check(root)
    failures.extend(errs or [])

    for line in failures:
        print("FAIL " + line)
    if note:
        print(note)
    n_checks = len(set(LABELS) - {"read"})
    print(
        f"prose-lint selftest: {'FAIL' if failures else 'OK'}, {len(cases)} fixture cases, "
        f"{n_checks} checks each tripped by a fixture, {len(failures)} failure(s)"
    )
    return 1 if failures else 0


class _Null:
    def write(self, _s):
        return 0

    def flush(self):
        pass


# ------------------------------------------------------------------ main


def main(argv, root: str = ROOT, out=None) -> int:
    out = out or sys.stdout
    args = argv[1:]
    if args == ["--selftest"]:
        return selftest(root)
    if args == ["--list-rules"]:
        print(RULE_TABLE, file=out)
        return 0
    ship = "--ship" in args
    paths = [a for a in args if a != "--ship"]
    if any(a.startswith("-") for a in paths):
        err = sys.stderr if out is sys.stdout else out
        print(
            "usage: quality/prose_lint.py [--ship] [path ...] | --selftest | --list-rules", file=err
        )
        return 2
    files, findings, notes, source = run(root, paths, ship)
    for note in notes:
        print(note, file=out)
    for f in sorted(findings, key=lambda f: (f.path, f.line, f.check)):
        print(f.render(), file=out)
    print(summary(files, findings, source, ship), file=out)
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
