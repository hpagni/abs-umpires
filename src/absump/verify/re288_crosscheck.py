"""DT-27, second clause: an RE288 built from Retrosheet reproduces delta_run_exp.

SOP section 6.3, DT-27: "Retrosheet header identical 2015-2025; RE288 built
from it reproduces `delta_run_exp`", gate "<=0.01 runs per base-out-count
cell". The header clause is ``tests/data/test_retrosheet.py``. This module is
the second clause.

WHAT IS BUILT. The 288-state run expectancy, 24 base-out states by 12 counts,
from the Retrosheet ``plays.csv`` files for 2015-2025, the seasons SOP W2.12
names. A cell's value is the mean number of runs the batting team scores from
a pitch thrown at that state and count to the end of the half-inning.

  * Regular season only (``gametype == regular``), the population Statcast is
    compared on.
  * Half-innings that end with three outs only. A walk-off half-inning stops
    before its run expectancy is used up, so it is left out of the table, the
    usual convention for a run expectancy matrix.
  * One observation per pitch, as Statcast has one row per pitch. The counts a
    plate appearance passes through come from its ``pitches`` string: B, I, P
    and V are balls; C, S, K, L, M, O, Q, T and A are strikes; F and R are
    strikes below two strikes and nothing at two; X, Y and H end the count.
    N (no pitch) and the markers + * . 1 2 3 > are not pitches.
  * The base-out state of a pitch is the state of the row it belongs to. A
    plate appearance interrupted by a stolen base, a wild pitch or a pickoff is
    several rows, each carrying the cumulative pitch string; the pitches new to
    a row were thrown under that row's pre-play state. So a count reached
    before a stolen base is scored with the runner on first, and a count after
    it with the runner on second.

WHAT IT IS COMPARED WITH. Statcast ``delta_run_exp`` on the open MLB regular
seasons 2022-2025, read read-only through ``main_marts.v_pitch_open`` in
the warehouse file (``absump.paths.DUCKDB_PATH``). 2026 is never read. For every pitch the
Retrosheet-implied value is ``RE[next state] - RE[this state] + runs on the
pitch``, where the next state is the next pitch's state in the same
half-inning, or 0 when the half-inning is over. The gate compares, cell by
cell, the mean of Statcast's ``delta_run_exp`` with the mean of the
Retrosheet-implied value over the same pitches; ``abs_diff`` is that
difference and the bar is 0.01 runs.

Two further columns are reported, not gated: the RE288 built from Retrosheet
2022-2025 alone (the seasons Statcast is compared on), and the RE288 Statcast
itself implies, solved by least squares from every transition
(``delta_run_exp - runs = RE[next] - RE[this]``, with RE 0 at the end of a
half-inning).

    uv run --locked python -m absump.verify.re288_crosscheck

writes ``out/tables/re288_crosscheck.csv``, one row per cell, and prints the
maximum absolute difference. Exit 0 when every cell is inside the bar, 1 when
one is not, 2 when an input is missing.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final

import duckdb
import numpy as np

from absump import paths
from absump.ingest import retrosheet

__all__ = [
    "BAR_RUNS",
    "BASE_STATES",
    "CELLS",
    "OUT_PATH",
    "RETRO_SEASONS",
    "STATCAST_SEASONS",
    "build_re288",
    "cell_key",
    "compare",
    "count_path",
    "main",
    "pitch_rows",
    "statcast_moves",
    "warehouse_re288",
]

#: SOP DT-27: "<=0.01 runs per base-out-count cell".
BAR_RUNS: Final[float] = 0.01

#: SOP W2.12: the Retrosheet seasons.
RETRO_SEASONS: Final[tuple[int, ...]] = retrosheet.YEARS

#: The open MLB seasons that carry delta_run_exp. 2026 is not compared: the
#: comparison is a cross-check, and the seal keeps it to closed seasons.
STATCAST_SEASONS: Final[tuple[int, ...]] = (2022, 2023, 2024, 2025)

#: The matched build, reported beside the gated one.
MATCHED_SEASONS: Final[tuple[int, ...]] = STATCAST_SEASONS

OUT_PATH: Final[Path] = paths.REPO_ROOT / "out" / "tables" / "re288_crosscheck.csv"

#: First, second, third; 1/2/3 for occupied, - for empty. The warehouse's
#: fct_re288 spells base_state the same way.
BASE_STATES: Final[tuple[str, ...]] = tuple(a + b + c for a in "-1" for b in "-2" for c in "-3")
COUNTS: Final[tuple[tuple[int, int], ...]] = tuple((b, s) for b in range(4) for s in range(3))
CELLS: Final[tuple[tuple[int, str, int, int], ...]] = tuple(
    (outs, bases, b, s) for outs in range(3) for bases in BASE_STATES for b, s in COUNTS
)
_INDEX: Final[dict[tuple[int, str, int, int], int]] = {cell: i for i, cell in enumerate(CELLS)}

_BALLS: Final[frozenset[str]] = frozenset("BIPV")
_STRIKES: Final[frozenset[str]] = frozenset("CSKLMOQTA")
_FOULS: Final[frozenset[str]] = frozenset("FR")
_ENDS: Final[frozenset[str]] = frozenset("XYH")
_NOT_PITCHES: Final[frozenset[str]] = frozenset("N+*.123>")

_COLUMNS: Final[tuple[str, ...]] = (
    "outs",
    "base_state",
    "balls",
    "strikes",
    "re_retro",
    "n_retro",
    "ball_n_statcast",
    "ball_delta_statcast",
    "ball_delta_retro",
    "strike_n_statcast",
    "strike_delta_statcast",
    "strike_delta_retro",
    "abs_diff",
    "bar",
    "pass",
    "abs_diff_2022_2025",
    "re_retro_2022_2025",
    "re_warehouse",
    "n_warehouse",
    "diff_re_warehouse",
)


def cell_key(outs: int, bases: str, balls: int, strikes: int) -> tuple[int, str, int, int]:
    return (int(outs), str(bases), int(balls), int(strikes))


def count_path(pitches: str) -> list[tuple[int, int]] | None:
    """The count before each pitch in a Retrosheet pitch string, in order.

    Returns None when the string holds a character this module does not know
    (a U for an unknown pitch, a ? for a missing sequence), so the plate
    appearance is left out rather than guessed.
    """
    balls = strikes = 0
    out: list[tuple[int, int]] = []
    for char in pitches or "":
        if char in _NOT_PITCHES:
            continue
        if balls > 3 or strikes > 2:
            return None  # a pitch after ball four or strike three: not a count
        if char in _BALLS:
            out.append((balls, strikes))
            balls += 1
        elif char in _STRIKES:
            out.append((balls, strikes))
            strikes += 1
        elif char in _FOULS:
            out.append((balls, strikes))
            strikes = min(strikes + 1, 2) if strikes < 2 else strikes
        elif char in _ENDS:
            out.append((balls, strikes))
        else:
            return None
    return out


def _bases(first: Any, second: Any, third: Any) -> str:
    return ("1" if first else "-") + ("2" if second else "-") + ("3" if third else "-")


def _read_plays(season: int) -> list[tuple[Any, ...]]:
    path = retrosheet.unzipped_csv(season)
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; run python -m absump.ingest.retrosheet")
    con = duckdb.connect()
    try:
        return con.execute(
            """
            select gid, inning, top_bot, pa, outs_pre, outs_post, br1_pre, br2_pre, br3_pre,
                   score_v, score_h, runs, pitches
            from read_csv(?, header = true, all_varchar = true)
            where gametype = 'regular'
            """,
            [str(path)],
        ).fetchall()
    finally:
        con.close()


def pitch_rows(rows: Iterable[Sequence[Any]]) -> list[tuple[tuple[int, str, int, int], int]]:
    """(cell, runs to the end of the half-inning) for every pitch in ``rows``.

    ``rows`` are plays.csv rows in file order with the columns ``_read_plays``
    selects. Half-innings that end with fewer than three outs are dropped.
    """
    out: list[tuple[tuple[int, str, int, int], int]] = []
    rows = list(rows)
    start = 0
    while start < len(rows):
        gid, inning, half = rows[start][0], rows[start][1], rows[start][2]
        stop = start
        while stop < len(rows) and rows[stop][0:3] == (gid, inning, half):
            stop += 1
        block = rows[start:stop]
        start = stop
        batting = 9 if str(half) == "0" else 10  # score_v bats in the top, score_h in the bottom
        final_outs = max(int(r[5] or 0) for r in block)
        if final_outs < 3:
            continue
        end_score = max(int(r[batting] or 0) + int(r[11] or 0) for r in block)
        seen = 0  # pitches of the current plate appearance already attributed
        for row in block:
            ends_pa = str(row[3]) == "1"
            path = count_path(row[12] or "") if row[12] else []
            if path is None or not row[12]:
                # A substitution row carries no pitches and leaves the plate
                # appearance where it was; an unreadable string drops the rest
                # of the plate appearance rather than guessing its counts.
                seen = 0 if ends_pa else (seen if path is not None else 10**6)
                continue
            state_bases = _bases(row[6], row[7], row[8])
            outs = int(row[4] or 0)
            rest = end_score - int(row[batting] or 0)
            if outs <= 2:
                for balls, strikes in path[seen:]:
                    out.append((cell_key(outs, state_bases, balls, strikes), rest))
            seen = 0 if ends_pa else len(path)
    return out


_SEASON_SUMS: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _season_sums(season: int) -> tuple[np.ndarray, np.ndarray]:
    """(runs total, pitch count) per cell for one season, computed once."""
    if season not in _SEASON_SUMS:
        total = np.zeros(len(CELLS))
        count = np.zeros(len(CELLS))
        for cell, rest in pitch_rows(_read_plays(season)):
            index = _INDEX[cell]
            total[index] += rest
            count[index] += 1
        _SEASON_SUMS[season] = (total, count)
    return _SEASON_SUMS[season]


def build_re288(seasons: Iterable[int]) -> tuple[np.ndarray, np.ndarray]:
    """(re, n) over CELLS from the Retrosheet plays files of ``seasons``."""
    total = np.zeros(len(CELLS))
    count = np.zeros(len(CELLS))
    for season in seasons:
        season_total, season_count = _season_sums(int(season))
        total += season_total
        count += season_count
    with np.errstate(invalid="ignore", divide="ignore"):
        return total / count, count


_MOVES_SQL: Final[str] = """
with p as (
    select game_pk, at_bat_number, pitch_number, inning, inning_topbot,
           outs_when_up as outs,
           (case when on_1b is not null then '1' else '-' end)
             || (case when on_2b is not null then '2' else '-' end)
             || (case when on_3b is not null then '3' else '-' end) as bases,
           balls, strikes, bat_score, post_bat_score, delta_run_exp
    from main_marts.v_pitch_open
    where analysis_set = 'open' and level = 'mlb' and game_type = 'R'
      and season in (2022, 2023, 2024, 2025)
      and balls between 0 and 3 and strikes between 0 and 2 and outs_when_up between 0 and 2
),
q as (
    select *,
           lead(at_bat_number) over w as n_ab, lead(outs) over w as n_outs,
           lead(bases) over w as n_bases, lead(balls) over w as n_balls,
           lead(strikes) over w as n_strikes, lead(bat_score) over w as n_bat_score
    from p
    window w as (partition by game_pk, inning, inning_topbot
                 order by at_bat_number, pitch_number)
)
select outs, bases, balls, strikes,
       case when n_balls = balls + 1 then 'ball' else 'strike' end as move,
       count(*) as n, avg(delta_run_exp) as mean_delta, stddev_samp(delta_run_exp) as sd_delta
from q
where delta_run_exp is not null
  and n_ab = at_bat_number and n_outs = outs and n_bases = bases
  and post_bat_score = bat_score and n_bat_score = bat_score
  and ((n_balls = balls + 1 and n_strikes = strikes)
       or (n_balls = balls and n_strikes = strikes + 1))
group by all
"""

_FCT_SQL: Final[str] = """
select outs, base_state, balls, strikes, re, n
from main_marts.fct_re288
where analysis_set = 'open' and level = 'mlb'
"""


def _connect(db: Path | None) -> duckdb.DuckDBPyConnection:
    path = Path(db) if db is not None else paths.DUCKDB_PATH
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; the warehouse is built by dbt")
    return duckdb.connect(str(path), read_only=True)


def statcast_moves(
    db: Path | None = None,
) -> dict[tuple[tuple[int, str, int, int], str], tuple[int, float, float]]:
    """(cell, 'ball'|'strike') -> (n, mean delta_run_exp, sd) over pure count moves.

    A pure move is a pitch whose next pitch is in the same plate appearance
    with the same outs and runners, no run scored, and the count one ball or
    one strike further on. On such a pitch delta_run_exp is, by definition,
    RE[next count] - RE[this count] in Savant's own table and nothing else, so
    it is the one place the two tables can be compared term for term. A pitch
    on which a runner moves or scores is left out: Savant's value covers the
    pitch, not the running play that rode on it.
    """
    con = _connect(db)
    try:
        rows = con.execute(_MOVES_SQL).fetchall()
    finally:
        con.close()
    return {
        (cell_key(outs, bases, balls, strikes), move): (int(n), float(mean), float(sd or 0.0))
        for outs, bases, balls, strikes, move, n, mean, sd in rows
    }


def warehouse_re288(db: Path | None = None) -> dict[tuple[int, str, int, int], tuple[float, int]]:
    """The warehouse's Statcast-built RE288 (fct_re288), read-only."""
    con = _connect(db)
    try:
        rows = con.execute(_FCT_SQL).fetchall()
    finally:
        con.close()
    return {cell_key(o, b, ba, st): (float(re), int(n)) for o, b, ba, st, re, n in rows}


def _move_target(cell: tuple[int, str, int, int], move: str) -> tuple[int, str, int, int] | None:
    outs, bases, balls, strikes = cell
    if move == "ball":
        return (outs, bases, balls + 1, strikes) if balls < 3 else None
    return (outs, bases, balls, strikes + 1) if strikes < 2 else None


def compare(
    re: np.ndarray, moves: dict[tuple[tuple[int, str, int, int], str], tuple[int, float, float]]
) -> dict[tuple[int, str, int, int], dict[str, float]]:
    """Per cell and move: Statcast's mean delta_run_exp against RE[next] - RE[this]."""
    out: dict[tuple[int, str, int, int], dict[str, float]] = {}
    for cell in CELLS:
        entry: dict[str, float] = {}
        for move in ("ball", "strike"):
            target = _move_target(cell, move)
            got = moves.get((cell, move))
            if target is None or got is None:
                continue
            n, mean, _sd = got
            retro = float(re[_INDEX[target]] - re[_INDEX[cell]])
            entry[f"{move}_n"] = n
            entry[f"{move}_statcast"] = mean
            entry[f"{move}_retro"] = retro
            entry[f"{move}_diff"] = mean - retro
        out[cell] = entry
    return out


def compare_moves(re: np.ndarray, moves: dict) -> list[float]:
    """Every |Statcast - Retrosheet| over every compared move, for a summary."""
    found: list[float] = []
    for entry in compare(re, moves).values():
        found.extend(abs(entry[k]) for k in ("ball_diff", "strike_diff") if k in entry)
    return found


def _fmt(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return ""
    return f"{value:.6f}"


def write_table(rows: list[dict[str, Any]], path: Path = OUT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def run(*, db: Path | None = None, out_path: Path = OUT_PATH, stream: Any = None) -> dict[str, Any]:
    """Build, compare, write the table. Returns the summary it prints."""
    out = stream if stream is not None else sys.stdout
    re, n_retro = build_re288(RETRO_SEASONS)
    re_matched, _ = build_re288(MATCHED_SEASONS)
    moves = statcast_moves(db)
    fct = warehouse_re288(db)
    gated = compare(re, moves)
    matched = compare(re_matched, moves)
    rows: list[dict[str, Any]] = []
    worst: list[tuple[float, tuple[int, str, int, int]]] = []
    fct_gap: list[float] = []
    for i, cell in enumerate(CELLS):
        entry = gated[cell]
        diffs = [abs(entry[k]) for k in ("ball_diff", "strike_diff") if k in entry]
        matched_diffs = [
            abs(matched[cell][k]) for k in ("ball_diff", "strike_diff") if k in matched[cell]
        ]
        worst_here = max(diffs) if diffs else None
        if worst_here is not None:
            worst.append((worst_here, cell))
        fct_re, fct_n = fct.get(cell, (float("nan"), 0))
        if np.isfinite(fct_re) and np.isfinite(re_matched[i]):
            fct_gap.append(abs(re_matched[i] - fct_re))
        rows.append(
            {
                "outs": cell[0],
                "base_state": cell[1],
                "balls": cell[2],
                "strikes": cell[3],
                "re_retro": _fmt(re[i]),
                "n_retro": int(n_retro[i]),
                "ball_n_statcast": int(entry.get("ball_n", 0)),
                "ball_delta_statcast": _fmt(entry.get("ball_statcast")),
                "ball_delta_retro": _fmt(entry.get("ball_retro")),
                "strike_n_statcast": int(entry.get("strike_n", 0)),
                "strike_delta_statcast": _fmt(entry.get("strike_statcast")),
                "strike_delta_retro": _fmt(entry.get("strike_retro")),
                "abs_diff": _fmt(worst_here),
                "bar": f"{BAR_RUNS:.2f}",
                "pass": ""
                if worst_here is None
                else ("true" if worst_here <= BAR_RUNS else "false"),
                "abs_diff_2022_2025": _fmt(max(matched_diffs) if matched_diffs else None),
                "re_retro_2022_2025": _fmt(re_matched[i]),
                "re_warehouse": _fmt(fct_re),
                "n_warehouse": int(fct_n),
                "diff_re_warehouse": _fmt(re_matched[i] - fct_re),
            }
        )
    write_table(rows, out_path)
    values = np.asarray([w for w, _ in worst])
    top, top_cell = max(worst)
    moves_all = compare_moves(re, moves)
    summary = {
        "cells_compared": len(worst),
        "cells_over_bar": int(np.sum(values > BAR_RUNS)),
        "max_abs_diff": float(top),
        "max_cell": top_cell,
        "median_abs_diff": float(np.median(values)),
        "moves_compared": len(moves_all),
        "max_abs_diff_2022_2025": float(
            max(
                max(abs(v[k]) for k in ("ball_diff", "strike_diff") if k in v)
                for v in matched.values()
                if v
            )
        ),
        "max_gap_warehouse": float(np.max(fct_gap)) if fct_gap else float("nan"),
        "median_gap_warehouse": float(np.median(fct_gap)) if fct_gap else float("nan"),
    }
    print(
        f"re288: Retrosheet {RETRO_SEASONS[0]}-{RETRO_SEASONS[-1]} regular season, "
        f"{int(n_retro.sum()):,} pitches; Statcast {STATCAST_SEASONS[0]}-{STATCAST_SEASONS[-1]} "
        f"open MLB regular season, {sum(v[0] for v in moves.values()):,} pure count moves",
        file=out,
    )
    print(
        f"re288: DT-27 max |delta_run_exp - (RE[next] - RE[this])| = {top:.4f} runs at "
        f"{top_cell}; {summary['cells_over_bar']} of {summary['cells_compared']} cells over "
        f"the {BAR_RUNS} bar; median {summary['median_abs_diff']:.4f}; "
        f"{'PASS' if top <= BAR_RUNS else 'FAIL'}",
        file=out,
    )
    print(
        f"re288: reported, not gated: the same with the 2022-2025 Retrosheet table, max "
        f"{summary['max_abs_diff_2022_2025']:.4f}; Retrosheet 2022-2025 against the warehouse's "
        f"Statcast-built fct_re288, max {summary['max_gap_warehouse']:.4f}, median "
        f"{summary['median_gap_warehouse']:.4f} runs",
        file=out,
    )
    shown = (
        out_path.relative_to(paths.REPO_ROOT)
        if out_path.is_relative_to(paths.REPO_ROOT)
        else out_path
    )
    print(f"re288: wrote {shown}", file=out)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m absump.verify.re288_crosscheck",
        description="DT-27: an RE288 built from Retrosheet against Statcast delta_run_exp.",
    )
    parser.add_argument(
        "--db", default=None, help="the warehouse file (default absump.paths.DUCKDB_PATH)"
    )
    parser.add_argument("--out", default=str(OUT_PATH), help="the table to write")
    parser.add_argument(
        "--report",
        action="store_true",
        help="write the table and exit 0 whatever the verdict; the verdict is still printed",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        summary = run(db=Path(args.db) if args.db else None, out_path=Path(args.out))
    except (FileNotFoundError, duckdb.Error) as exc:
        print(f"re288: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.report:
        return 0
    return 0 if summary["max_abs_diff"] <= BAR_RUNS else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main())
