{{ config(materialized='view') }}

-- stg_abs_leaderboard -- SOP step W2.17, the staging layer.
--
-- The Savant ABS leaderboard, one model per source so the DAG is complete.
-- W4.3 owns the 28-page sweep and interim/abs_leaderboard holds no bytes on
-- this machine yet, so lake_scan returns a zero-row select and the model builds
-- empty rather than failing the run on a file that is absent by design.
--
-- The three stub columns are the pull parameters contracts/savant_absdata.yml
-- fixes: 7 challenge types x 2 levels x 2 seasons = 28 pages. The measure
-- columns are not named here, because the row schema is settled by the bytes
-- W4.3 lands and guessing it now would put a wrong name in the warehouse
-- contract. When the table exists this model reads it whole and casts it, and
-- the cast list is added in the same change that lands the bytes.

with source as ( {{ lake_scan('abs_leaderboard', ['level', 'season', 'challenge_type']) }} )

select
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(challenge_type as varchar)                            as challenge_type
from source
