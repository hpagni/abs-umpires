"""W2.7 acceptance tests: batter heights, three tiers.

SOP W2.7 names four clauses, and each one has a test here under the name of the
clause:

* coverage >= 99.5% of called pitches per season 2022 to 2026;
* `sz_top*12*25.4/0.535` a multiple of 0.5 mm for >= 99% of 2026 batters and
  about 4% of 2025 batters;
* no batter-season with two `feed_roster` heights differing by more than 1 inch;
* `|o| < 1.0 in` and `sd(h_abs - h_roster) < 1.5 in`.

The rest of the module guards the two instructions in the same SOP paragraph
that are not clauses but are just as load-bearing: `gameData.players[].
strikeZoneTop/Bottom` is never read, and a feed height is read only for a player
who appears as `matchup.batter`.

Every threshold comes from `absump.heights`, which states each one once. A test
that repeated a number would let the two drift apart.

These tests read the built dimension. When it is absent they fail rather than
skip: `quality/steps.yml` lists the dimension in W2.7's `needs`, so a clean
clone with no 2026 datum on disk reports MISSING from `scripts/prove.sh` and
never reaches this file.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import polars as pl
import pytest

from absump import heights, paths

SEASONS = (2022, 2023, 2024, 2025, 2026)


@pytest.fixture(scope="module")
def dim() -> pl.DataFrame:
    frame = heights.read_dim("mlb")
    if frame.is_empty():
        pytest.fail(
            f"{heights.dim_dir()} holds no MLB batter-season rows. "
            "Run: uv run python -m absump.heights --build"
        )
    return frame


@pytest.fixture(scope="module")
def calibration() -> dict:
    return heights.read_calibration()


@pytest.fixture(scope="module")
def feed() -> pl.DataFrame:
    return heights.feed_summary(heights.feed_roster())


# --------------------------------------------------------------------------
# Clause 1. Coverage
# --------------------------------------------------------------------------


def test_coverage_is_at_least_995_of_called_pitches_per_season(dim: pl.DataFrame) -> None:
    """Every season 2022 to 2026 carries a height on >= 99.5% of called pitches."""
    seen = set()
    for season in sorted(dim["season"].unique().to_list()):
        summary = heights.season_summary(dim.filter(pl.col("season") == season))
        seen.add(season)
        assert summary["n_called"] > 0, f"season {season} has no called pitches"
        assert summary["coverage"] >= heights.COVERAGE_MIN, (
            f"season {season}: {summary['n_called_covered']} of {summary['n_called']} "
            f"called pitches carry a height, {summary['coverage']:.5f} < "
            f"{heights.COVERAGE_MIN}"
        )
    assert seen == set(SEASONS), f"seasons built: {sorted(seen)}, expected {list(SEASONS)}"


def test_every_covered_row_has_a_height_and_a_tier(dim: pl.DataFrame) -> None:
    """`height_source` is one of the three tiers, and it agrees with `height_in`."""
    tiers = {"abs_measured", "people_offset", "feed_roster"}
    sources = set(dim["height_source"].drop_nulls().unique().to_list())
    assert sources <= tiers, f"unknown height_source values: {sorted(sources - tiers)}"
    mismatched = dim.filter(pl.col("height_source").is_null() != pl.col("height_in").is_null())
    assert mismatched.height == 0, (
        f"{mismatched.height} rows carry a height without a tier, or a tier without a height"
    )
    implausible = dim.filter(
        pl.col("height_in").is_not_null() & ~pl.col("height_in").is_between(58.0, 84.0)
    )
    assert implausible.height == 0, f"{implausible.height} rows carry an implausible height"


def test_one_row_per_level_season_batter(dim: pl.DataFrame) -> None:
    keys = dim.select(["level", "season", "batter"])
    assert keys.height == keys.unique().height, "dim_batter_season has a duplicate key"


def test_abs_measured_height_is_back_linked_across_a_batters_seasons(
    dim: pl.DataFrame,
) -> None:
    """SOP W2.7 tier 1 reads `any` MLB 2026 or AAA 2023+ row, so the height
    belongs to the batter, not to the season it was measured in."""
    per_batter = (
        dim.filter(pl.col("h_abs_in").is_not_null())
        .group_by("batter")
        .agg(pl.col("h_abs_in").n_unique().alias("n"))
        .filter(pl.col("n") > 1)
    )
    assert per_batter.height == 0, (
        f"{per_batter.height} batters carry more than one ABS-measured height across seasons"
    )
    in_2026 = set(
        dim.filter((pl.col("season") == 2026) & pl.col("h_abs_in").is_not_null())[
            "batter"
        ].to_list()
    )
    earlier = dim.filter((pl.col("season") < 2026) & pl.col("batter").is_in(in_2026))
    assert earlier.filter(pl.col("h_abs_in").is_null()).height == 0, (
        "a batter measured in 2026 is missing that height in an earlier season"
    )


# --------------------------------------------------------------------------
# Clause 2. The half-millimetre signature
# --------------------------------------------------------------------------


def test_half_millimetre_signature_2026_and_2025(dim: pl.DataFrame) -> None:
    """The ABS measured height is stored at half-millimetre resolution.

    Counted over batter-days, the granularity of the figures SOP section
    "Zone definition" verified (321 batters on 2026-09-15, 184 on 2025-09-15).
    """
    share = {
        season: heights.season_summary(dim.filter(pl.col("season") == season))["half_mm_share"]
        for season in SEASONS
    }
    assert share[2026] >= heights.HALF_MM_2026_MIN, (
        f"2026 half-mm share {share[2026]:.4f} < {heights.HALF_MM_2026_MIN}"
    )
    low, high = heights.HALF_MM_2025_BAND
    assert low <= share[2025] <= high, (
        f"2025 half-mm share {share[2025]:.4f} outside {heights.HALF_MM_2025_BAND}"
    )
    assert share[2025] < share[2026] / 10, (
        "2025 must not look measured: it is operator-set per pitch through 2025"
    )


def test_stored_abs_measured_heights_land_on_the_half_millimetre_grid(
    dim: pl.DataFrame,
) -> None:
    """Every `abs_measured` height is on the grid, to a tenth of the tolerance."""
    rows = dim.filter(pl.col("height_source") == "abs_measured")
    assert rows.height > 0, "no batter-season carries an abs_measured height"
    mm = rows["height_in"].to_numpy() * 25.4
    off = abs(mm - (mm * 2).round() / 2)
    assert off.max() < heights.HALF_MM_TOLERANCE_MM / 10, (
        f"an abs_measured height sits {off.max():.6f} mm off the 0.5 mm grid"
    )


def test_the_two_verified_days_reproduce(dim: pl.DataFrame) -> None:
    """The SOP verified 321/321 batters on 2026-09-15 and 8/184 on 2025-09-15.

    This build measures 7 of 184 at a 1e-3 mm tolerance, so the 2025 assertion
    is a band around the recorded figure rather than the figure. The 2025 hits
    are the noise floor of the test: at 1e-4 mm not one of them survives, while
    a real ABS row is 3e-7 mm from the grid.
    """
    day_2026 = _day_file(2026, "2026-09-15")
    day_2025 = _day_file(2025, "2025-09-15")
    if day_2026 is None or day_2025 is None:
        pytest.skip("the two verified day files are not on this machine")
    total_2026, sig_2026 = _day_signature(day_2026)
    total_2025, sig_2025 = _day_signature(day_2025)
    assert (total_2026, sig_2026) == (321, 321), (
        f"2026-09-15: {sig_2026} of {total_2026} batters, SOP recorded 321 of 321"
    )
    assert total_2025 == 184, f"2025-09-15: {total_2025} batters, SOP recorded 184"
    assert 5 <= sig_2025 <= 12, f"2025-09-15: {sig_2025} of 184 batters, SOP recorded 8 of 184"


def _day_file(season: int, date: str) -> str | None:
    for candidate in heights.day_files("mlb", season):
        if date in candidate:
            return candidate
    return None


def _day_signature(path: str) -> tuple[int, int]:
    """(batters in the day file, batters with a half-millimetre `sz_top`)."""
    import duckdb

    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT TRY_CAST(batter AS BIGINT) AS batter, TRY_CAST(sz_top AS DOUBLE) AS sz_top "
            "FROM read_csv($file, header = true, union_by_name = true, sample_size = -1) "
            "WHERE batter IS NOT NULL AND sz_top IS NOT NULL",
            {"file": path},
        ).fetchall()
    finally:
        con.close()
    signature: dict[int, bool] = {}
    for batter, sz_top in rows:
        signature[batter] = signature.get(batter, False) or heights.is_half_mm(sz_top)
    return len(signature), sum(signature.values())


# --------------------------------------------------------------------------
# Clause 3. feed_roster consistency
# --------------------------------------------------------------------------


def test_no_batter_season_has_two_feed_roster_heights_over_an_inch_apart(
    feed: pl.DataFrame,
) -> None:
    assert feed.height > 0, "no feed_roster heights were read"
    wide = feed.filter(pl.col("feed_spread_in") > heights.FEED_SPREAD_MAX_IN)
    assert wide.height == 0, (
        f"{wide.height} batter-seasons carry two feed heights more than "
        f"{heights.FEED_SPREAD_MAX_IN} in apart: "
        f"{wide.head(5).select(['level', 'season', 'batter', 'feed_spread_in']).rows()}"
    )


def test_feed_heights_are_read_only_for_players_who_bat(dim: pl.DataFrame) -> None:
    """SOP W2.7 restricts any height identity assertion to `matchup.batter`.

    Every feed row therefore belongs to a batter-season that the Statcast pitch
    rows also know as a batter.
    """
    rows = heights.feed_roster()
    mlb_2026 = rows.filter((pl.col("level") == "mlb") & (pl.col("season") == 2026))
    if mlb_2026.is_empty():
        pytest.skip("no MLB 2026 feeds on this machine")
    known = set(dim.filter(pl.col("season") == 2026)["batter"].to_list())
    strays = sorted(set(mlb_2026["batter"].to_list()) - known)
    assert not strays, f"{len(strays)} feed heights belong to non-batters, e.g. {strays[:5]}"


def test_game_data_strike_zone_is_never_read() -> None:
    """`gameData.players[].strikeZoneTop/Bottom` is forbidden by SOP W2.7.

    74 of 281 pitches in `824466` disagree with the per-pitch `pitchData`
    values, and three pitchers in that game carry stale non-ABS values implying
    heights 7.1 to 7.2 inches apart. The check reads the parsed module rather
    than its text, so the two names may be discussed in a docstring and only a
    real dictionary key or attribute access fails it.
    """
    forbidden = ("strikeZoneTop", "strikeZoneBottom")
    tree = ast.parse(Path(heights.__file__).read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        holder = isinstance(
            node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        )
        if holder and node.body and isinstance(node.body[0], ast.Expr):
            value = node.body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                docstrings.add(id(value))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden:
            hits.append(node.attr)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            hits.extend(name for name in forbidden if name in node.value)
    assert not hits, f"absump.heights reads {sorted(set(hits))} from the feed; SOP W2.7 forbids it"


# --------------------------------------------------------------------------
# Clause 4. The calibration offset
# --------------------------------------------------------------------------


def test_calibration_offset_and_spread(calibration: dict) -> None:
    """`|o| < 1.0 in` and `sd(h_abs - h_roster) < 1.5 in` on the overlap cohort."""
    assert calibration["n_overlap"] > 0, "the overlap cohort is empty"
    offset = calibration["offset_in"]
    sd = calibration["sd_in"]
    assert abs(offset) < heights.OFFSET_MAX_IN, (
        f"|o| = {abs(offset):.4f} in is not under {heights.OFFSET_MAX_IN} in "
        f"on {calibration['n_overlap']} batters"
    )
    assert sd < heights.SD_MAX_IN, (
        f"sd(h_abs - h_roster) = {sd:.4f} in is not under {heights.SD_MAX_IN} in"
    )


def test_people_offset_rows_are_the_roster_height_plus_the_offset(
    dim: pl.DataFrame, calibration: dict
) -> None:
    rows = dim.filter(pl.col("height_source") == "people_offset")
    assert rows.height > 0, "no batter-season falls back to people_offset"
    residual = (rows["height_in"] - rows["h_roster_in"] - calibration["offset_in"]).abs().max()
    assert residual < 1e-9, f"a people_offset height is {residual} in off the tier rule"


# --------------------------------------------------------------------------
# The roster string, and the seal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("6' 3\"", 75.0),
        ("5' 11\"", 71.0),
        ("6'0\"", 72.0),
        ("6'", 72.0),
        ("6' 3", 75.0),
        (None, None),
        ("", None),
        ("183 cm", None),
        ("6 ft 3 in", None),
        ("2' 0\"", None),
    ],
)
def test_height_inches_parses_the_roster_string(text: str | None, expected: float | None) -> None:
    assert heights.height_inches(text) == expected


def test_the_build_reads_no_sealed_day(dim: pl.DataFrame) -> None:
    """B-2. The dimension is an open-side interim artifact.

    Every date from 2026-09-22 is sealed, so no day file after
    `paths.LAST_OPEN_DATE` may reach this build.
    """
    for season in SEASONS:
        for path in heights.day_files("mlb", season):
            stem = Path(path).parent.name.split("=")[-1] if "date=" in path else Path(path).stem
            assert not paths.is_sealed(stem), f"{path} is a sealed day"
    assert dt.date(2026, 9, 21) == paths.LAST_OPEN_DATE
