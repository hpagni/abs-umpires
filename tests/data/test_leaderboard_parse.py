"""The Savant ABS leaderboard page shape, pinned to a saved fixture (SOP W2.11, W4.3).

The fixtures in `fixtures/` are SYNTHETIC and deliberately so. Their structure --
the `<script>` block arrangement, the `serverParams`, `leagueData` and `absData`
assignments, every key name, the nesting and the container shapes -- is
byte-faithful to what Savant serves for the mlb/2026 views. Every numeric and
every player-identifying value in them is invented: round numbers and
placeholder names, recognisable as fake on sight.

Real values are not used because the live 2026 leaderboard is a whole-season
aggregate that moves every night, so any capture taken after the seal boundary
D-61 names -- the one date that lives in `config/seal.yml` and nowhere else --
sums in the nights held out behind it. DEV-40 measures exactly that growth in
this endpoint's sibling. Committing such a capture would carry held-out
quantities into the open tree, and no test here needs them: what is pinned is
page structure, not page content.

What these tests hold. The 2026-09-24 03:13 sweep lost all 28 views to one
sentence, "leagueData is not assigned an object", and still exited 0. The cause
was a shape change on the page, not a rename: `leagueData` moved from an object
keyed by side to a one-element array holding only the side the view belongs to.
`absData` and `serverParams` did not move. A further rename must fail here
loudly and by name instead of being swallowed by a sweep that carries on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from absump.ingest import savant_leaderboard as board

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


CATCHER = "savant_abs_catcher_synthetic.html"
BATTER = "savant_abs_batter_synthetic.html"


def test_absdata_is_found_by_the_w211_regex() -> None:
    """The SOP's own regex still matches. When it stops, the route changes."""
    page = board.parse_page(_fixture(CATCHER), view="catcher")
    assert page.absdata_route == "w2.11-regex"
    assert page.abs_data and all(isinstance(row, dict) for row in page.abs_data)
    assert {"n_challenges", "n_overturns", "n_fails"} <= set(page.abs_data[0])


def test_leaguedata_is_served_as_a_one_element_array() -> None:
    """The one-element-array shape, pinned. A return to the object shape also
    passes: both container shapes must key by side."""
    page = board.parse_page(_fixture(CATCHER), view="catcher")
    assert page.league_shape == "list"
    assert list(page.league_data) == ["fielding"]
    row = page.league_data["fielding"]
    assert {"n_total_sample", "n_challenges", "n_overturns", "n_fails"} <= set(row)
    assert all(isinstance(row[k], int) for k in ("n_total_sample", "n_challenges"))


def test_the_side_of_leaguedata_follows_the_view() -> None:
    """A batter page carries batting; a catcher page carries fielding."""
    batting = board.parse_page(_fixture(BATTER), view="batter")
    fielding = board.parse_page(_fixture(CATCHER), view="catcher")
    assert list(batting.league_data) == ["batting"]
    assert list(fielding.league_data) == ["fielding"]
    assert batting.league_shape == fielding.league_shape == "list"
    assert set(batting.league_data["batting"]) == set(fielding.league_data["fielding"])


def test_every_view_maps_to_a_side() -> None:
    """The map covers the seven challenge types the sweep enumerates, and only
    those. A new selector value on the page leaves this list short."""
    assert set(board.LEAGUE_SIDE_BY_VIEW) == {
        "batter",
        "batting-team",
        "catcher",
        "pitcher",
        "catching-team",
        "team-summary",
        "league",
    }


def test_serverparams_is_still_an_object() -> None:
    page = board.parse_page(_fixture(CATCHER), view="catcher")
    assert page.server_params["challengeType"] == "catcher"
    assert page.server_params["level"] == "mlb"


def test_a_renamed_absdata_is_found_in_a_script_block() -> None:
    """The fallback route: the array moves into a JSON script block."""
    page = board.parse_page(_fixture(CATCHER), view="catcher")
    blob = json.dumps({"props": {"rows": page.abs_data}})
    moved = (
        "<html><script>const serverParams = "
        + json.dumps(page.server_params)
        + ";\nconst leagueData = ["
        + json.dumps(page.league_data["fielding"])
        + "];\n</script>\n"
        + '<script type="application/json">'
        + blob
        + "</script></html>\n"
    )
    found = board.parse_page(moved, view="catcher")
    assert found.absdata_route == "script-block"
    assert len(found.abs_data) == len(page.abs_data)


def test_a_page_with_no_records_anywhere_raises() -> None:
    """A rename this module cannot follow must fail loudly, not return empty."""
    with pytest.raises(board.ParseError) as caught:
        board.parse_page(
            '<html><script>const serverParams = {"challengeType":"catcher"};\n'
            "const leagueData = [];\n</script></html>",
            view="catcher",
        )
    assert "no absData array" in str(caught.value)


def test_an_empty_view_parses_and_keys_nothing() -> None:
    """MLB 2025: serverParams pins validSeasons to [2026], so the view is empty.
    That is a reported result, not a parse failure."""
    page = board.parse_page(
        '<html><script>const serverParams = {"challengeType":"batter"};\n'
        "const leagueData = [];\nconst absData = [];\n</script></html>",
        view="batter",
    )
    assert page.abs_data == []
    assert page.league_data == {}
