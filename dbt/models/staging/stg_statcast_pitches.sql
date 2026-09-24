{{ config(materialized='view', tags=['smoke']) }}

-- stg_statcast_pitches -- SOP step W2.17, the staging layer. W1.11 wrote the
-- skeleton; this is the same model over the lake W2.14 landed.
--
-- One row per tracked pitch. Renames and casts only (SOP section 2.6): no
-- filter, no join, no derived measure. The analysis set, the regime and the
-- zone geometry are the intermediate layer's business, so a reader can see
-- exactly what the lake holds. On this machine the lake holds 3,108,070 rows,
-- MLB 2022 to 2026, and (game_pk, at_bat_number, pitch_number) is unique on
-- every one of them.
--
-- TWO READERS, ONE MODEL, TWO COLUMN LISTS. The ci target has no lake and no
-- warehouse file, so it builds over the 200-row synthetic seed and keeps the
-- skeleton's column list, which is what W1.11's smoke build and
-- mart_called_pitches read. Every other target reads interim/statcast_pitch,
-- which carries the columns the fct_pitch contract needs and does not carry
-- three the seed flattens in: official_date is the CSV's game_date,
-- has_abs_challenges is a feed_game column and reaches the models through
-- int_regime, and play_id is not in the Statcast CSV at all and reaches them
-- through stg_pitch_joined.
--
-- The lake read goes through lake_scan, so a clone with no data/ directory
-- builds this model empty instead of failing the run on a missing file.
--
-- umpire_raw is the CSV's deprecated `umpire` column, carried so that DT-03 can
-- assert it is empty where the analysis reads it. The home-plate umpire comes
-- from stg_game_official.

{% if target.name == 'ci' %}

with source as (select * from {{ ref('seed_synthetic_pitches') }})

select
    cast(game_pk as varchar)
        || ':' || cast(at_bat_number as varchar)
        || ':' || cast(pitch_number as varchar)                as pitch_uid,
    cast(game_pk as bigint)                                    as game_pk,
    cast(at_bat_number as integer)                             as at_bat_number,
    cast(pitch_number as integer)                              as pitch_number,
    cast(season as integer)                                    as season,
    cast(game_type as varchar)                                 as game_type,
    cast(official_date as date)                                as official_date,
    cast(level as varchar)                                     as level,
    cast(has_abs_challenges as boolean)                        as has_abs_challenges,
    cast(inning as integer)                                    as inning,
    cast(inning_topbot as varchar)                             as inning_topbot,
    cast(balls as integer)                                     as balls,
    cast(strikes as integer)                                   as strikes,
    cast(outs_when_up as integer)                              as outs_when_up,
    cast(batter as bigint)                                     as batter,
    cast(pitcher as bigint)                                    as pitcher,
    cast(fielder_2 as bigint)                                  as fielder_2,
    cast(stand as varchar)                                     as stand,
    cast(p_throws as varchar)                                  as p_throws,
    cast(pitch_type as varchar)                                as pitch_type,
    cast(release_speed as double)                              as release_speed,
    cast(plate_x as double)                                    as plate_x,
    cast(plate_z as double)                                    as plate_z,
    cast(sz_top as double)                                     as sz_top,
    cast(sz_bot as double)                                     as sz_bot,
    cast(description as varchar)                               as description,
    cast(play_id as varchar)                                   as play_id,
    cast(delta_run_exp as double)                              as delta_run_exp,
    cast(null as varchar)                                      as umpire_raw

{% else %}

with source as ( {{ lake_scan('statcast_pitch', [
    'game_pk', 'at_bat_number', 'pitch_number', 'level', 'season', 'game_type',
    'game_date', 'inning', 'inning_topbot', 'balls', 'strikes', 'outs_when_up', 'on_1b',
    'on_2b', 'on_3b', 'batter', 'pitcher', 'fielder_2', 'stand', 'p_throws', 'pitch_type',
    'pitch_name', 'release_speed', 'plate_x', 'plate_z', 'plate_x_mid', 'plate_z_mid',
    'plate_x_front', 'plate_z_front', 'plane_source', 'sz_top', 'sz_bot', 'sz_top_h',
    'sz_bot_h', 'batter_height_in', 'height_source', 'tracked', 'in_zone_center',
    'edge_dist_in', 'edge_dist_r_in', 'vx0', 'vy0', 'vz0', 'ax', 'ay', 'az', 'zone',
    'description', 'events', 'bat_score', 'post_bat_score', 'home_score', 'away_score',
    'home_score_diff', 'bat_score_diff', 'home_win_exp', 'bat_win_exp',
    'delta_home_win_exp', 'delta_run_exp', 'umpire']) }} )

select
    cast(game_pk as varchar)
        || ':' || cast(at_bat_number as varchar)
        || ':' || cast(pitch_number as varchar)                as pitch_uid,
    cast(game_pk as bigint)                                    as game_pk,
    cast(at_bat_number as integer)                             as at_bat_number,
    cast(pitch_number as integer)                              as pitch_number,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(game_type as varchar)                                 as game_type,
    cast(game_date as date)                                    as official_date,
    cast(inning as integer)                                    as inning,
    cast(inning_topbot as varchar)                             as inning_topbot,
    cast(balls as integer)                                     as balls,
    cast(strikes as integer)                                   as strikes,
    cast(outs_when_up as integer)                              as outs_when_up,
    cast(on_1b as bigint)                                      as on_1b,
    cast(on_2b as bigint)                                      as on_2b,
    cast(on_3b as bigint)                                      as on_3b,
    cast(batter as bigint)                                     as batter,
    cast(pitcher as bigint)                                    as pitcher,
    cast(fielder_2 as bigint)                                  as fielder_2,
    cast(stand as varchar)                                     as stand,
    cast(p_throws as varchar)                                  as p_throws,
    cast(pitch_type as varchar)                                as pitch_type,
    cast(pitch_name as varchar)                                as pitch_name,
    cast(release_speed as double)                              as release_speed,
    cast(plate_x as double)                                    as plate_x,
    cast(plate_z as double)                                    as plate_z,
    cast(plate_x_mid as double)                                as plate_x_mid,
    cast(plate_z_mid as double)                                as plate_z_mid,
    cast(plate_x_front as double)                              as plate_x_front,
    cast(plate_z_front as double)                              as plate_z_front,
    cast(plane_source as varchar)                              as plane_source,
    cast(sz_top as double)                                     as sz_top,
    cast(sz_bot as double)                                     as sz_bot,
    cast(sz_top_h as double)                                   as sz_top_h,
    cast(sz_bot_h as double)                                   as sz_bot_h,
    cast(batter_height_in as double)                           as batter_height_in,
    cast(height_source as varchar)                             as height_source,
    cast(tracked as boolean)                                   as tracked,
    cast(in_zone_center as boolean)                            as in_zone_center,
    cast(edge_dist_in as double)                               as edge_dist_in,
    cast(edge_dist_r_in as double)                             as edge_dist_r_in,
    cast(vx0 as double)                                        as vx0,
    cast(vy0 as double)                                        as vy0,
    cast(vz0 as double)                                        as vz0,
    cast(ax as double)                                         as ax,
    cast(ay as double)                                         as ay,
    cast(az as double)                                         as az,
    cast(zone as integer)                                      as zone,
    cast(description as varchar)                               as description,
    cast(events as varchar)                                    as events,
    cast(bat_score as integer)                                 as bat_score,
    cast(post_bat_score as integer)                            as post_bat_score,
    cast(home_score as integer)                                as home_score,
    cast(away_score as integer)                                as away_score,
    cast(home_score_diff as integer)                           as home_score_diff,
    cast(bat_score_diff as integer)                            as bat_score_diff,
    cast(home_win_exp as double)                               as home_win_exp,
    cast(bat_win_exp as double)                                as bat_win_exp,
    cast(delta_home_win_exp as double)                         as delta_home_win_exp,
    cast(delta_run_exp as double)                              as delta_run_exp,
    cast(umpire as varchar)                                    as umpire_raw

{% endif %}

from source
