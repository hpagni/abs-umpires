{{ config(materialized='view') }}

-- stg_pitch_joined -- SOP step W2.17, the staging layer.
--
-- The corrected join W2.15 lands in interim/pitch_joined: one row per feed
-- pitch slot, carrying the Statcast pitch_number that slot resolves to.
-- Renames and casts only.
--
-- This is the only bridge between the two pitch keys. The feed counts slots
-- inside a plate appearance, Statcast numbers pitches, and an unnumbered feed
-- event moves the two apart. match_side says which side a row was seen on:
-- 'both' is a matched pitch, 'api_unnumbered' is a feed slot with no Statcast
-- pitch, and those rows carry a null pitch_number. On this machine, MLB 2026
-- gives 691,287 matched of 691,502 slots.
--
-- play_id is the feed's playId UUID. The Statcast CSV carries none, so this
-- column is the only route from a Statcast pitch to the Savant drawer.

with source as ( {{ lake_scan('pitch_joined', [
    'game_pk', 'level', 'season', 'official_date', 'at_bat_number',
    'pitch_slot', 'pitch_number', 'match_side', 'unnumbered', 'play_id',
    'play_index', 'event_type', 'call_code', 'call_description', 'is_pitch',
    'is_strike', 'is_ball', 'is_in_play', 'pitch_type_code', 'p_x', 'p_z',
    'plane', 'api_x_at_plane', 'api_z_at_plane', 'csv_x_at_plane',
    'csv_z_at_plane', 'csv_description', 'csv_events', 'csv_tracked',
    'coord_err_ft']) }} )

select
    cast(game_pk as bigint)                                    as game_pk,
    cast(at_bat_number as integer)                             as at_bat_number,
    cast(pitch_slot as integer)                                as pitch_slot,
    cast(pitch_number as integer)                              as pitch_number,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(official_date as date)                                as official_date,
    cast(match_side as varchar)                                as match_side,
    cast(unnumbered as boolean)                                as unnumbered,
    cast(play_id as varchar)                                   as play_id,
    cast(play_index as integer)                                as play_index,
    cast(event_type as varchar)                                as event_type,
    cast(call_code as varchar)                                 as call_code,
    cast(call_description as varchar)                          as call_description,
    cast(is_pitch as boolean)                                  as is_pitch,
    cast(is_strike as boolean)                                 as is_strike,
    cast(is_ball as boolean)                                   as is_ball,
    cast(is_in_play as boolean)                                as is_in_play,
    cast(pitch_type_code as varchar)                           as pitch_type_code,
    cast(p_x as double)                                        as p_x,
    cast(p_z as double)                                        as p_z,
    cast(plane as varchar)                                     as plane,
    cast(api_x_at_plane as double)                             as api_x_at_plane,
    cast(api_z_at_plane as double)                             as api_z_at_plane,
    cast(csv_x_at_plane as double)                             as csv_x_at_plane,
    cast(csv_z_at_plane as double)                             as csv_z_at_plane,
    cast(csv_description as varchar)                           as csv_description,
    cast(csv_events as varchar)                                as csv_events,
    cast(csv_tracked as boolean)                               as csv_tracked,
    cast(coord_err_ft as double)                               as coord_err_ft
from source
