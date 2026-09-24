{{ config(materialized='view') }}

-- agg_closed_season_drift -- SOP step W2.18, the marts layer. The comparison
-- DT-20 tests.
--
-- One row per tracked mart per closed season that has been counted at least
-- twice, holding this build's count, the previous build's count and the
-- difference. DT-20 requires that difference to be zero, and the test that says
-- so is dt_20_closed_season_row_counts_have_no_drift in this directory's
-- schema.yml.
--
-- Ordering is by built_at then snapshot_id, so two snapshots written in the
-- same second still order deterministically. A pair whose previous count does
-- not exist produces no row, which is what makes the first build after a
-- full refresh pass.
--
-- The view is rebuilt from the ledger on every run, so it always compares the
-- snapshot this run wrote against the one before it.

with ledger as (

    select *
    from {{ ref('agg_closed_season_rowcount') }}

),

ordered as (

    select
        table_name,
        season,
        snapshot_id,
        built_at,
        n_rows,
        row_number() over (
            partition by table_name, season
            order by built_at desc, snapshot_id desc
        )                                                      as rn
    from ledger

),

paired as (

    select
        latest.table_name                                      as table_name,
        latest.season                                          as season,
        latest.snapshot_id                                     as snapshot_id,
        latest.built_at                                        as built_at,
        latest.n_rows                                          as n_rows,
        previous.snapshot_id                                   as previous_snapshot_id,
        previous.built_at                                      as previous_built_at,
        previous.n_rows                                        as previous_n_rows
    from ordered as latest
    join ordered as previous
        on latest.table_name = previous.table_name
       and latest.season = previous.season
       and previous.rn = 2
    where latest.rn = 1

)

select
    paired.*,
    paired.n_rows - paired.previous_n_rows                     as drift
from paired
