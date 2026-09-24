{{ config(materialized='table') }}

-- fct_pitch -- SOP step W2.18, the marts layer.
--
-- One row per Statcast pitch, grain (game_pk, at_bat_number, pitch_number),
-- carrying the fct_pitch column list of SOP section 2.6 and the five columns
-- every mart carries: regime, level, season, official_date, analysis_set. The
-- work is done in int_pitch; this model is the published shape of it, cut to
-- the contract, with the home-plate umpire attached.
--
-- umpire_hp_id is here because DT-19 asserts that every pitch resolves to a row
-- of dim_umpire_game. int_pitch's umpire_raw, the Statcast CSV's deprecated
-- umpire column, is dropped: DT-03 asserts it is empty, and carrying an empty
-- column into a mart invites a model to read it.
--
-- THREE CALL COLUMNS, NOT ONE. description is Statcast's own word. call_final
-- is that word folded into the feed's two, ball and strike, and per SOP D-62 it
-- is the call after any challenge. call_original is the umpire's call before
-- the challenge. SOP risk R-05 is that reading call_final as the umpire's call
-- scores about 4,716 overturns as correct, in the exact band where the contour
-- is estimated, so the three stay separate all the way to the model.
--
-- The rows past the last open day were already dropped by int_pitch.

with pitches as (

    select *
    from {{ ref('int_pitch') }}
    where official_date <= date '{{ var("last_open_date") }}'

),

umpires as (

    select
        game_pk,
        hp_umpire_id
    from {{ ref('dim_umpire_game') }}

)

select
    pitches.pitch_uid                                          as pitch_uid,
    pitches.game_pk                                            as game_pk,
    pitches.at_bat_number                                      as at_bat_number,
    pitches.pitch_number                                       as pitch_number,
    pitches.level                                              as level,
    pitches.season                                             as season,
    pitches.official_date                                      as official_date,
    pitches.game_type                                          as game_type,
    pitches.regime                                             as regime,
    pitches.analysis_set                                       as analysis_set,
    pitches.plate_x_mid                                        as plate_x_mid,
    pitches.plate_z_mid                                        as plate_z_mid,
    pitches.plate_x_front                                      as plate_x_front,
    pitches.plate_z_front                                      as plate_z_front,
    pitches.plane_source                                       as plane_source,
    pitches.sz_top                                             as sz_top,
    pitches.sz_bot                                             as sz_bot,
    pitches.sz_top_h                                           as sz_top_h,
    pitches.sz_bot_h                                           as sz_bot_h,
    pitches.batter_height_in                                   as batter_height_in,
    pitches.height_source                                      as height_source,
    pitches.tracked                                            as tracked,
    pitches.balls                                              as balls,
    pitches.strikes                                            as strikes,
    pitches.outs_when_up                                       as outs_when_up,
    pitches.inning                                             as inning,
    pitches.inning_topbot                                      as inning_topbot,
    pitches.stand                                              as stand,
    pitches.p_throws                                           as p_throws,
    pitches.fielder_2                                          as fielder_2,
    pitches.batter                                             as batter,
    pitches.pitcher                                            as pitcher,
    pitches.pitch_type                                         as pitch_type,
    pitches.release_speed                                      as release_speed,
    pitches.vx0                                                as vx0,
    pitches.vy0                                                as vy0,
    pitches.vz0                                                as vz0,
    pitches.ax                                                 as ax,
    pitches.ay                                                 as ay,
    pitches.az                                                 as az,
    pitches.description                                        as description,
    pitches.call_final                                         as call_final,
    pitches.call_original                                      as call_original,
    pitches.play_id                                            as play_id,
    pitches.delta_run_exp                                      as delta_run_exp,
    pitches.delta_home_win_exp                                 as delta_home_win_exp,
    pitches.home_win_exp                                       as home_win_exp,
    pitches.bat_win_exp                                        as bat_win_exp,
    pitches.home_score_diff                                    as home_score_diff,
    pitches.bat_score_diff                                     as bat_score_diff,
    pitches.bat_score                                          as bat_score,
    pitches.post_bat_score                                     as post_bat_score,
    pitches.on_1b                                              as on_1b,
    pitches.on_2b                                              as on_2b,
    pitches.on_3b                                              as on_3b,
    pitches.edge_dist_in                                       as edge_dist_in,
    pitches.edge_dist_r_in                                     as edge_dist_r_in,
    pitches.in_zone_center                                     as in_zone_center,
    pitches.challenged                                         as challenged,
    pitches.is_overturned                                      as is_overturned,
    umpires.hp_umpire_id                                       as umpire_hp_id
from pitches
left join umpires
    on pitches.game_pk = umpires.game_pk
