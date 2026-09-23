"""DT-26 and UT-14 for the Savant catcher-framing export. SOP step W4.4.

The gate this file registers is the validator in ``absump.ingest.savant_framing``,
not the network. It runs from a clean clone with no 2026 datum on disk:

* a synthetic export is built to the exact W4.4 measurement -- 13,808 bytes, 58
  rows, the 21 columns in the SOP order, a UTF-8 BOM, ``pitches`` 2,573 to 8,769
  and ``rv_tot`` -10.72 to +7.78 -- and must pass every clause;
* one mutation per clause must fail that clause and no other. If a clause is ever
  dropped from the validator, its mutation starts passing and this file goes red;
* the twelve URLs, the season range and the column list are compared against the
  SOP text character for character;
* ``pull()`` is checked to send exactly twelve requests, one per season, all
  through ``absump.http.get`` and none at import;
* when the real export is already in ``data/raw`` it is validated too, with the
  same validator. Until then that one test skips and the rest still gate.

The synthetic export is padded in its ``name`` field to reach 13,808 bytes
exactly. The padding is what makes the fixture meet the byte clause, and it is
deliberate: a fixture that cannot hit the measured byte count cannot prove that
the byte clause is still being checked.
"""

from __future__ import annotations

import pytest

from absump import http
from absump.ingest import savant_framing as framing

# SOP section 6.1, step W4.4, first sentence, copied character for character.
SOP_URL_2026 = (
    "https://baseballsavant.mlb.com/leaderboard/catcher-framing"
    "?year=2026&team=&min=q&type=catcher&sort=4&sortDir=desc&csv=true"
)

# SOP section 6.1, step W4.4, the column list as it is written there.
SOP_COLUMNS = (
    "id,name,pitches,rv_tot,pct_tot,rv_11,pct_11,rv_12,pct_12,rv_13,pct_13,"
    "rv_14,pct_14,rv_16,pct_16,rv_17,pct_17,rv_18,pct_18,rv_19,pct_19"
)


# ---------------------------------------------------------------- the fixture


def build_export(
    *,
    n_rows: int = framing.CONTRACT_ROWS,
    byte_target: int | None = framing.CONTRACT_BYTES,
    columns: tuple[str, ...] = framing.COLUMNS,
    bom: bool = True,
    min_pitches: int = framing.CONTRACT_MIN_PITCHES,
    max_pitches: int = framing.CONTRACT_MAX_PITCHES,
    min_rv: float = framing.CONTRACT_MIN_RV_TOT,
    max_rv: float = framing.CONTRACT_MAX_RV_TOT,
) -> bytes:
    """A framing export built to the W4.4 contract, or to a named deviation.

    Rows are sorted by ``rv_tot`` descending, which is what ``sort=4&sortDir=desc``
    asks the endpoint for. The first and last rows carry the exact bounds, so
    ``min`` and ``max`` over the column are the stated numbers and not a rounding
    of them.
    """
    rows = []
    for i in range(n_rows):
        span = max(n_rows - 1, 1)
        pitches = round(min_pitches + i * (max_pitches - min_pitches) / span)
        rv_tot = round(max_rv - i * (max_rv - min_rv) / span, 2)
        if i == 0:
            pitches, rv_tot = min_pitches, max_rv
        if i == n_rows - 1:
            pitches, rv_tot = max_pitches, min_rv
        record = {
            "id": f"{500000 + i * 37:06d}",
            "name": f"Catcher {i:02d}",
            "pitches": str(pitches),
            "rv_tot": f"{rv_tot:.2f}",
            "pct_tot": f"{50.0 + (i % 11) * 0.137:.3f}",
        }
        for zone in (11, 12, 13, 14, 16, 17, 18, 19):
            record[f"rv_{zone}"] = f"{-1.5 + ((i + zone) % 13) * 0.25:.3f}"
            record[f"pct_{zone}"] = f"{40.0 + ((i + zone) % 17) * 0.75:.3f}"
        rows.append(record)

    def render(pads: list[int]) -> bytes:
        lines = [",".join(columns)]
        for i, record in enumerate(rows):
            fields = []
            for column in columns:
                value = record.get(column, "")
                if column == "name":
                    value = value + "x" * pads[i]
                fields.append(value)
            lines.append(",".join(fields))
        text = "".join(line + "\n" for line in lines)
        return (framing.BOM if bom else b"") + text.encode("utf-8")

    pads = [0] * n_rows
    raw = render(pads)
    if byte_target is None or n_rows == 0:
        return raw
    deficit = byte_target - len(raw)
    if deficit < 0:
        raise AssertionError(f"the synthetic export is already {-deficit} B past {byte_target} B")
    per, extra = divmod(deficit, n_rows)
    pads = [per + (1 if i < extra else 0) for i in range(n_rows)]
    raw = render(pads)
    assert len(raw) == byte_target
    return raw


def failed_clauses(checks: tuple[framing.Check, ...]) -> set[str]:
    return {check.clause for check in checks if not check.passed}


@pytest.fixture(scope="module")
def conforming() -> bytes:
    return build_export()


# ------------------------------------------------------------ the request plan


def test_url_reproduces_the_sop_line_character_for_character():
    assert framing.framing_url(2026) == SOP_URL_2026


def test_the_framing_endpoint_is_not_the_abs_challenges_endpoint():
    """W4.2's contract is the opposite one and must never be pasted over this."""
    url = framing.framing_url(2026)
    assert "/leaderboard/catcher-framing" in url
    assert "/leaderboard/abs-challenges" not in url
    assert "season%5B%5D" not in url
    assert "csv=true" in url


def test_twelve_seasons_2015_to_2026():
    assert list(framing.SEASONS) == list(range(2015, 2027))
    assert len(framing.SEASONS) == 12


def test_twelve_urls_one_per_season_all_on_savant():
    urls = framing.season_urls()
    assert len(urls) == 12
    assert len(set(urls)) == 12
    assert all(url.startswith(f"https://{framing.HOST}/") for url in urls)
    for season, url in zip(framing.SEASONS, urls, strict=True):
        assert f"year={season}&" in url
        assert "min=q&" in url


def test_a_season_outside_the_range_is_refused():
    with pytest.raises(ValueError):
        framing.framing_url(2014)
    with pytest.raises(ValueError):
        framing.framing_url(2027)


def test_the_min_one_twin_differs_only_in_the_min_parameter():
    left = framing.framing_url(2026, min_param=framing.MIN_QUALIFIED)
    right = framing.framing_url(2026, min_param=framing.MIN_ONE)
    assert left.replace("&min=q&", "&min=1&") == right


def test_the_chokepoint_accepts_the_framing_url_without_sending_anything(monkeypatch):
    """absump.http refuses csv=true on the ABS leaderboard. Not on this one."""
    monkeypatch.setenv("ABSUMP_DRY_RUN", "1")
    response = http.get(framing.framing_url(2026))
    assert response.dry_run is True
    assert response.content == b""


# ---------------------------------------------------------------- the columns


def test_columns_are_the_twenty_one_the_sop_names_in_that_order():
    assert ",".join(framing.COLUMNS) == SOP_COLUMNS
    assert len(framing.COLUMNS) == 21 == framing.N_COLUMNS


def test_fiftyeight_qualified_catchers_not_the_hundred_and_seven_abs_view():
    """D-35: the min= parameter is ignored, so the file is qualified catchers."""
    assert framing.QUALIFIED_CATCHERS == 58
    assert framing.ABS_VIEW_CATCHERS == 107
    assert framing.QUALIFIED_CATCHERS != framing.ABS_VIEW_CATCHERS


# ------------------------------------------------------------- UT-14, the BOM


def test_ut14_the_body_is_decoded_with_utf_8_sig(conforming):
    assert conforming.startswith(framing.BOM)
    text = framing.decode(conforming)
    assert not text.startswith("﻿")
    assert text.split("\n", 1)[0] == SOP_COLUMNS


def test_ut14_plain_utf_8_would_corrupt_the_first_column_name(conforming):
    """Why utf-8-sig is not optional: the BOM lands in the 'id' header."""
    first = conforming.decode("utf-8").split("\n", 1)[0]
    assert first.startswith("﻿")
    assert first.split(",")[0] != "id"


# ------------------------------------------------- DT-26 on a conforming file


def test_dt26_passes_on_an_export_built_to_the_measurement(conforming):
    checks = framing.verify_contract(
        2026,
        conforming,
        status_code=200,
        content_type="text/csv; charset=utf-8",
        min_one_raw=conforming,
    )
    assert failed_clauses(checks) == set(), framing.report(checks)


def test_dt26_checks_every_clause_the_sop_states(conforming):
    checks = framing.verify_contract(
        2026,
        conforming,
        status_code=200,
        content_type="text/csv",
        min_one_raw=conforming,
    )
    clauses = {check.clause for check in checks}
    assert {
        "status",
        "content_type",
        "bom",
        "columns",
        "bytes",
        "rows",
        "pitches_min",
        "pitches_max",
        "rv_tot_min",
        "rv_tot_max",
        "qualified_only",
        "min_ignored",
    } <= clauses


def test_the_fixture_is_the_measured_shape(conforming):
    table = framing.parse(conforming, season=2026)
    assert table.byte_length == 13808
    assert table.n_rows == 58
    assert table.columns == framing.COLUMNS
    pitches = [int(value) for value in table.column("pitches")]
    rv_tot = [float(value) for value in table.column("rv_tot")]
    assert (min(pitches), max(pitches)) == (2573, 8769)
    assert (round(min(rv_tot), 2), round(max(rv_tot), 2)) == (-10.72, 7.78)


# -------------------------------------------------- DT-26, one mutation each


@pytest.mark.parametrize(
    ("clause", "kwargs"),
    [
        ("bytes", {"byte_target": framing.CONTRACT_BYTES + 1}),
        ("rows", {"n_rows": 57}),
        ("bom", {"bom": False}),
        ("pitches_min", {"min_pitches": 2572}),
        ("pitches_max", {"max_pitches": 8770}),
        ("rv_tot_min", {"min_rv": -10.73}),
        ("rv_tot_max", {"max_rv": 7.79}),
    ],
)
def test_dt26_fails_the_clause_the_mutation_breaks(clause, kwargs):
    raw = build_export(**kwargs)
    checks = framing.verify_contract(2026, raw, status_code=200, content_type="text/csv")
    assert clause in failed_clauses(checks), framing.report(checks)


def test_dt26_fails_when_a_column_is_renamed():
    columns = tuple("rvtot" if name == "rv_tot" else name for name in framing.COLUMNS)
    raw = build_export(columns=columns)
    checks = framing.verify_contract(2026, raw, status_code=200, content_type="text/csv")
    assert "columns" in failed_clauses(checks)


def test_dt26_fails_when_a_column_is_dropped():
    columns = tuple(name for name in framing.COLUMNS if name != "pct_19")
    raw = build_export(columns=columns, byte_target=None)
    checks = framing.verify_contract(2026, raw, status_code=200, content_type="text/csv")
    assert "columns" in failed_clauses(checks)


def test_dt26_fails_on_a_non_csv_content_type(conforming):
    checks = framing.verify_contract(
        2026, conforming, status_code=200, content_type="text/html; charset=utf-8"
    )
    assert failed_clauses(checks) == {"content_type"}


def test_dt26_fails_on_a_non_200_status(conforming):
    checks = framing.verify_contract(2026, conforming, status_code=500, content_type="text/csv")
    assert failed_clauses(checks) == {"status"}


def test_dt26_fails_when_pitches_is_not_numeric(conforming):
    """Same length, so only the numeric clause can catch it."""
    broken = conforming.replace(b",2573,", b",abcd,", 1)
    assert len(broken) == len(conforming)
    checks = framing.verify_contract(2026, broken, status_code=200, content_type="text/csv")
    assert "numeric" in failed_clauses(checks), framing.report(checks)


# --------------------------------------- DT-26, the clause the step is about


def test_min_one_byte_identical_passes_when_the_bodies_match(conforming):
    checks = framing.verify_contract(2026, conforming, min_one_raw=bytes(conforming))
    assert "min_ignored" not in failed_clauses(checks)


def test_min_one_byte_identical_fails_on_a_single_changed_byte(conforming):
    twin = bytearray(conforming)
    twin[-2] = twin[-2] ^ 0x01
    checks = framing.verify_contract(2026, conforming, min_one_raw=bytes(twin))
    assert failed_clauses(checks) == {"min_ignored"}


def test_min_one_byte_identical_fails_on_a_longer_body(conforming):
    checks = framing.verify_contract(2026, conforming, min_one_raw=conforming + b"\n")
    assert "min_ignored" in failed_clauses(checks)


def test_the_min_clause_is_not_checked_when_the_twin_is_absent(conforming):
    checks = framing.verify_contract(2026, conforming)
    assert "min_ignored" not in {check.clause for check in checks}


# ------------------------------------------------- the other eleven seasons


def test_the_exact_2026_figures_are_not_imposed_on_an_earlier_season():
    """W4.4 measured 2026. 2015 has its own row count and its own byte count."""
    raw = build_export(n_rows=91, byte_target=None, min_pitches=1200, max_pitches=9900)
    checks = framing.verify_contract(2015, raw, status_code=200, content_type="text/csv")
    assert failed_clauses(checks) == set(), framing.report(checks)
    assert {"bytes", "rows", "pitches_min"} & {check.clause for check in checks} == set()


def test_the_column_list_is_required_in_every_season():
    columns = tuple("rvtot" if name == "rv_tot" else name for name in framing.COLUMNS)
    raw = build_export(n_rows=91, byte_target=None, columns=columns)
    checks = framing.verify_contract(2015, raw, status_code=200, content_type="text/csv")
    assert "columns" in failed_clauses(checks)


def test_the_bom_is_required_in_every_season():
    raw = build_export(n_rows=91, byte_target=None, bom=False)
    checks = framing.verify_contract(2015, raw, status_code=200, content_type="text/csv")
    assert "bom" in failed_clauses(checks)


# ------------------------------------------------------------------ the pull


def _response(url: str, body: bytes, *, from_cache: bool = False) -> http.Response:
    return http.Response(
        url=url,
        host=framing.HOST,
        status_code=200,
        content=body,
        dest_path=framing.REPO_ROOT / "data" / "raw" / "unused",
        sha256="",
        wire_bytes=len(body),
        disk_bytes=len(body),
        attempt=1,
        elapsed_s=0.0,
        from_cache=from_cache,
        headers={"content-type": "text/csv"},
    )


def test_pull_sends_twelve_requests_one_per_season(monkeypatch):
    sent: list[str] = []

    def fake_get(url, *, host_budget=True):
        sent.append(url)
        season = int(url.split("year=")[1].split("&")[0])
        body = build_export() if season == 2026 else build_export(n_rows=91, byte_target=None)
        return _response(url, body)

    monkeypatch.setattr(http, "get", fake_get)
    results = framing.pull()
    assert len(sent) == 12
    assert sent == list(framing.season_urls())
    assert [result.season for result in results] == list(range(2015, 2027))
    assert all(result.checks for result in results)


def test_pull_raises_when_a_season_breaks_its_contract(monkeypatch):
    def fake_get(url, *, host_budget=True):
        return _response(url, build_export(n_rows=57))

    monkeypatch.setattr(http, "get", fake_get)
    with pytest.raises(framing.ContractError) as excinfo:
        framing.pull(seasons=(2026,))
    assert "rows" in str(excinfo.value)


def test_pull_refuses_a_live_response_that_carries_no_content_type(monkeypatch):
    def fake_get(url, *, host_budget=True):
        response = _response(url, build_export())
        return http.Response(
            url=response.url,
            host=response.host,
            status_code=200,
            content=response.content,
            dest_path=response.dest_path,
            sha256="",
            wire_bytes=response.wire_bytes,
            disk_bytes=response.disk_bytes,
            attempt=1,
            elapsed_s=0.0,
            from_cache=False,
            headers={},
        )

    monkeypatch.setattr(http, "get", fake_get)
    with pytest.raises(framing.ContractError) as excinfo:
        framing.pull(seasons=(2026,))
    assert "content_type" in str(excinfo.value)


def test_probe_min_ignored_sends_the_twin_and_checks_byte_identity(monkeypatch):
    sent: list[str] = []
    body = build_export()

    def fake_get(url, *, host_budget=True):
        sent.append(url)
        return _response(url, body)

    monkeypatch.setattr(http, "get", fake_get)
    checks = framing.probe_min_ignored(2026)
    assert sent == [framing.framing_url(2026), framing.framing_url(2026, min_param="1")]
    assert "min_ignored" not in failed_clauses(checks)


def test_a_dry_run_pull_sends_nothing(monkeypatch):
    monkeypatch.setenv("ABSUMP_DRY_RUN", "1")
    results = framing.pull(seasons=(2026,))
    assert len(results) == 1
    assert results[0].dry_run is True
    assert results[0].table is None


# ------------------------------------------- the real bytes, once they exist


def test_the_cached_export_meets_dt26_when_the_pull_has_run():
    url = framing.framing_url(framing.CONTRACT_SEASON)
    body = framing.cached_body(url)
    if body is None:
        pytest.skip("no 2026 framing export in data/raw yet; the W4.4 pull has not run")
    checks = framing.verify_contract(framing.CONTRACT_SEASON, body)
    assert failed_clauses(checks) == set(), framing.report(checks)


def test_cached_body_is_none_for_a_url_the_manifest_never_recorded():
    assert framing.cached_body("https://baseballsavant.mlb.com/leaderboard/nothing-here") is None
