{{ config(materialized='view') }}

-- stg_schedule_game -- SOP step W2.17, the staging layer.
--
-- One row per scheduled game, from the statsapi schedule endpoint, which W2.4
-- lands in interim/schedule_game. Renames and casts only.
--
-- official_date is gameData.datetime.officialDate, never gameDate. SOP section
-- 2.4: a 2026-09-15 game can carry a gameDate one day later in UTC, and
-- partitioning on the UTC timestamp puts it on the wrong side of the boundary.
-- game_date_utc is kept beside it so the difference stays visible.
--
-- game_type is the code the analysis-set predicate reads: R regular, F wild
-- card, D division, L championship, W world series, S spring, A all-star,
-- E exhibition.

with source as ( {{ lake_scan('schedule_game', [
    'game_pk', 'season', 'level', 'game_type', 'official_date', 'game_date_utc',
    'status_abstract', 'status_coded', 'status_detailed',
    'away_team_id', 'home_team_id', 'doubleheader', 'game_number',
    'venue_id', 'game_id']) }} )

select
    cast(game_pk as bigint)                                    as game_pk,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(game_type as varchar)                                 as game_type,
    cast(official_date as date)                                as official_date,
    cast(game_date_utc as timestamptz)                         as game_date_utc,
    cast(status_abstract as varchar)                           as status_abstract,
    cast(status_coded as varchar)                              as status_coded,
    cast(status_detailed as varchar)                           as status_detailed,
    cast(away_team_id as integer)                              as away_team_id,
    cast(home_team_id as integer)                              as home_team_id,
    cast(doubleheader as varchar)                              as doubleheader,
    cast(game_number as integer)                               as game_number,
    cast(venue_id as integer)                                  as venue_id,
    cast(game_id as varchar)                                   as game_id
from source
