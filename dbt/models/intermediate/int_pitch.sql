{{ config(materialized='view') }}

-- int_pitch -- SOP step W2.17, the intermediate layer.
--
-- One row per Statcast pitch, grain (game_pk, at_bat_number, pitch_number),
-- carrying the columns the fct_pitch contract of SOP section 2.6 names, plus
-- regime, level, season, official_date and analysis_set on every row.
--
-- THE BOUNDARY. The where clause keeps rows on or before the last open day.
-- That selects exactly the rows the frozen predicate of SOP section 2.4 leaves
-- open, and it is written as a variable because GD-04 rule 5 fails on the first
-- held-out day written anywhere under dbt/. dbt/dbt_project.yml defines
-- last_open_date and it equals absump.paths.LAST_OPEN_DATE. Rows past it are
-- dropped here, before anything downstream can read them, and the dev target's
-- on-run-start hook fails the run if a stale table still holds any.
--
-- THE THREE COLUMNS THAT ARE NOT IN THE STATCAST CSV. play_id comes from
-- stg_pitch_joined, which W2.15 built, and is the only route to the Savant
-- drawer. regime and analysis_set come from int_regime. call_original comes
-- from the challenge record when the pitch was challenged.
--
-- CALLS, ONE VOCABULARY. The feed writes 'ball' and 'strike'; Statcast writes
-- 'called_strike', 'ball' and 'blocked_ball' and, per SOP D-62, its description
-- is the FINAL call, after any challenge. call_final is the Statcast
-- description folded into the feed's two words, and is null on a pitch that was
-- swung at or put in play. call_original is the umpire's call before the
-- challenge: the challenge record when there is one, and call_final otherwise,
-- because an unchallenged call is its own original.
--
-- umpire_raw is the Statcast CSV's deprecated `umpire` column. It is carried
-- here so DT-03 can assert on the built warehouse that it is empty, which is
-- what makes stg_game_official the only umpire source. It is not a fct_pitch
-- column and the mart drops it.

with pitches as (

    select *
    from {{ ref('stg_statcast_pitches') }}
    where official_date <= date '{{ var("last_open_date") }}'

),

games as (

    select
        game_pk,
        regime,
        regime_source,
        has_abs_challenges,
        analysis_set,
        home_team_id,
        away_team_id
    from {{ ref('int_regime') }}

),

bridge as (

    select
        game_pk,
        at_bat_number,
        pitch_number,
        play_id,
        pitch_slot,
        coord_err_ft
    from {{ ref('stg_pitch_joined') }}
    where pitch_number is not null

),

-- One challenge record per pitch. A pitch reviewed at more than one level
-- carries more than one row in the challenge table, and the event record is the
-- pitch-level one, so it wins; the play record is next and an additionalReviews
-- record last.
challenge as (

    select
        pitch_uid,
        review_level,
        is_overturned,
        call_original,
        challenge_team_id,
        challenger_id,
        challenger_role,
        tokens_remaining_before
    from {{ ref('int_challenge_resolved') }}
    where pitch_uid is not null
    qualify row_number() over (
        partition by pitch_uid
        order by case review_level
            when 'event' then 1
            when 'play' then 2
            else 3
        end
    ) = 1

),

folded as (

    select
        pitches.*,
        case
            when pitches.description = 'called_strike' then 'strike'
            when pitches.description in ('ball', 'blocked_ball') then 'ball'
        end                                                    as call_final
    from pitches

)

select
    folded.pitch_uid                                           as pitch_uid,
    folded.game_pk                                             as game_pk,
    folded.at_bat_number                                       as at_bat_number,
    folded.pitch_number                                        as pitch_number,
    folded.level                                               as level,
    folded.season                                              as season,
    folded.official_date                                       as official_date,
    folded.game_type                                           as game_type,
    games.regime                                               as regime,
    games.regime_source                                        as regime_source,
    games.has_abs_challenges                                   as has_abs_challenges,
    games.analysis_set                                         as analysis_set,
    games.home_team_id                                         as home_team_id,
    games.away_team_id                                         as away_team_id,
    bridge.play_id                                             as play_id,
    bridge.pitch_slot                                          as pitch_slot,
    bridge.coord_err_ft                                        as coord_err_ft,
    folded.plate_x_mid                                         as plate_x_mid,
    folded.plate_z_mid                                         as plate_z_mid,
    folded.plate_x_front                                       as plate_x_front,
    folded.plate_z_front                                       as plate_z_front,
    folded.plane_source                                        as plane_source,
    folded.sz_top                                              as sz_top,
    folded.sz_bot                                              as sz_bot,
    folded.sz_top_h                                            as sz_top_h,
    folded.sz_bot_h                                            as sz_bot_h,
    folded.batter_height_in                                    as batter_height_in,
    folded.height_source                                       as height_source,
    folded.tracked                                             as tracked,
    folded.in_zone_center                                      as in_zone_center,
    folded.edge_dist_in                                        as edge_dist_in,
    folded.edge_dist_r_in                                      as edge_dist_r_in,
    folded.balls                                               as balls,
    folded.strikes                                             as strikes,
    folded.outs_when_up                                        as outs_when_up,
    folded.inning                                              as inning,
    folded.inning_topbot                                       as inning_topbot,
    folded.on_1b                                               as on_1b,
    folded.on_2b                                               as on_2b,
    folded.on_3b                                               as on_3b,
    folded.stand                                               as stand,
    folded.p_throws                                            as p_throws,
    folded.batter                                              as batter,
    folded.pitcher                                             as pitcher,
    folded.fielder_2                                           as fielder_2,
    folded.pitch_type                                          as pitch_type,
    folded.pitch_name                                          as pitch_name,
    folded.release_speed                                       as release_speed,
    folded.vx0                                                 as vx0,
    folded.vy0                                                 as vy0,
    folded.vz0                                                 as vz0,
    folded.ax                                                  as ax,
    folded.ay                                                  as ay,
    folded.az                                                  as az,
    folded.zone                                                as zone,
    folded.description                                         as description,
    folded.events                                              as events,
    folded.call_final                                          as call_final,
    coalesce(challenge.call_original, folded.call_final)       as call_original,
    challenge.pitch_uid is not null                            as challenged,
    challenge.review_level                                     as review_level,
    challenge.is_overturned                                    as is_overturned,
    challenge.challenge_team_id                                as challenge_team_id,
    challenge.challenger_id                                    as challenger_id,
    challenge.challenger_role                                  as challenger_role,
    challenge.tokens_remaining_before                          as tokens_remaining_before,
    folded.bat_score                                           as bat_score,
    folded.post_bat_score                                      as post_bat_score,
    folded.home_score                                          as home_score,
    folded.away_score                                          as away_score,
    folded.home_score_diff                                     as home_score_diff,
    folded.bat_score_diff                                      as bat_score_diff,
    folded.home_win_exp                                        as home_win_exp,
    folded.bat_win_exp                                         as bat_win_exp,
    folded.delta_home_win_exp                                  as delta_home_win_exp,
    folded.delta_run_exp                                       as delta_run_exp,
    folded.umpire_raw                                          as umpire_raw
from folded
left join games
    on folded.game_pk = games.game_pk
left join bridge
    on folded.game_pk = bridge.game_pk
   and folded.at_bat_number = bridge.at_bat_number
   and folded.pitch_number = bridge.pitch_number
left join challenge
    on folded.pitch_uid = challenge.pitch_uid
