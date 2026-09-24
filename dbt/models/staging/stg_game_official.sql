{{ config(materialized='view') }}

-- stg_game_official -- SOP step W2.17, the staging layer.
--
-- One row per official per game, from the schedule endpoint's officials block,
-- which W2.5 lands in interim/game_official. Renames and casts only.
--
-- official_type is 'Home Plate', 'First Base', 'Second Base' or 'Third Base'.
-- The home-plate row is the umpire every Chapter 1 fit groups on. The Statcast
-- CSV's own `umpire` column is empty in every export and is never the source;
-- DT-03 asserts that on the built warehouse.
--
-- The source names the day `date`. It equals the schedule's official_date on
-- 18,754 of 18,754 home-plate rows on this machine, so the rename states what
-- the column is rather than where it was written.

with source as ( {{ lake_scan('game_official', [
    'game_pk', 'official_type', 'official_id', 'official_name',
    'level', 'season', 'date']) }} )

select
    cast(game_pk as bigint)                                    as game_pk,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(date as date)                                         as official_date,
    cast(official_type as varchar)                             as official_type,
    cast(official_id as integer)                               as official_id,
    cast(official_name as varchar)                             as official_name
from source
