{{ config(materialized='table') }}

-- fct_re288 -- SOP step W2.18, the marts layer.
--
-- Run expectancy by base-out-count state, grain (outs, base_state, balls,
-- strikes), which is 3 x 8 x 12 = 288 cells and is the SOP section 2.6
-- contract. re is the mean runs the batting team scores from that state to the
-- end of the half inning; n is the number of pitches that produced it.
--
-- int_re288_state does the arithmetic and states the population: MLB
-- regular-season pitches in the open analysis set, every season on disk. That
-- population is written here as two constant columns rather than left implied,
-- because a state table has no game and no day of its own and a reader who
-- filters on level would otherwise get nothing. There is no season column and
-- no official_date column: the table pools every season by design, and a null
-- date column would be counted as a sealed row by the dev target's
-- on-run-start guard, which compares by subtraction.
--
-- DT-27 cross-checks this table against Statcast's own delta_run_exp to 0.01
-- runs per cell.

select
    cast(outs as varchar) || ':' || base_state
        || ':' || cast(balls as varchar)
        || ':' || cast(strikes as varchar)                     as re288_key,
    outs                                                       as outs,
    base_state                                                 as base_state,
    balls                                                      as balls,
    strikes                                                    as strikes,
    re                                                         as re,
    n                                                          as n,
    'mlb'                                                      as level,
    'open'                                                     as analysis_set
from {{ ref('int_re288_state') }}
