"""GD-04 and GD-05. Layer 3 of the four-layer guard: the static scan.

SOP step W9.7, inverted in revision R2 and repaired after the phase 01 red team.

The engine is `tests/guard/gd04_scan.py`; its module docstring states what the
scan walks, what it never walks and what the four rules are. This file is the
assertion layer: it pins the allowlist, pins the scope, and reproduces every
plant that the independent red team got past the R2 scanner, so that none of
them can come back.

The eleven plants of the phase 01 red team, and where each is pinned below:

    P1  raw fact read in R/ch1/                       caught then, still caught
    P2  boundary-date literal in src/absump/ch3/      caught then, still caught
    P8  the held-out view inside a YAML config        caught then, still caught
    P9a the held-out view in a small notebook         caught then, still caught
    P3  the label spelled in two pieces by paste0     MISSED then, pinned here
    P4  the view name built by an f-string            MISSED then, pinned here
    P5  FROM and the table on two lines, in dbt       MISSED then, pinned here
    P6  a raw read forgiven by a comment, in dbt      MISSED then, pinned here
    P7  a later boundary date, and > the day before   MISSED then, pinned here
    P9b the same notebook padded with a plot blob     MISSED then, pinned here
    P10 a symlink out of an ignored directory         MISSED then, pinned here

Two more the verifier demonstrated against the engine directly, not as worktree
plants, are pinned as well: the complement `!= 'open'`, which selects exactly
the held-out rows without ever writing the label, and the second fact table.

The plants below run on strings and on temporary files, never on the worktree,
so a test run never dirties a tracked path. The worktree round trip is GD-09,
`tests/guard/redteam_run.sh`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from gd04_scan import (
    _COMPLEMENT_OPS,
    _FACT,
    _HELD,
    _VIEW,
    ALLOWLIST,
    EXCLUDED_PREFIXES,
    EXEMPT_DIRS,
    EXEMPT_MIN_REASON,
    EXEMPT_NEVER,
    NON_CODE_SUFFIXES,
    REPO_ROOT,
    SCANNED_DIR_SKIPS,
    WALKED_ROOTS,
    Violation,
    boundary_date,
    exemption_claim,
    exemption_place_ok,
    exemption_site_ok,
    is_excluded,
    is_scannable,
    on_analysis_surface,
    read_scannable,
    scan_repository,
    scan_text,
    shipped_files,
)

BOUNDARY = boundary_date()


def rules(found: list[Violation]) -> set[str]:
    return {v.rule for v in found}


# ===================================================================== GD-05
def test_allowlist_is_exactly_two_paths() -> None:
    """GD-05's count is two, by exact path, and nothing else."""
    assert len(ALLOWLIST) == 2
    assert sorted(ALLOWLIST) == ["quality/sql/analysis_set.sql", "src/absump/seal.py"]


def test_allowlisted_paths_exist() -> None:
    for relative in sorted(ALLOWLIST):
        assert (REPO_ROOT / relative).is_file(), f"{relative} is allowlisted but absent"


def test_allowlist_is_load_bearing() -> None:
    """Without the allowlist the scan fails, and only on allowlisted paths."""
    unfiltered = scan_repository(allowlist=frozenset())
    assert unfiltered, "the scan no longer flags the two files that define the held-out set"
    assert {v.path for v in unfiltered} <= ALLOWLIST, "\n".join(str(v) for v in unfiltered)


# =============================================================== GD-04 scope
def test_no_directory_is_skipped() -> None:
    """The R1 directory list is gone and stays gone (architect item 6)."""
    assert not SCANNED_DIR_SKIPS, f"a directory list came back: {sorted(SCANNED_DIR_SKIPS)}"


def test_every_directory_that_executes_is_walked() -> None:
    """R/, src/, dbt/, notebooks/, scripts/, ops/, app/ and tests/ are all walked."""
    for name in ("R", "src", "dbt", "notebooks", "scripts", "ops", "app", "tests"):
        assert name in WALKED_ROOTS, f"{name}/ is not walked"


def test_the_only_exclusions_are_transcripts() -> None:
    """A transcript format under one of two directories, and nothing else.

    This is the self-poisoning fix, narrowed after the R2 red team. A receipt
    quotes the guard's failure text verbatim, so scanning receipts made every
    red-team run write the file that turned the next run red. dbt/logs/ is the
    third directory on the same footing: dbt's own debug log echoes the SQL of
    the build that just ran, so it quotes our compiled boundary comparison back
    at the next run. The skip is by
    FORMAT and by mode: a `.sql` or a `.sh` under either prefix is scanned, and
    so is an executable whatever its suffix.
    """
    assert set(EXCLUDED_PREFIXES) == {"quality/receipts/", "logs/", "dbt/logs/"}
    for prefix in EXCLUDED_PREFIXES:
        assert is_excluded(prefix + "run.log")
        assert not is_excluded(prefix + "anything.sql"), f"{prefix} hides a .sql file"
        assert not is_excluded(prefix + "fetch.sh"), f"{prefix} hides a shell script"
        assert not is_excluded(prefix + "probe.py"), f"{prefix} hides a python file"
    for name in WALKED_ROOTS:
        if name + "/" in set(EXCLUDED_PREFIXES):
            continue
        assert not is_excluded(name + "/anything.sql"), f"{name}/ must not be excluded"


def test_nothing_runnable_is_excluded_on_disk() -> None:
    """The claim the R2 verifier refuted, made an assertion over the real tree.

    `logs/env-setup.sh` is mode 755 and sat under an excluded prefix. The prose
    said nothing runnable was excluded; nothing checked it. This walks both
    directories as they are on disk and fails on any file that executes, or is
    code-shaped, and is skipped.
    """
    runnable_suffixes = {".sh", ".bash", ".zsh", ".py", ".r", ".sql", ".ipynb", ".pl", ".rb", ""}
    skipped_but_runnable = []
    for prefix in EXCLUDED_PREFIXES:
        base = REPO_ROOT / prefix.rstrip("/")
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            relative = str(path.relative_to(REPO_ROOT))
            if not is_excluded(relative):
                continue
            executable = os.access(path, os.X_OK)
            if executable or path.suffix.lower() in runnable_suffixes:
                skipped_but_runnable.append(relative)
    assert not skipped_but_runnable, (
        "these files execute or are code, and the scan skips them: "
        + ", ".join(sorted(skipped_but_runnable))
    )


def test_an_executable_under_an_excluded_prefix_is_scanned(tmp_path: Path) -> None:
    """The R2 plants C1 and C2, as strings and as a real listing."""
    script = f'duckdb -c "SELECT * FROM {_VIEW}"\n'
    for relative in ("logs/env-setup.sh", "quality/receipts/fetch.sh"):
        assert not is_excluded(relative), f"{relative} is skipped"
        assert scan_text(relative, script, BOUNDARY), f"{relative} carries a read and is silent"
    listed = set(shipped_files())
    # The installer itself was moved out from under the excluded prefix in the
    # R2 fixup: it lives at ops/env-setup.sh now, where nothing is skipped.
    assert not (REPO_ROOT / "logs" / "env-setup.sh").is_file(), (
        "logs/env-setup.sh is back under an excluded prefix; it belongs in ops/"
    )
    if (REPO_ROOT / "ops" / "env-setup.sh").is_file():
        assert "ops/env-setup.sh" in listed, "the toolchain installer is not even listed"


def test_no_executable_or_shebang_under_an_excluded_prefix() -> None:
    """The stronger form of the R2 finding: those directories hold no programs.

    `test_nothing_runnable_is_excluded_on_disk` proves the scan does not SKIP a
    program there. This one proves there is no program there to skip, which is
    what lets `ops/lint_http.sh` exclude the same two directories wholesale so
    that a lint receipt quoting a violation never re-triggers the linter. Both
    the executable bit and a `#!` first line count, whatever the suffix.
    """
    offenders: list[str] = []
    for prefix in EXCLUDED_PREFIXES:
        base = REPO_ROOT / prefix.rstrip("/")
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = str(path.relative_to(REPO_ROOT))
            if os.access(path, os.X_OK):
                offenders.append(f"{relative} (mode {oct(path.stat().st_mode & 0o777)})")
                continue
            try:
                with path.open("rb") as handle:
                    if handle.read(2) == b"#!":
                        offenders.append(f"{relative} (shebang)")
            except OSError:
                continue
    assert not offenders, (
        "an excluded directory holds a program; move it under ops/ or scripts/: "
        + ", ".join(sorted(offenders))
    )


def test_a_transcript_is_still_skipped() -> None:
    """And the self-trigger stays gone: a `.log` under either prefix is skipped."""
    assert is_excluded("quality/receipts/W9.7.log")
    assert is_excluded("logs/evidence/W9.7.log")
    assert is_excluded("quality/receipts/W9.7.json")


def test_a_receipt_quoting_the_guard_does_not_poison_the_scan(tmp_path: Path) -> None:
    """The exact phase 01 failure: the transcript of a red-team run."""
    transcript = (
        f"[redteam] make test-guard -> exit 2   "
        f"GD-04 FAIL: R/ch1/20_surfaces.R:31 reads analysis_set = '{_HELD}'\n"
        f"[redteam] make test-guard -> exit 2   "
        f"GD-04 FAIL: src/absump/ch3/dp_fast.py:37 reads {_VIEW}\n"
        f"literal boundary-date comparison -- official_date >= DATE '{BOUNDARY}'\n"
    )
    assert scan_text("quality/receipts/W9.7.log", transcript, BOUNDARY), (
        "the transcript really does carry banned text; that is why it is excluded by path"
    )
    assert is_excluded("quality/receipts/W9.7.log")
    assert is_excluded("logs/evidence/W9.7.log")
    written = tmp_path / "W9.7.log"
    written.write_text(transcript, encoding="utf-8")
    assert "quality/receipts" not in {v.path for v in scan_repository()}


def test_every_shipped_file_is_dropped_only_for_its_format() -> None:
    """The one reason a shipped file is not scanned is that it is not code.

    Size is no longer a reason and neither is being a symlink: both were exits
    the red team walked through.
    """
    for relative in shipped_files():
        if is_scannable(relative):
            continue
        path = REPO_ROOT / relative
        reason_is_format = Path(relative).suffix.lower() in NON_CODE_SUFFIXES
        reason_is_gone = not path.exists()
        assert reason_is_format or reason_is_gone, (
            f"{relative} was skipped and no format rule explains it"
        )


def test_code_extensions_are_all_scanned() -> None:
    code = [p for p in shipped_files() if Path(p).suffix.lower() in {".py", ".r", ".sql", ".sh"}]
    assert len(code) > 10, "the scan found almost no code; the listing is probably wrong"
    for relative in code:
        assert is_scannable(relative), f"{relative} is code and must be scanned"


def test_repository_has_no_held_out_read() -> None:
    """The whole repository, every file it ships, minus two allowlisted paths."""
    found = scan_repository()
    assert not found, "\n".join(str(v) for v in found)


# ============================================ the eleven plants of the red team
def test_p1_raw_fact_read_in_R_is_caught() -> None:
    line = f'  DBI::dbGetQuery(con, "SELECT plate_x, plate_z FROM {_FACT}pitch")\n'
    found = scan_text("R/ch1/20_surfaces.R", line, BOUNDARY)
    assert "unqualified raw fact-table read" in rules(found)


def test_p2_boundary_date_literal_in_ch3_is_caught() -> None:
    text = (
        "    return con.execute(\n"
        f"        \"SELECT * FROM v_pitch_open WHERE official_date >= DATE '{BOUNDARY}'\"\n"
        "    ).pl()\n"
    )
    found = scan_text("src/absump/ch3/dp_fast.py", text, BOUNDARY)
    assert "literal boundary-date comparison" in rules(found)


def test_p8_the_view_inside_a_yaml_config_is_caught() -> None:
    text = f'value_frame:\n  sql: "SELECT * FROM {_VIEW}"\n'
    found = scan_text("config/ch3_queries.yml", text, BOUNDARY)
    assert "names the held-out pitch view" in rules(found)


def test_p3_a_label_spelled_in_two_pieces_is_caught() -> None:
    """The label built by paste0 and compared through a variable.

    R2 matched a quoted literal, so the label held in `HELD` was invisible. The
    seam-joiner closes the gap between the fragments, and the taint pass carries
    the value to the line that compares it.
    """
    text = (
        f'HELD <- paste0("{_HELD[:4]}", "{_HELD[4:]}")\n'
        "d <- dplyr::filter(d, analysis_set == HELD)\n"
    )
    found = scan_text("R/ch1/20_surfaces.R", text, BOUNDARY)
    assert "reads the held-out analysis set" in rules(found)
    assert [v.line for v in found if v.rule == "reads the held-out analysis set"] == [2]


def test_p3b_the_fragments_alone_are_caught_when_compared() -> None:
    """The same trick without the variable: the two pieces on the comparison line."""
    text = f'd <- dplyr::filter(d, analysis_set == paste0("{_HELD[:4]}", "{_HELD[4:]}"))\n'
    assert "reads the held-out analysis set" in rules(scan_text("R/ch1/x.R", text, BOUNDARY))


def test_p4_a_view_name_built_by_an_fstring_is_caught() -> None:
    text = (
        f'    split = "{_HELD}"\n'
        '    view = f"v_pitch_{split}"\n'
        '    return con.execute(f"SELECT * FROM {view}").pl()\n'
    )
    found = scan_text("src/absump/ch3/dp_fast.py", text, BOUNDARY)
    assert "names the held-out pitch view" in rules(found)
    hits = sorted(v.line for v in found if v.rule == "names the held-out pitch view")
    assert hits == [2, 3], f"both the build and the use must be named, got {hits}"


def test_p5_from_and_the_table_on_two_lines_is_caught() -> None:
    """A formatter breaks the statement; R2's per-line rule 3 lost the read."""
    text = (
        "{{ config(materialized='view') }}\n"
        "SELECT\n    game_pk,\n    plate_x\nFROM\n"
        f"    {_FACT}pitch\n"
    )
    found = scan_text("dbt/models/marts/v_pitch_all.sql", text, BOUNDARY)
    assert "unqualified raw fact-table read" in rules(found)


def test_p6_a_comment_forgives_nothing() -> None:
    """R2 computed the open qualification over the whole file, comments included."""
    text = (
        "-- Sibling of v_pitch_open, which restricts analysis_set = 'open'. This one\n"
        "-- counts every pitch so the totals in the memo reconcile.\n"
        "{{ config(materialized='table') }}\n"
        f"SELECT game_pk, count(*) AS pitches FROM {_FACT}pitch GROUP BY 1\n"
    )
    found = scan_text("dbt/models/marts/late_counts.sql", text, BOUNDARY)
    assert "unqualified raw fact-table read" in rules(found)


def test_p7_any_day_on_or_after_the_boundary_is_caught() -> None:
    """R2 matched one literal. Every later day, and `>` the day before, read the same rows."""
    from datetime import date, timedelta

    day = date.fromisoformat(BOUNDARY)
    after = (day + timedelta(days=1)).isoformat()
    before = (day - timedelta(days=1)).isoformat()
    for snippet in (
        f"WHERE official_date >= DATE '{after}'",
        f"WHERE official_date > DATE '{before}'",
        f"WHERE official_date <= DATE '{after}'",
        f"WHERE official_date BETWEEN DATE '2026-04-01' AND DATE '{after}'",
        f"d <- dplyr::filter(d, official_date > as.Date('{before}'))",
    ):
        found = scan_text("src/absump/ch3/dp_fast.py", snippet + "\n", BOUNDARY)
        assert "literal boundary-date comparison" in rules(found), snippet


def test_a_comparison_that_stays_open_is_not_flagged() -> None:
    """The rule bans reading the held-out days, not writing a date."""
    from datetime import date, timedelta

    day = date.fromisoformat(BOUNDARY)
    before = (day - timedelta(days=1)).isoformat()
    for snippet in (
        f"WHERE official_date < DATE '{BOUNDARY}'",
        f"WHERE official_date <= DATE '{before}'",
    ):
        assert not scan_text("src/absump/ch2/predict.py", snippet + "\n", BOUNDARY), snippet


def test_p9b_a_notebook_is_scanned_whatever_it_weighs(tmp_path: Path) -> None:
    """One embedded plot used to push the same notebook past the size skip."""
    blob = "iVBORw0KGgoAAAANSUhEUg" * 120_000
    notebook = (
        '{\n "cells": [\n  {\n   "cell_type": "code",\n'
        '   "outputs": [\n    {"output_type": "display_data",\n'
        f'     "data": {{"image/png": "{blob}"}}}}\n   ],\n'
        '   "source": [\n'
        f'    "rows = con.execute(\\"SELECT * FROM {_VIEW}\\").pl()\\n"\n'
        '   ]\n  }\n ],\n "nbformat": 4\n}\n'
    )
    path = tmp_path / "notebooks" / "ch1_explore.ipynb"
    path.parent.mkdir(parents=True)
    path.write_text(notebook, encoding="utf-8")
    assert path.stat().st_size > 2_000_000, "the plant must be past the old size skip"
    assert is_scannable("notebooks/ch1_explore.ipynb", root=tmp_path)
    found = scan_text("notebooks/ch1_explore.ipynb", notebook, BOUNDARY)
    assert "names the held-out pitch view" in rules(found)


def test_p10_a_symlink_out_of_an_ignored_directory_is_scanned(tmp_path: Path) -> None:
    """An importable symlink into ignored research/ was skipped by design in R2."""
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "probe.py"
    target.write_text(f'def probe(con):\n    return con.execute("SELECT * FROM {_VIEW}").pl()\n')
    inside = tmp_path / "src" / "absump" / "ch3"
    inside.mkdir(parents=True)
    os.symlink(target, inside / "probe.py")
    relative = "src/absump/ch3/probe.py"
    assert is_scannable(relative, root=tmp_path), "a symlink to code is still code"
    found = scan_repository(root=tmp_path, allowlist=frozenset(), only=relative)
    assert "names the held-out pitch view" in rules(found)


def test_the_complement_of_the_open_label_is_caught() -> None:
    """`!= 'open'` selects exactly the held-out rows and never writes the label.

    R2 read this as proof that the file was restricted to the open set, and
    forgave the raw fact reads in the same file as well.
    """
    bang, angle, notin = _COMPLEMENT_OPS
    for snippet in (
        f"con.execute(\"SELECT plate_x FROM v_pitch_open WHERE analysis_set {bang} 'open'\")",
        f"SELECT plate_x FROM dim_game WHERE analysis_set {angle} 'open'",
        f"d <- dplyr::filter(d, analysis_set {bang} 'open')",
        f"SELECT * FROM dim_game WHERE analysis_set {notin} ('open')",
    ):
        found = scan_text("src/absump/ch3/dp_fast.py", snippet + "\n", BOUNDARY)
        assert "reads the held-out analysis set" in rules(found), snippet


def test_the_complement_does_not_qualify_a_raw_read() -> None:
    text = f"SELECT plate_x FROM {_FACT}pitch WHERE analysis_set {_COMPLEMENT_OPS[0]} 'open'\n"
    found = scan_text("dbt/models/marts/x.sql", text, BOUNDARY)
    assert rules(found) == {"reads the held-out analysis set", "unqualified raw fact-table read"}


def test_the_second_fact_table_is_guarded_too() -> None:
    """Rule 3 named one table in R2. The challenge table was unguarded."""
    text = f"SELECT * FROM {_FACT}challenge\n"
    assert "unqualified raw fact-table read" in rules(scan_text("sql/x.sql", text, BOUNDARY))


def test_qualification_ahead_of_the_read_forgives_nothing() -> None:
    """An open restriction belonging to an earlier statement is not a licence."""
    text = (
        f"SELECT game_pk FROM dim_game WHERE analysis_set = 'open';\nSELECT * FROM {_FACT}pitch\n"
    )
    found = scan_text("sql/two_statements.sql", text, BOUNDARY)
    assert [v.line for v in found if v.rule == "unqualified raw fact-table read"] == [2]


def test_a_distant_open_query_does_not_forgive_a_later_raw_read() -> None:
    """File-wide forgiveness is gone: the window is the statement, not the file."""
    text = (
        "q1 = \"SELECT * FROM v_pitch_open WHERE analysis_set = 'open'\"\n"
        + "filler = 1\n" * 8
        + f'q2 = "SELECT * FROM {_FACT}pitch"\n'
    )
    found = scan_text("src/absump/ch3/dp_fast.py", text, BOUNDARY)
    assert [v.line for v in found if v.rule == "unqualified raw fact-table read"] == [10]


# ------------------------------------------------- what must stay unflagged
def test_an_open_read_is_not_flagged() -> None:
    open_read = "rows = con.execute('SELECT * FROM v_pitch_open').pl()\n"
    assert not scan_text("src/absump/ch2/predict.py", open_read, BOUNDARY)
    view_definition = (
        f"CREATE VIEW v_pitch_open AS\nSELECT * FROM {_FACT}pitch\nWHERE analysis_set = 'open'\n"
    )
    assert not scan_text("dbt/models/marts/v_pitch_open.sql", view_definition, BOUNDARY)


def test_an_unqualified_fact_read_is_flagged() -> None:
    unqualified = f"CREATE VIEW v_all AS\nSELECT * FROM {_FACT}pitch\n"
    found = scan_text("dbt/models/marts/v_all.sql", unqualified, BOUNDARY)
    assert found and found[0].rule == "unqualified raw fact-table read"


def _planted() -> list[tuple[str, str]]:
    return [
        ("analysis set", f"SELECT game_pk FROM dim_game WHERE analysis_set = '{_HELD}'"),
        ("held-out view", f"rows = con.execute('SELECT * FROM {_VIEW}').pl()"),
        ("raw fact table", f"SELECT plate_x FROM {_FACT}pitch WHERE balls = 0"),
        ("boundary date", f"SELECT * FROM dim_game WHERE official_date >= DATE '{BOUNDARY}'"),
    ]


@pytest.mark.parametrize(("label", "snippet"), _planted(), ids=[c[0] for c in _planted()])
def test_a_planted_violation_is_caught(label: str, snippet: str) -> None:
    found = scan_text("src/absump/ch3/dp_fast.py", snippet + "\n", BOUNDARY)
    assert found, f"the {label} rule no longer fires"


def test_gd09_plants_in_both_ch3_and_R_are_caught() -> None:
    """GD-09 plants one violation in R/ch1/ and one in src/absump/ch3/."""
    plants = {
        "R/ch1/20_surfaces.R": f"d <- dplyr::filter(d, analysis_set == '{_HELD}')",
        "src/absump/ch3/dp_fast.py": f'rows = con.execute("SELECT * FROM {_VIEW}").pl()',
    }
    for relative, line in plants.items():
        assert relative not in ALLOWLIST
        found = scan_text(relative, line + "\n", BOUNDARY)
        assert found, f"the guard did not fail on the plant in {relative}"


# ================================ the nine spellings the R2 red team got past
# Every one of these read held-out rows while the R2 scanner stayed silent. They
# are pinned here as strings, so `make test-guard` fails on a regression without
# waiting for the worktree round trip in GD-09.
def test_a_pull_window_with_no_comparison_is_caught() -> None:
    """R2 B1a. `end: "<late day>"` in a config the nightly pull reads."""
    year = BOUNDARY[:4]
    config = f'backfill:\n  start: "{year}-09-15"\n  end: "{year}-09-30"\n'
    found = scan_text("config/backfill.yml", config, BOUNDARY)
    assert "held-out date literal" in rules(found), config


def test_a_held_out_game_copied_into_a_fixture_is_caught() -> None:
    """R2 B2. A datum, not a query: the cheapest way held-out data enters git."""
    from datetime import date, timedelta

    later = (date.fromisoformat(BOUNDARY) + timedelta(days=2)).isoformat()
    fixture = f'{{"gamePk": 825412, "officialDate": "{later}"}}\n'
    found = scan_text("tests/fixtures/generated/late_game.json", fixture, BOUNDARY)
    assert "held-out date literal" in rules(found), fixture


def test_a_boundary_day_built_from_fragments_is_caught() -> None:
    """R2 B3 and B7. The seam-joiner, applied to the date rules at last."""
    python_plant = f'FIRST = "{BOUNDARY[:-1]}" + "{BOUNDARY[-1]}"\n'
    assert scan_text("src/absump/ch3/window.py", python_plant, BOUNDARY), python_plant
    year, month, day = BOUNDARY.split("-")
    r_plant = f'cut_day <- as.Date(paste("{year}", "{month}", "{day}", sep = "-"))\n'
    assert scan_text("R/ch1/20_surfaces.R", r_plant, BOUNDARY), r_plant


def test_a_query_carried_as_base64_is_caught() -> None:
    """R2 B4a. The blob decodes to a read of the held-out view."""
    import base64 as _b64

    payload = _b64.b64encode(f"SELECT * FROM {_VIEW}".encode()).decode()
    cell = f'    "q = base64.b64decode(\\"{payload}\\").decode()",\n'
    found = scan_text("notebooks/ch1.ipynb", cell, BOUNDARY)
    assert "names the held-out pitch view" in rules(found), cell


def test_a_blob_abutting_the_view_name_is_caught() -> None:
    """R2 B4c. The redaction used to swallow the first letter of the name."""
    blob = "QUJD" * 200
    line = f'{{"output_type": "stream", "text": "{blob}{_VIEW}"}}\n'
    found = scan_text("notebooks/ch1.ipynb", line, BOUNDARY)
    assert "names the held-out pitch view" in rules(found), line[-60:]


def test_the_label_assembled_with_jinja_concat_is_caught() -> None:
    """R2 B5b. dbt is where `~` is the ordinary way to join two strings."""
    model = (
        f"{{% set held = '{_HELD[:4]}' ~ '{_HELD[4:]}' %}}\n"
        f"SELECT game_pk FROM {{{{ ref('stg_pitch') }}}} WHERE analysis_set = '{{{{ held }}}}'\n"
    )
    found = scan_text("dbt/models/marts/late_pitch.sql", model, BOUNDARY)
    assert found, model


def test_a_fact_table_parked_in_a_jinja_variable_is_caught() -> None:
    """R2 B5c. Taint used to follow the label and the view, never a table."""
    model = f"{{% set tbl = '{_FACT}pitch' %}}\nSELECT game_pk, plate_x FROM {{{{ tbl }}}}\n"
    found = scan_text("dbt/models/marts/all_pitch.sql", model, BOUNDARY)
    assert "unqualified raw fact-table read" in rules(found), model


def test_the_held_out_partition_read_by_path_is_caught() -> None:
    """R2 B6. No view, no fact table: a parquet path and a glob."""
    line = f"con.execute(\"SELECT * FROM read_parquet('data/{_HELD}/pitch/*.parquet')\")\n"
    found = scan_text("src/absump/ch3/dp_fast.py", line, BOUNDARY)
    assert found and any(v.code == "GD-05" for v in found), line


# ======================================================================= GD-05
def test_gd05_the_label_alone_in_chapter_code_is_caught() -> None:
    """SOP-final.md line 1757, and the F8 the two red teams raised.

    `split = "<label>"` names the held-out set with no read on the line. The
    earlier scanner implemented GD-05 as a count of the allowlist; this is the
    rule.
    """
    found = scan_text("src/absump/ch3/dp_fast.py", f'split = "{_HELD}"\n', BOUNDARY)
    assert [v for v in found if v.code == "GD-05"], "GD-05 is still only a count"


def test_gd05_runs_on_the_analysis_surface() -> None:
    """Every directory where a chapter, a model or a notebook can read a row."""
    for relative in (
        "R/ch1/20_surfaces.R",
        "dbt/models/marts/x.sql",
        "notebooks/ch1.ipynb",
        "src/absump/ch3/dp_fast.py",
        "config/pull.yml",
        "tests/fixtures/generated/x.json",
    ):
        assert on_analysis_surface(relative), f"{relative} is off the GD-05 surface"


def test_gd05_does_not_fire_on_the_seal_machinery() -> None:
    """The rule runs where a read is written, not where the seal is defined.

    `src/absump/paths.py`, `dbt/profiles.yml.example`'s target name and a step
    receipt all name the label for their own reasons. A rule that failed on
    those would be switched off within a week, and that is stated here rather
    than in prose alone.
    """
    assert not on_analysis_surface("src/absump/paths.py")
    assert not on_analysis_surface("quality/steps.yml")
    assert not on_analysis_surface("ops/preregister.sh")


def test_the_repository_is_green_under_the_two_surface_rules() -> None:
    """Rules 5 and 6 over the real tree, which is the only test that matters."""
    found = [
        v for v in scan_repository() if v.rule.startswith(("held-out date", "the held-out label"))
    ]
    assert not found, "\n".join(str(v) for v in found)


# ================================================== layer 2 and the ordering
def test_the_runtime_gate_is_shut() -> None:
    """GD-03. `_unlocked()` is False and the public surface is the one W1.8 names."""
    from absump import seal

    for name in ("assert_unsealed", "sealed_only", "frame", "_unlocked"):
        assert hasattr(seal, name), f"absump.seal is missing {name}"
    assert seal._unlocked() is False
    assert seal.unlock_report()["failed"], "the gate reports no failing precondition"


def test_the_one_way_door_refuses_and_tags_nothing() -> None:
    """GD-12. `ops/preregister.sh` is MILESTONE M1's door, and it stays shut.

    A bare run always refuses, before M1 and after it. Only the owner opens it,
    by hand, with --confirm.
    """
    before = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "tag"], capture_output=True, text=True, check=False
    ).stdout
    done = subprocess.run(
        ["bash", str(REPO_ROOT / "ops" / "preregister.sh")],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    after = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "tag"], capture_output=True, text=True, check=False
    ).stdout
    assert done.returncode != 0, "the one-way door did not refuse"
    assert "MILESTONE M1" in done.stdout + done.stderr
    assert before == after, "the door created or moved a tag"


def test_fit_receipts_descend_from_the_pre_registration() -> None:
    """GD-12, D-67. Every fit receipt under out/, open or held out."""
    done = subprocess.run(
        ["bash", str(REPO_ROOT / "ops" / "check_seal_order.sh")],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "SEAL-ORDER OK" in done.stdout


# ------------------------------------------------- R3: the six new spellings
def test_identifiers_are_matched_without_regard_to_case() -> None:
    """DuckDB folds identifiers, so one shift key must not empty three rules."""
    shouted = f"SELECT GAME_PK, PLATE_X FROM {_VIEW.upper()}\n"
    found = scan_text("sql/shouted.sql", shouted, BOUNDARY)
    assert [v.rule for v in found] == ["names the held-out pitch view"]
    labelled = f"SELECT * FROM {_FACT.upper()}PITCH WHERE ANALYSIS_SET = '{_HELD.upper()}'\n"
    rules = {v.rule for v in scan_text("sql/shouted2.sql", labelled, BOUNDARY)}
    assert "reads the held-out analysis set" in rules
    assert "the held-out label outside the two allowlisted files" in rules


def test_the_held_out_partition_is_read_off_the_analysis_surface() -> None:
    """`ops/` holds the pull, the seal and the deploy; a read there is a read."""
    line = f"df = pl.read_parquet('data/{_HELD}/pitch/*.parquet')\n"
    found = scan_text("ops/nightly_pull.py", line, BOUNDARY)
    assert [(v.code, v.rule) for v in found] == [("GD-05", "reads the held-out partition off disk")]


def test_a_glob_inside_the_label_segment_is_still_the_label() -> None:
    globbed = f"SELECT * FROM read_parquet('data/{_HELD[:4]}*/pitch/*.parquet')\n"
    assert scan_text("sql/globbed.sql", globbed, BOUNDARY)
    assert scan_text("ops/deploy.py", globbed, BOUNDARY)


def test_a_day_reached_by_arithmetic_is_a_held_out_day() -> None:
    from datetime import date, timedelta

    start = date.fromisoformat(BOUNDARY) - timedelta(days=3)
    arithmetic = (
        f"CUT = date({start.year}, {start.month}, {start.day}) + timedelta(days=3)\n"
        "rows = frame.filter(pl.col('official_date') >= CUT)\n"
    )
    found = scan_text("src/absump/ch3/window.py", arithmetic, BOUNDARY)
    assert found and found[0].rule == "literal boundary-date comparison"
    safe = f"CUT = date({start.year}, {start.month}, {start.day}) + timedelta(days=1)\n"
    assert not scan_text("src/absump/ch3/window_ok.py", safe, BOUNDARY)


def test_a_name_assembled_from_character_codes_is_that_name() -> None:
    """The scanner's own token trick, turned back on it."""
    codes = "+".join(f"chr({ord(char)})" for char in _VIEW[:2])
    line = f'q = "SELECT * FROM " + {codes}+"{_VIEW[2:]}"\n'
    found = scan_text("src/absump/ch3/ordinals.py", line, BOUNDARY)
    assert found and found[0].rule == "names the held-out pitch view"


def test_a_label_spelled_with_escapes_is_that_label() -> None:
    escaped = f'split = "{_HELD[:4]}\\x{ord(_HELD[4]):02x}{_HELD[5:]}"\n'
    found = scan_text("src/absump/ch3/escaped.py", escaped, BOUNDARY)
    assert found and found[0].code == "GD-05"


def test_the_seal_machinery_writing_its_own_directory_is_not_a_read() -> None:
    """`out/<label>/` is where the seal writes; listing it is not a read."""
    machinery = f'sealed="$root/out/{_HELD}"\nfind "$sealed" -type f\n'
    assert not scan_text("ops/seal_check.sh", machinery, BOUNDARY)


# ------------------------------------------------------ the rule-3 scope exemption
#
# The owner decision scopes rule 3 so that warehouse CONSTRUCTION and
# whole-warehouse MEASUREMENT are not analysis reads. These pin it from both
# sides: the marker buys the exemption only where the site really is that kind
# of site, and an analysis read of a fact table stays strict everywhere.

MARKER = "GD-04-EXEM" + "PT"
REASON = "the reason, long enough to be a sentence and not a shrug"
FACT_READ = f"select * from {{{{ ref('{_FACT}pitch') }}}}\n"


def marked(kind: str, comment: str = "--", reason: str = REASON) -> str:
    return f"{comment} {MARKER}: {kind} -- {reason}\n"


def test_a_construction_site_without_the_marker_still_fails() -> None:
    """The exemption is declared, never inferred from the path."""
    found = scan_text(f"dbt/models/marts/{_FACT}called_pitch.sql", FACT_READ, BOUNDARY)
    assert rules(found) == {"unqualified raw fact-table read"}


def test_a_construction_site_with_the_marker_is_scoped_out() -> None:
    path = f"dbt/models/marts/{_FACT}called_pitch.sql"
    assert not scan_text(path, marked("construction") + FACT_READ, BOUNDARY)


def test_a_dbt_test_is_construction_and_a_staging_model_is_not() -> None:
    """Both are dbt SQL; only one has an assertion about a fact table as output."""
    body = marked("construction") + FACT_READ
    assert not scan_text("dbt/tests/assert_something.sql", body, BOUNDARY)
    assert scan_text("dbt/models/staging/stg_something.sql", body, BOUNDARY)


def test_a_mart_that_is_not_a_fact_table_cannot_claim_construction() -> None:
    """The property is the model's OWN output, not the directory it sits in."""
    found = scan_text(
        "dbt/models/marts/v_called_pitch_open.sql", marked("construction") + FACT_READ, BOUNDARY
    )
    assert "unqualified raw fact-table read" in rules(found)


def test_an_analysis_read_without_the_qualifier_still_fails() -> None:
    """The strict half of the decision, with no marker anywhere near it."""
    for path in (
        "src/absump/ch2/estimate.py",
        "R/ch1/20_surfaces.R",
        "notebooks/explore.ipynb",
        "sql/adhoc.sql",
    ):
        found = scan_text(path, f"q = 'select * from marts.{_FACT}called_pitch'\n", BOUNDARY)
        assert "unqualified raw fact-table read" in rules(found), path


def test_an_analysis_read_with_the_open_qualifier_is_still_forgiven() -> None:
    line = f"q = \"select * from marts.{_FACT}called_pitch where analysis_set = 'open'\"\n"
    assert not scan_text("src/absump/ch2/estimate.py", line, BOUNDARY)


@pytest.mark.parametrize(
    "path",
    [
        "src/absump/ch1/load.py",
        "src/absump/ch2/estimate.py",
        "src/absump/ch3/window.py",
        "R/ch1/20_surfaces.R",
        "notebooks/explore.py",
        "tests/fixtures/one_game.py",
    ],
)
def test_the_marker_grants_nothing_on_the_analysis_surface(path: str) -> None:
    """A chapter that decorates itself as construction is caught twice."""
    body = marked("construction", "#") + f"q = 'select * from marts.{_FACT}pitch'\n"
    found = scan_text(path, body, BOUNDARY)
    assert "unqualified raw fact-table read" in rules(found), path
    assert "GD-04 exemption marker where it grants nothing" in rules(found), path
    assert not exemption_place_ok(path)


def test_a_measurement_marker_needs_a_whole_warehouse_profile() -> None:
    """One table under a measurement banner is an analysis read wearing a hat."""
    one = marked("measurement", "#") + f"q = 'select count(*) from marts.{_FACT}challenge'\n"
    assert "unqualified raw fact-table read" in rules(scan_text("tests/data/one.py", one, BOUNDARY))
    many = (
        marked("measurement", "#")
        + f"q = 'select count(*) from marts.{_FACT}challenge'\n"
        + f"r = 'select count(*) from marts.{_FACT}pitch'\n"
        + "s = 'select count(*) from staging.stg_feed_pitch'\n"
        + "t = 'select count(*) from marts.dim_game'\n"
    )
    assert not scan_text("tests/data/many.py", many, BOUNDARY)


def test_the_marker_must_be_a_comment_and_must_give_a_reason() -> None:
    path = f"dbt/models/marts/{_FACT}called_pitch.sql"
    live = f"select '{MARKER}: construction -- {REASON}' as note\n" + FACT_READ
    assert "unqualified raw fact-table read" in rules(scan_text(path, live, BOUNDARY))
    assert exemption_claim(path, live) is None
    shrug = marked("construction", reason="because") + FACT_READ
    assert "unqualified raw fact-table read" in rules(scan_text(path, shrug, BOUNDARY))
    assert len("because") < EXEMPT_MIN_REASON


def test_the_exemption_never_reaches_the_chapters_or_the_notebooks() -> None:
    """The directories the decision names, as a property of the table itself."""
    for prefix in ("src/absump/ch", "R/", "notebooks/"):
        assert prefix in EXEMPT_NEVER
    for place in EXEMPT_NEVER:
        assert not exemption_place_ok(place + "anything.py")


def test_every_marker_in_the_repository_is_one_the_scanner_grants() -> None:
    """No marker sits in the tree unearned, and none of them is a dead letter."""
    for relative in shipped_files():
        if not is_scannable(relative):
            continue
        text = read_scannable(relative)
        if text is None or MARKER + ":" not in text:
            continue
        claim = exemption_claim(relative, text)
        if claim is None:
            continue
        kind, reason, _number = claim
        assert exemption_place_ok(relative), f"{relative}: marker where it grants nothing"
        assert len(reason) >= EXEMPT_MIN_REASON, relative
        assert any(exemption_site_ok(relative, kind, text, line) for line in text.splitlines()), (
            f"{relative}: claims {kind} and is not one"
        )
        assert any(relative.startswith(prefix) for prefix in EXEMPT_DIRS), relative
