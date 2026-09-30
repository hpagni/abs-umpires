"""W2.21, the export gate and the attribution file. SOP section 2, step W2.21.

The SOP clause this module makes mechanical, copied from W2.21:

    `out/` is the only generated directory git tracks. `tests/unit/test_exports.py`
    enforces mechanically: no file under `out/` may contain both a `game_pk`
    column and a `pitch_number`/`pitch_slot` column, and no export may exceed
    50,000 rows.

The rule is crude on purpose. A raw dump of pitches carries the game key and the
pitch key side by side and runs to hundreds of thousands of rows, so it cannot
pass this file by accident.

WHAT COUNTS AS A COLUMN. Column names come out of the file itself: the header row
of a CSV or TSV, the schema of a Parquet file, the keys of a JSON or JSONL
record, the header cells of a Markdown pipe table. Every name is folded to lower
case and each run of characters that is not a letter or a digit becomes one
underscore, so `Pitch Number`, `pitch-number` and `PITCH_NUMBER` all read as
`pitch_number`. Text inside a cell is not a column: `out/tables/join_failures.csv`
carries the string `pitch_number=3` inside its `detail` column and is a per-game
failure report, not a per-pitch export.

WHAT COUNTS AS A ROW. Data rows, header excluded, counted with the format's own
reader, so a newline inside a quoted CSV field is not counted as a row.

THE ONE EXEMPTION, narrow and mechanical. A file with zero data rows publishes no
grain, so the column rule does not fire on it. `out/tables/join_unmatched.csv` is
that case: SOP W2.15 always writes the unmatched report, and a healthy build
leaves it with a header and nothing under it, because any unmatched row fails the
join build first. The exemption is a row count, not a path allowlist. One data row
in that file and the assertion fires.

FILES THAT ARE NOT TABLES. Figures, model artifacts, `.gitkeep` markers and prose
without a pipe table carry no column header, so the column rule has nothing to
read. They are listed in the inventory with format `other` and are skipped.

A JSON FILE THAT IS ONE OBJECT. A fit receipt (`out/models/<fit>/provenance.json`,
`out/ch1/model/provenance.json`) is a single JSON object, not a list of records. It
is read as one record: its top-level keys are its columns and it counts one row, so
the grain and size rules apply to it as to any record. It is also walked to every
depth, through nested objects and lists, and it fails on two more things. The first is
a date after `absump.paths.LAST_OPEN_DATE`, written as an ISO day anywhere, in a value,
inside prose or as a key. The second is a key that names a game, pitch, player or
umpire identifier, or an umpire's name. Two exemptions are spelled out at
`STAMP_KEYS` and `ISO_DAY`: a write stamp and an integer. A list of records is
read as before, and this walk does not run on it.

THE ATTRIBUTION FILE. SOP W2.21 also fixes the contents of `ATTRIBUTION.md`: the
MLBAM notice, the posture paragraph, the Retrosheet string, credit to Baseball
Savant for the ABS leaderboard and to `baseballsavant.mlb.com/abs-metrics-documentation`
for the metric definitions, and credit to The Odds API and Kalshi for phase 2.
Each of the six is asserted below by a marker that cannot survive the section
being deleted.

Run this module as a script to refresh `out/audit/export_inventory.csv`:

    uv run python tests/unit/test_exports.py

The tests do not read that inventory. It is an audit record of what the scanner
saw, and the assertions run against a fresh scan every time.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from absump.paths import LAST_OPEN_DATE

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "out"
ATTRIBUTION = REPO_ROOT / "ATTRIBUTION.md"
INVENTORY = OUT_DIR / "audit" / "export_inventory.csv"

# SOP W2.21, verbatim. Neither number nor name came from an endpoint.
GAME_COLUMN = "game_pk"
PITCH_COLUMNS = ("pitch_number", "pitch_slot")
MAX_ROWS = 50000

# Suffixes read as tables. Everything else is `other`.
DELIMITED = {".csv": ",", ".tsv": "\t"}
JSON_LINES = {".jsonl", ".ndjson"}

# The pipe-table row of a Markdown alignment line, for example `|---|:--:|`.
MD_RULE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def rel_path(path: Path) -> str:
    """Repo-relative POSIX path, or the plain path for a file outside the repo."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def normalise(name: str) -> str:
    """Fold one column name to its comparison form."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


@dataclass(frozen=True)
class Table:
    """One file under out/, as the scanner read it."""

    path: str  # repo-relative, POSIX separators
    fmt: str  # csv, tsv, parquet, json, json_object, jsonl, markdown, other
    columns: tuple[str, ...]  # normalised, empty when the format carries none
    n_rows: int  # data rows, header excluded; -1 when unknown
    note: str  # why a format was not read, empty when it was
    findings: tuple[str, ...] = ()  # a single-object JSON's late dates and identifier keys

    @property
    def has_game(self) -> bool:
        return GAME_COLUMN in self.columns

    @property
    def has_pitch(self) -> bool:
        return any(c in self.columns for c in PITCH_COLUMNS)

    @property
    def breaks_grain_rule(self) -> bool:
        # The exemption: a file with no data rows publishes no grain.
        return self.has_game and self.has_pitch and self.n_rows > 0

    @property
    def breaks_size_rule(self) -> bool:
        return self.n_rows > MAX_ROWS


# ---------------------------------------------------------------------------
# readers


def _table_from_delimited(path: Path, delim: str) -> list[Table]:
    rel = rel_path(path)
    fmt = path.suffix.lstrip(".")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=delim)
        try:
            header = next(reader)
        except StopIteration:
            return [Table(rel, "other", (), 0, "empty file")]
        n_rows = sum(1 for row in reader if any(cell.strip() for cell in row))
    return [Table(rel, fmt, tuple(normalise(c) for c in header), n_rows, "")]


def _table_from_parquet(path: Path) -> list[Table]:
    rel = rel_path(path)
    try:
        import pyarrow.parquet as pq
    except ImportError:  # pragma: no cover - pyarrow is pinned in this project
        return [Table(rel, "parquet", (), -1, "pyarrow not importable")]
    pf = pq.ParquetFile(path)
    names = tuple(normalise(n) for n in pf.schema_arrow.names)
    return [Table(rel, "parquet", names, int(pf.metadata.num_rows), "")]


def _table_from_jsonl(path: Path) -> list[Table]:
    rel = rel_path(path)
    columns: list[str] = []
    n_rows = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            n_rows += 1
            if n_rows > 200:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return [Table(rel, "jsonl", (), n_rows, "line is not JSON")]
            if isinstance(record, dict):
                for key in record:
                    if normalise(key) not in columns:
                        columns.append(normalise(key))
    return [Table(rel, "jsonl", tuple(columns), n_rows, "")]


def _table_from_json(path: Path) -> list[Table]:
    rel = rel_path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [Table(rel, "json", (), -1, "file is not JSON")]
    if isinstance(payload, list) and payload and all(isinstance(r, dict) for r in payload):
        columns: list[str] = []
        for record in payload[:200]:
            for key in record:
                if normalise(key) not in columns:
                    columns.append(normalise(key))
        return [Table(rel, "json", tuple(columns), len(payload), "")]
    if isinstance(payload, dict):
        # One object, such as a fit receipt, is one record.
        columns = tuple(dict.fromkeys(normalise(str(k)) for k in payload))
        return [Table(rel, "json_object", columns, 1, "", tuple(record_findings(payload)))]
    return [Table(rel, "json", (), 0, "not a list of records")]


# A day written the ISO way, alone or at the head of a timestamp. An integer is never
# read as a date, because the pre-registered seeds are spelled as days: every fit
# receipt carries `seed` and `draw_seed` as eight-digit integers.
ISO_DAY = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")

# The keys that stamp when a file was written, not what it holds. Every receipt
# written after the boundary carries a stamp after it, so a stamp key is exempt, but
# only while its whole value is one clock time. A bare day under a stamp key, or a
# stamp inside prose, is read like any other date.
STAMP_KEYS = frozenset({"written_madrid", "timestamp_madrid"})
CLOCK_STAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
    r"(?:Z|[+-]\d{2}:?\d{2}|\s[A-Z]{3,5})?"
)

# A key that names a game, a pitch, a player or an umpire, matched whole on the
# normalised key, so `game_pk_sha256` and `n_umpires` are not identifiers. A column
# named inside a string value, such as `s(umpire_hp_id, bs = "re")` in a formula, is
# text and is not read.
IDENTIFIER_KEY = re.compile(
    r"game_?pk"
    r"|pitch_?(?:number|slot|id)|play_?id|sv_?id"
    r"|(?:batter|pitcher|catcher|player|mlbam)(?:_?(?:id|name))?"
    r"|(?:hp_)?umpire(?:_hp)?(?:_?(?:id|name|raw))?"
)


def _late_days(text: str, where: str) -> list[str]:
    found = []
    for m in ISO_DAY.finditer(text):
        try:
            day = dt.date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            continue  # not a calendar day, so not a date
        if day > LAST_OPEN_DATE:
            found.append(f"{where} carries {m[0]}, after {LAST_OPEN_DATE.isoformat()}")
    return found


def record_findings(node: object, where: str = "") -> list[str]:
    """Every late date and identifier key in one JSON record, walked to every depth."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{where}.{key}" if where else str(key)
            if IDENTIFIER_KEY.fullmatch(normalise(str(key))):
                found.append(f"{path} is an identifier key")
            found.extend(_late_days(str(key), f"{path} (as a key)"))
            if (
                normalise(str(key)) in STAMP_KEYS
                and isinstance(value, str)
                and CLOCK_STAMP.fullmatch(value.strip())
            ):
                continue
            found.extend(record_findings(value, path))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(record_findings(value, f"{where}[{i}]"))
    elif isinstance(node, str):
        found.extend(_late_days(node, where))
    return found


def _table_from_markdown(path: Path) -> list[Table]:
    """One Table per pipe table in the file, anchored `<path>#t<n>`."""
    rel = rel_path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tables: list[Table] = []
    i = 0
    while i < len(lines) - 1:
        head, rule = lines[i].strip(), lines[i + 1]
        if head.startswith("|") and MD_RULE.match(rule):
            cells = [normalise(c) for c in head.strip("|").split("|")]
            j = i + 2
            n_rows = 0
            while j < len(lines) and lines[j].strip().startswith("|"):
                n_rows += 1
                j += 1
            tables.append(Table(f"{rel}#t{len(tables) + 1}", "markdown", tuple(cells), n_rows, ""))
            i = j
            continue
        i += 1
    if not tables:
        return [Table(rel, "other", (), -1, "prose, no pipe table")]
    return tables


def scan_file(path: Path) -> list[Table]:
    rel = rel_path(path)
    suffix = path.suffix.lower()
    if path.stat().st_size == 0:
        return [Table(rel, "other", (), 0, "empty file")]
    if suffix in DELIMITED:
        return _table_from_delimited(path, DELIMITED[suffix])
    if suffix == ".parquet":
        return _table_from_parquet(path)
    if suffix in JSON_LINES:
        return _table_from_jsonl(path)
    if suffix == ".json":
        return _table_from_json(path)
    if suffix == ".md":
        return _table_from_markdown(path)
    return [Table(rel, "other", (), -1, f"not a table format ({suffix or 'no suffix'})")]


# out/dev/ holds local development artefacts: synthetic designs, recovery replicates and
# benchmark fits. .gitignore excludes the whole tree, so git can never publish a file
# there. The gate skips a file under out/dev/ only when it is untracked and git ignores
# it. A tracked file under out/dev/, and every file elsewhere under out/, is still read.
DEV_DIR = "out/dev/"


def ignored_dev_files() -> set[str]:
    """Untracked files under out/dev/ that .gitignore excludes, as repo-relative paths."""
    git = shutil.which("git")
    if git is None or not (REPO_ROOT / ".git").exists():
        return set()
    proc = subprocess.run(
        [
            git,
            "-C",
            str(REPO_ROOT),
            "ls-files",
            "-z",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--",
            DEV_DIR,
        ],
        capture_output=True,
        check=True,
    )
    return {p for p in proc.stdout.decode("utf-8").split("\0") if p}


def scan_out() -> list[Table]:
    """Every file under out/, in path order, less the ignored local files under out/dev/."""
    if not OUT_DIR.is_dir():
        return []
    skip = ignored_dev_files()
    tables: list[Table] = []
    for path in sorted(OUT_DIR.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        if rel_path(path) in skip:
            continue
        tables.extend(scan_file(path))
    return tables


def test_out_dev_is_ignored_and_untracked() -> None:
    """The out/dev/ skip holds only while git ignores that tree and tracks nothing in it."""
    git = shutil.which("git")
    if git is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    probe = subprocess.run(
        [git, "-C", str(REPO_ROOT), "check-ignore", "-q", "--no-index", DEV_DIR + "probe.parquet"],
        check=False,
    )
    assert probe.returncode == 0, ".gitignore does not exclude out/dev/"
    tracked = subprocess.run(
        [git, "-C", str(REPO_ROOT), "ls-files", "--", DEV_DIR],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert not tracked, f"git tracks files under out/dev/: {tracked[:5]}"


# ---------------------------------------------------------------------------
# the export rule

TABULAR_SUFFIXES = set(DELIMITED) | JSON_LINES | {".parquet", ".json"}


@pytest.fixture(scope="module")
def tables() -> list[Table]:
    return scan_out()


def test_out_directory_exists() -> None:
    assert OUT_DIR.is_dir(), "out/ is the published directory and must exist"


def test_no_export_mixes_game_and_pitch_grain(tables: list[Table]) -> None:
    """SOP W2.21, first half of the export rule."""
    bad = [t for t in tables if t.breaks_grain_rule]
    assert not bad, "per-pitch grain published under out/: " + "; ".join(
        f"{t.path} has {GAME_COLUMN} and "
        f"{[c for c in t.columns if c in PITCH_COLUMNS]} over {t.n_rows} rows"
        for t in bad
    )


def test_no_export_exceeds_fifty_thousand_rows(tables: list[Table]) -> None:
    """SOP W2.21, second half of the export rule."""
    bad = [t for t in tables if t.breaks_size_rule]
    assert not bad, "export over the 50,000 row limit: " + "; ".join(
        f"{t.path} has {t.n_rows} rows" for t in bad
    )


def test_every_tabular_file_under_out_was_read(
    tables: list[Table], request: pytest.FixtureRequest
) -> None:
    """A format the scanner cannot read is a hole in the gate, not a pass."""
    unread = [
        t
        for t in tables
        if Path(t.path.split("#")[0]).suffix.lower() in TABULAR_SUFFIXES
        and (t.n_rows < 0 or t.note)
    ]
    assert not unread, "tabular file not read by the export gate: " + "; ".join(
        f"{t.path} ({t.note or 'row count unknown'})" for t in unread
    )
    # The count goes into the step's receipt log, so a reader sees what was scanned.
    files = {t.path.split("#")[0] for t in tables}
    read = {t.path.split("#")[0] for t in tables if t.fmt != "other"}
    objects = {t.path for t in tables if t.fmt == "json_object"}
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write("\n")
        reporter.write_line(
            f"W2.21 export gate: {len(files)} files under out/, {len(read)} read as tables, "
            f"{len(objects)} of them single-object JSON walked for dates and identifiers"
        )


def record_scan_failures(tables: list[Table]) -> list[str]:
    """One line per finding, naming the file and the key path inside it."""
    return [f"{t.path}: {f}" for t in tables for f in t.findings]


def test_no_single_object_json_carries_a_late_date_or_an_identifier(
    tables: list[Table],
) -> None:
    """A fit receipt ships under out/, so it is scanned, not skipped."""
    bad = record_scan_failures(tables)
    assert not bad, "single-object JSON under out/ fails the record scan: " + "; ".join(bad)


def test_the_gate_is_not_vacuous(tmp_path: Path) -> None:
    """The three edges of the rule, on files planted for the purpose."""
    dump = tmp_path / "dump.csv"
    with dump.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Game PK", "pitch-number", "plate_x"])
        w.writerow([824466, 3, -0.08])
    planted = _table_from_delimited(dump, ",")[0]
    assert planted.columns[:2] == (GAME_COLUMN, "pitch_number")
    assert planted.breaks_grain_rule

    header_only = tmp_path / "header_only.csv"
    header_only.write_text("game_pk,pitch_slot,pitch_number\n", encoding="utf-8")
    exempt = _table_from_delimited(header_only, ",")[0]
    assert exempt.has_game and exempt.has_pitch
    assert exempt.n_rows == 0 and not exempt.breaks_grain_rule

    long = tmp_path / "long.csv"
    with long.open("w", encoding="utf-8", newline="") as fh:
        fh.write("season\n")
        fh.writelines("2026\n" for _ in range(MAX_ROWS + 1))
    over = _table_from_delimited(long, ",")[0]
    assert over.n_rows == MAX_ROWS + 1 and over.breaks_size_rule


# The first held-out day, computed, never written: GD-04 fails the repository on a
# literal date on or after the seal start.
FIRST_LATE_DAY = (LAST_OPEN_DATE + dt.timedelta(days=1)).isoformat()


def _planted(tmp_path: Path, payload: object) -> Table:
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return scan_file(path)[0]


def test_a_fit_receipt_is_read_as_one_clean_record(tmp_path: Path) -> None:
    """A receipt shaped like the real ones, ending on the last open day, passes."""
    table = _planted(
        tmp_path,
        {
            "fit": "surface_main",
            "min_official_date": "2022-04-07",
            "max_official_date": LAST_OPEN_DATE.isoformat(),
            "game_pk_sha256": "0" * 64,
            "seed": int(FIRST_LATE_DAY.replace("-", "")),
            "written_madrid": f"{FIRST_LATE_DAY}T07:50:45+0200",
            "formula": 'cs ~ s(velo, k = 10) + s(umpire_hp_id, bs = "re")',
            "n_umpires": 114,
            "rows_by_season": {"2022": 226513, "2026": 232815},
            "fits": [{"max_official_date": LAST_OPEN_DATE.isoformat(), "files": ["a.rds"]}],
        },
    )
    assert (table.fmt, table.n_rows, table.note) == ("json_object", 1, "")
    assert "max_official_date" in table.columns and "fits" in table.columns
    assert table.findings == ()
    assert not table.breaks_grain_rule and not table.breaks_size_rule


@pytest.mark.parametrize(
    ("payload", "where"),
    [
        ({"max_official_date": FIRST_LATE_DAY}, "max_official_date carries"),
        (
            {"fits": [{}, {"settings": {"window": ["2022-04-07", FIRST_LATE_DAY]}}]},
            "fits[1].settings.window[1] carries",
        ),
        ({"height_rule": f"refit through {FIRST_LATE_DAY}"}, "height_rule carries"),
        ({"rows_by_day": {FIRST_LATE_DAY: 12}}, f"rows_by_day.{FIRST_LATE_DAY} (as a key)"),
        ({"written_madrid": FIRST_LATE_DAY}, "written_madrid carries"),
    ],
)
def test_a_receipt_with_a_late_date_fails(tmp_path: Path, payload: object, where: str) -> None:
    """A day after the boundary fails wherever it sits, and the message names file and key."""
    table = _planted(tmp_path, payload)
    assert table.n_rows == 1 and not table.note
    failures = record_scan_failures([table])
    assert len(failures) == 1
    assert failures[0].startswith(f"{table.path}: {where}")
    assert FIRST_LATE_DAY in failures[0]


@pytest.mark.parametrize(
    ("payload", "where"),
    [
        ({"game_pk": 824466}, "game_pk"),
        ({"fits": [{"inputs": {"gamePk": 824466}}]}, "fits[0].inputs.gamePk"),
        ({"play_id": "planted"}, "play_id"),
        ({"batter_id": 0}, "batter_id"),
        ({"umpire_hp_name": "planted"}, "umpire_hp_name"),
    ],
)
def test_a_receipt_with_an_identifier_key_fails(
    tmp_path: Path, payload: object, where: str
) -> None:
    """A game, pitch, player or umpire key fails at any depth."""
    table = _planted(tmp_path, payload)
    assert record_scan_failures([table]) == [f"{table.path}: {where} is an identifier key"]


@pytest.mark.parametrize("payload", [[1, 2], "text", 3, []])
def test_json_that_is_neither_records_nor_one_object_stays_unread(
    tmp_path: Path, payload: object
) -> None:
    """Reading one object must not turn every JSON value into a pass."""
    table = _planted(tmp_path, payload)
    assert table.note == "not a list of records"


def test_out_is_the_only_generated_directory_git_tracks() -> None:
    """SOP W2.21, first sentence."""
    git = shutil.which("git")
    if git is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")

    def tracked(pathspec: str) -> list[str]:
        proc = subprocess.run(
            [git, "-C", str(REPO_ROOT), "ls-files", "--", pathspec],
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in proc.stdout.splitlines() if line.strip()]

    assert tracked("out"), "out/ carries no tracked file, so nothing is published"
    for generated in ("warehouse", "data", "logs", "dbt/target", ".venv", "renv/library"):
        assert not tracked(generated), f"{generated}/ is generated and must not be tracked"


# ---------------------------------------------------------------------------
# ATTRIBUTION.md

# Verbatim from http://gdx.mlb.com/components/copyright.txt, as carried in
# DATA_LICENSE.md. Compared after whitespace folding, so a line wrap is allowed
# and a word change is not.
MLBAM_NOTICE = (
    "Copyright 2026 MLB Advanced Media, L.P. Use of any content on this page "
    "acknowledges agreement to the terms posted here "
    "http://gdx.mlb.com/components/copyright.txt"
)

# Verbatim from https://www.retrosheet.org/notice.txt, the statement that notice
# requires to appear prominently.
RETROSHEET_STRING = (
    "The information used here was obtained free of charge from and is "
    "copyrighted by Retrosheet. Interested parties may contact Retrosheet at "
    '"www.retrosheet.org".'
)

POSTURE_MARKERS = (
    "individual, non-commercial",
    "src/absump/http.py",
    "R/lib/http.R",
    "config/throttle.yml",
    "redistributes no raw feed data",
)


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.fixture(scope="module")
def attribution() -> str:
    assert ATTRIBUTION.is_file(), "SOP W2.21 requires ATTRIBUTION.md at the repository root"
    return ATTRIBUTION.read_text(encoding="utf-8")


def test_attribution_carries_the_mlbam_notice(attribution: str) -> None:
    assert MLBAM_NOTICE in fold(attribution)


def test_attribution_carries_the_posture_paragraph(attribution: str) -> None:
    missing = [m for m in POSTURE_MARKERS if m not in attribution]
    assert not missing, f"posture paragraph is missing: {missing}"


def test_attribution_carries_the_retrosheet_string(attribution: str) -> None:
    folded = fold(attribution)
    assert RETROSHEET_STRING in folded
    assert "retrosheet.org/notice.txt" in folded


def test_attribution_credits_savant_for_the_abs_leaderboard(attribution: str) -> None:
    folded = fold(attribution)
    assert "Baseball Savant" in folded
    assert "baseballsavant.mlb.com/leaderboard/abs-challenges" in folded


def test_attribution_credits_the_metric_documentation(attribution: str) -> None:
    assert "baseballsavant.mlb.com/abs-metrics-documentation" in fold(attribution)


def test_attribution_credits_the_phase_two_sources(attribution: str) -> None:
    folded = fold(attribution)
    assert "The Odds API" in folded
    assert "Kalshi" in folded


# ---------------------------------------------------------------------------
# the inventory, written by `uv run python tests/unit/test_exports.py`

INVENTORY_HEADER = (
    "path",
    "format",
    "n_columns",
    "n_rows",
    "has_game_pk",
    "has_pitch_grain",
    "grain_verdict",
    "size_verdict",
    "note",
)


def inventory_rows(tables: list[Table]) -> list[list[str]]:
    rows = []
    for t in sorted(tables, key=lambda x: x.path):
        rows.append(
            [
                t.path,
                t.fmt,
                str(len(t.columns)),
                "" if t.n_rows < 0 else str(t.n_rows),
                "true" if t.has_game else "false",
                "true" if t.has_pitch else "false",
                "violation" if t.breaks_grain_rule else "ok",
                "violation" if t.breaks_size_rule else "ok",
                t.note,
            ]
        )
    return rows


def _render(rows: list[list[str]]) -> str:
    lines = [",".join(INVENTORY_HEADER)]
    for row in rows:
        lines.append(
            ",".join(
                ('"' + c.replace('"', '""') + '"') if ("," in c or '"' in c) else c for c in row
            )
        )
    return "\n".join(lines) + "\n"


def write_inventory() -> Path:
    """Write out/audit/export_inventory.csv, and rewrite only on a change.

    The inventory lists itself, so its own row count moves the first time the
    file appears. The loop runs the scan again until the rendered text stops
    changing, which takes two passes, so one call always leaves a stable file.
    """
    INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        body = _render(inventory_rows(scan_out()))
        if INVENTORY.is_file() and INVENTORY.read_text(encoding="utf-8") == body:
            return INVENTORY
        INVENTORY.write_text(body, encoding="utf-8")
    return INVENTORY


if __name__ == "__main__":
    path = write_inventory()
    tables = scan_out()
    bad = [t for t in tables if t.breaks_grain_rule or t.breaks_size_rule or t.findings]
    print(f"{path.relative_to(REPO_ROOT)}: {len(tables)} tables, {len(bad)} violations")
    sys.exit(1 if bad else 0)
