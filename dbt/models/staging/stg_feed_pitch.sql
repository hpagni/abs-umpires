{{ config(materialized='view') }}

-- stg_feed_pitch -- SOP step W2.17, the staging layer.
--
-- One row per pitch slot of the GUMBO play-by-play, grain
-- (game_pk, at_bat_number, pitch_slot), which W2.13 lands in
-- interim/feed_pitch. Renames and casts only.
--
-- pitch_slot is the feed's own position inside the plate appearance. It is not
-- the Statcast pitch_number: an unnumbered event shifts the two apart, which is
-- why W2.15 built the corrected join and why the bridge between the two keys
-- lives in stg_pitch_joined and not here.
--
-- call_code is the feed vocabulary: C called strike, B ball, *B blocked ball.

with source as ( {{ lake_scan('feed_pitch', [
    'game_pk', 'at_bat_number', 'pitch_slot', 'play_index', 'is_pitch',
    'event_type', 'call_code', 'call_description', 'pitch_type_code',
    'is_strike', 'is_ball', 'is_in_play', 'play_id', 'start_time_utc',
    'start_speed', 'end_speed', 'strike_zone_top', 'strike_zone_bottom',
    'strike_zone_width', 'strike_zone_depth', 'zone', 'type_confidence',
    'plate_time', 'extension', 'p_x', 'p_z', 'x0', 'y0', 'z0',
    'vx0', 'vy0', 'vz0', 'ax', 'ay', 'az', 'pfx_x', 'pfx_z', 'x', 'y',
    'break_angle', 'break_length', 'break_y', 'break_vertical',
    'break_vertical_induced', 'break_horizontal', 'spin_rate',
    'spin_direction', 'level', 'season', 'official_date']) }} )

select
    cast(game_pk as bigint)                                    as game_pk,
    cast(at_bat_number as integer)                             as at_bat_number,
    cast(pitch_slot as integer)                                as pitch_slot,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(official_date as date)                                as official_date,
    cast(play_index as integer)                                as play_index,
    cast(is_pitch as boolean)                                  as is_pitch,
    cast(event_type as varchar)                                as event_type,
    cast(call_code as varchar)                                 as call_code,
    cast(call_description as varchar)                          as call_description,
    cast(pitch_type_code as varchar)                           as pitch_type_code,
    cast(is_strike as boolean)                                 as is_strike,
    cast(is_ball as boolean)                                   as is_ball,
    cast(is_in_play as boolean)                                as is_in_play,
    cast(play_id as varchar)                                   as play_id,
    cast(start_time_utc as timestamptz)                        as start_time_utc,
    cast(start_speed as double)                                as start_speed,
    cast(end_speed as double)                                  as end_speed,
    cast(strike_zone_top as double)                            as strike_zone_top,
    cast(strike_zone_bottom as double)                         as strike_zone_bottom,
    cast(strike_zone_width as double)                          as strike_zone_width,
    cast(strike_zone_depth as double)                          as strike_zone_depth,
    cast(zone as integer)                                      as zone,
    cast(type_confidence as double)                            as type_confidence,
    cast(plate_time as double)                                 as plate_time,
    cast(extension as double)                                  as extension,
    cast(p_x as double)                                        as p_x,
    cast(p_z as double)                                        as p_z,
    cast(x0 as double)                                         as x0,
    cast(y0 as double)                                         as y0,
    cast(z0 as double)                                         as z0,
    cast(vx0 as double)                                        as vx0,
    cast(vy0 as double)                                        as vy0,
    cast(vz0 as double)                                        as vz0,
    cast(ax as double)                                         as ax,
    cast(ay as double)                                         as ay,
    cast(az as double)                                         as az,
    cast(pfx_x as double)                                      as pfx_x,
    cast(pfx_z as double)                                      as pfx_z,
    cast(x as double)                                          as x,
    cast(y as double)                                          as y,
    cast(break_angle as double)                                as break_angle,
    cast(break_length as double)                               as break_length,
    cast(break_y as double)                                    as break_y,
    cast(break_vertical as double)                             as break_vertical,
    cast(break_vertical_induced as double)                     as break_vertical_induced,
    cast(break_horizontal as double)                           as break_horizontal,
    cast(spin_rate as integer)                                 as spin_rate,
    cast(spin_direction as integer)                            as spin_direction
from source
