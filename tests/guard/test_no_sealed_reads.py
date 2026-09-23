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
    NON_CODE_SUFFIXES,
    REPO_ROOT,
    SCANNED_DIR_SKIPS,
    WALKED_ROOTS,
    Violation,
    boundary_date,
    is_excluded,
    is_scannable,
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


def test_the_only_exclusions_are_evidence() -> None:
    """Receipts and gate logs. Nothing that executes is excluded.

    This is the self-poisoning fix. A receipt quotes the guard's failure text
    verbatim, so scanning receipts made every red-team run write the file that
    turned the next run red. Neither directory is importable, runnable or
    compiled, so excluding them removes no read.
    """
    assert set(EXCLUDED_PREFIXES) == {"quality/receipts/", "logs/"}
    for prefix in EXCLUDED_PREFIXES:
        assert is_excluded(prefix + "anything.sql")
    for name in WALKED_ROOTS:
        assert not is_excluded(name + "/anything.sql"), f"{name}/ must not be excluded"


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
