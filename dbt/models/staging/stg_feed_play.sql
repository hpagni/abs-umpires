{{ config(materialized='view') }}

-- stg_feed_play -- SOP step W2.17, the staging layer.
--
-- One row per plate appearance of the GUMBO play-by-play, grain
-- (game_pk, at_bat_index), which W2.13 lands in interim/feed_play. Renames and
-- casts only.
--
-- The feed numbers plate appearances from zero. DT-05 asserts
-- at_bat_number == at_bat_index + 1 on 100% of rows, and the addition belongs
-- to the layer that joins, not to a staging model that renames.
--
-- There is no catcher on the play object. The per-pitch catcher is Statcast
-- fielder_2 (SOP W2.13).

with source as ( {{ lake_scan('feed_play', [
    'game_pk', 'at_bat_index', 'batter_id', 'bat_side', 'pitcher_id',
    'pitch_hand', 'result_event_type', 'result_description', 'last_pitch_slot',
    'about_has_review', 'level', 'season', 'official_date']) }} )

select
    cast(game_pk as bigint)                                    as game_pk,
    cast(at_bat_index as integer)                              as at_bat_index,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(official_date as date)                                as official_date,
    cast(batter_id as bigint)                                  as batter_id,
    cast(bat_side as varchar)                                  as bat_side,
    cast(pitcher_id as bigint)                                 as pitcher_id,
    cast(pitch_hand as varchar)                                as pitch_hand,
    cast(result_event_type as varchar)                         as result_event_type,
    cast(result_description as varchar)                        as result_description,
    cast(last_pitch_slot as integer)                           as last_pitch_slot,
    cast(about_has_review as boolean)                          as about_has_review
from source
