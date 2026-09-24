{{ config(materialized='view') }}

-- stg_feed_player -- SOP step W2.17, the staging layer.
--
-- One row per player per game, from the feed's gameData.players block, which
-- W2.13 lands in interim/feed_player. Renames and casts only.
--
-- height_in is the roster height the feed states, parsed from height_raw
-- ("6' 3\"" reads 75 in). It is not the ABS measured height: SOP section 2.5
-- records a batter whose roster height is 75 in while the 2026 zone implies
-- 75.1772 in. dim_batter_season carries both and names the source.

with source as ( {{ lake_scan('feed_player', [
    'game_pk', 'player_id', 'height_raw', 'height_in', 'weight',
    'primary_position', 'level', 'season', 'official_date']) }} )

select
    cast(game_pk as bigint)                                    as game_pk,
    cast(player_id as bigint)                                  as player_id,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(official_date as date)                                as official_date,
    cast(height_raw as varchar)                                as height_raw,
    cast(height_in as double)                                  as height_in,
    cast(weight as integer)                                    as weight,
    cast(primary_position as varchar)                          as primary_position
from source
