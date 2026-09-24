{{ config(materialized='incremental') }}

-- GD-04-EXEMPT: measurement -- this model counts every row of every tracked mart per
-- closed season, which is what DT-20 compares against the previous nightly. A count
-- restricted to the open set could not see a held-out row appear in a closed season,
-- which is the one thing the ledger exists to see.

-- agg_closed_season_rowcount -- SOP step W2.18, the marts layer. The ledger
-- DT-20 reads.
--
-- DT-20 is "closed-season row counts 2022-2025 identical to the previous
-- nightly, 0 drift". A count cannot be compared with the previous run unless
-- the previous run wrote its count down, so this model is that record: one row
-- per build, per tracked mart, per closed season, appended and never rewritten.
-- agg_closed_season_drift does the comparison and the test lives there.
--
-- WHY 2022 TO 2025 AND NOT 2026. Those four seasons are finished. Their rows
-- can only change if the pipeline changed, which is exactly what DT-20 is for.
-- 2026 is still being played and its counts are supposed to move every night,
-- so including it would make the test fire on the pipeline working correctly.
--
-- THE SNAPSHOT ID is dbt's invocation_id, which is one value for one dbt
-- command and a different one for the next, so two builds in the same minute
-- are still two snapshots. built_at is run_started_at, the same clock for every
-- row of one snapshot, which is what makes the ordering in the drift model
-- total.
--
-- The grid is a cross join, so a table whose closed-season rows vanished
-- entirely still writes a row, with n_rows 0. Counting only what is there
-- would let a whole season disappear without the test seeing it.
--
-- THE MATERIALISATION is incremental with no unique key, so a run appends its
-- snapshot and leaves every earlier one alone. dbt build --full-refresh resets
-- the ledger to a single snapshot, and the first build after that has nothing
-- to compare against and passes with no rows, which is correct: a drift test
-- with one observation has no drift to report.
--
-- No official_date column. The grain is a build and a season, not a day.

with tracked as (

    select unnest([
        'dim_game',
        'dim_umpire_game',
        'fct_pitch',
        'fct_called_pitch',
        'fct_challenge',
        'fct_challenge_opportunity',
        'fct_team_game_tokens'
    ])                                                         as table_name

),

seasons as (

    select unnest([2022, 2023, 2024, 2025])                    as season

),

grid as (

    select tracked.table_name, seasons.season
    from tracked cross join seasons

),

counted as (

    select 'dim_game' as table_name, season, count(*) as n_rows
    from {{ ref('dim_game') }} group by 1, 2
    union all
    select 'dim_umpire_game', season, count(*)
    from {{ ref('dim_umpire_game') }} group by 1, 2
    union all
    select 'fct_pitch', season, count(*)
    from {{ ref('fct_pitch') }} group by 1, 2
    union all
    select 'fct_called_pitch', season, count(*)
    from {{ ref('fct_called_pitch') }} group by 1, 2
    union all
    select 'fct_challenge', season, count(*)
    from {{ ref('fct_challenge') }} group by 1, 2
    union all
    select 'fct_challenge_opportunity', season, count(*)
    from {{ ref('fct_challenge_opportunity') }} group by 1, 2
    union all
    select 'fct_team_game_tokens', season, count(*)
    from {{ ref('fct_team_game_tokens') }} group by 1, 2

)

select
    '{{ invocation_id }}'                                      as snapshot_id,
    cast('{{ run_started_at }}' as timestamp with time zone)   as built_at,
    grid.table_name                                            as table_name,
    grid.season                                                as season,
    coalesce(counted.n_rows, 0)                                as n_rows
from grid
left join counted
    on grid.table_name = counted.table_name
   and grid.season = counted.season
