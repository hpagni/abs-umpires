# W2.15 join report, full corpus

Written 2026-09-24 (Europe/Madrid). Machine state, not a claim about the seasons
themselves. The per-game rows live in `join_report.csv`; this file says what the
rows do and do not cover, and records the one coordinate exception.

## Coverage, per level and per season

| level | season | days joined | games | matched / api | status in the csv |
|---|---|---|---|---|---|
| mlb | 2026 | 178 | 2,342 | 691,287 / 691,287, 100.000% | 2,341 ok, 1 coord |
| mlb | 2025 | 0 | 0 | none | no_feed_pitch |
| mlb | 2024 | 0 | 0 | none | no_feed_pitch |
| mlb | 2023 | 0 | 0 | none | no_feed_pitch |
| mlb | 2022 | 0 | 0 | none | no_feed_pitch |
| aaa | 2025 | 0 | 0 | none | no_inputs |
| aaa | 2024 | 0 | 0 | none | no_inputs |
| aaa | 2023 | 0 | 0 | none | no_inputs |

What is actually on disk behind those statuses.

MLB 2022 to 2025 have the Statcast side and not the feed side. `statcast_pitch` holds
183 days for 2023, 185 for 2024, 184 for 2025 and 69 for 2022, and the raw Statcast
drawer holds 179 day files for 2022, which the running Savant pull is still filling, so
2022 is normalised behind its own raw. `feed_pitch` holds nothing for any of the four,
and `data/raw/statsapi/feed/sport=1` holds one feed JSON for 2025 and none for the other
three. A join needs both sides, so no game can be joined. Completing the feed side is a
statsapi pull of roughly 9,700 games, about 11 hours at the 4 s policy, which is an owner
decision and not something this step took on its own.

AAA has neither side. There is no AAA Statcast anywhere, raw or normalised, in either the
lake or the staging tree, and there is no AAA `feed_pitch`. AAA 2024 does have 665 staged
feed JSON files under `data/staging/statsapi/feeds/sport11/2024`, about 28 percent of the
2,345-game season, and those files are enough for the challenge work, which reads them,
but not for the join, which needs pitch coordinates. Until an AAA Statcast source lands
the AAA legs of W2.15 cannot produce a row, and the honest report is a coverage row.

A coverage row is `game_pk` empty, every count zero, and the reason in `status`. It is
written by `absump.ingest.join.coverage_row`, so the report distinguishes a season that
was requested and had nothing to join from a season nobody asked about.

## The coordinate exception, game 825000

One row of 688,686 checked breaches the 1e-6 ft assertion: game 825000, at-bat 31,
pitch 3, 2026-05-30, error 0.063625 ft. It is a Statcast artifact, and the evidence is
in `logs/evidence/W2.15-full-corpus.log`. In short. The API and the CSV carry the same
nine kinematic constants bit for bit. The CSV plate_x equals the re-projected API x at
the mid plane to the last bit, and the CSV plate_z sits 0.063625 ft above the API z. No
plane reproduces both published coordinates, so the published row is not a point on the
trajectory; the displacement is an exact decimal and the two z values share their
mantissa tail, which is what a constant added to a stored value looks like and not what
a recomputation looks like. Nothing is corrected. The game keeps status `coord`, the row
stays in `join_failures.csv`, and both z values put the pitch below sz_bot, so the zone
classification and the called strike are the same either way.
