# Data sources for plane-convention-vs-corrected

Every number on the figure, in the caption and in the alt text is read by
`plane-convention-vs-corrected.R` from the rows and columns below. No fit object
is loaded; no new fit is made; no per-game, per-pitch, per-player or per-umpire
datum is read. Values are printed to one decimal (band limits to zero decimals; the two 2025
area levels in the row 3 label to two decimals, so their difference rounds to the
printed plane component).

## `out/ch1/tab/T4_plane_component.csv`, row `estimand == "area_sqin"` (units column: `sq in`)

| column | value | where it appears |
|---|---:|---|
| `published_convention_change_point` | -19.9876821401359 | row 1 dot; printed −20.0 |
| `published_convention_change_lo95` | -28.2045160963776 | row 1 interval; printed −28.2 |
| `published_convention_change_hi95` | -12.9858303908721 | row 1 interval; printed −13.0 |
| `corrected_change_point` | -32.846030419492 | row 2 dot; printed −32.8 |
| `corrected_change_lo95` | -36.640593218863 | row 2 interval; printed −36.6 |
| `corrected_change_hi95` | -29.2918772832102 | row 2 interval; printed −29.3 |
| `point` | 12.8583482793561 | row 3 diamond; printed +12.9 |
| `lo95` | 6.25250959396778 | row 3 interval; printed 6.3 |
| `hi95` | 19.2020814259141 | row 3 interval; printed 19.2 |
| `theta_2025_mid` | 473.032058680372 | row 3 label; printed 473.03 |
| `theta_2025_front` | 460.173710401016 | row 3 label; printed 460.17 |
| `units` | sq in | guard that the row is in sq in |

## `out/ch1/tab/T9_published_comparison.csv`, row `quantity == "area_sqin"`

| column | value | where it appears |
|---|---:|---|
| `published_lo95` | -22 | left edge of the grey band; printed −22 |
| `published_hi95` | -8 | right edge of the grey band; printed −8 |
| `published_convention` | 2025 front-plane against 2026 mid-plane coordinates, through 25 April, batters in both seasons, 2026 heights in both | wording of the row 1 label (paraphrased) |
| `published_convention_change_point`, `corrected_change_point`, `plane_component_point` | as in T4 | equality guard against the T4 row; not drawn |

## Numbers that appear, with source

- −20.0 (−28.2 to −13.0): T4 `published_convention_change_point/_lo95/_hi95`.
- −32.8 (−36.6 to −29.3): T4 `corrected_change_point/_lo95/_hi95`.
- +12.9 (6.3 to 19.2): T4 `point/lo95/hi95` (component `plane`).
- 473.03 minus 460.17 sq in: T4 `theta_2025_mid`, `theta_2025_front`.
- −22 to −8 sq in: T9 `published_lo95`, `published_hi95`.
- 0: the dashed reference line, not a datum.
- Axis ticks −40 to 20 by 10: axis scale, not data.

Intervals are 95% throughout, as the column names state. The published range is
the 95% interval reported by the article named in T9 `published_source`; the
article title is not printed on the figure.
