{{ config(materialized='view') }}

-- int_challenge_opportunity -- SOP step W2.17, the intermediate layer.
--
-- Two rows per called pitch in a challenge-system game, one per side, grain
-- (game_pk, at_bat_number, pitch_number, acting_side). This is the denominator
-- Chapter 2 needs: a challenge rate is challenges over chances to challenge,
-- and a chance exists for a side only when it holds a token and the call on the
-- pitch went against it.
--
-- POPULATION. regime in ('abs_2026', 'aaa_challenge'), the two regimes where a
-- team may challenge at all. Full-ABS AAA games have no challenge and no
-- opportunity, and the pre-2026 MLB regimes have no system.
--
-- THE RULE THIS ENCODES. Only the batting side may challenge a called strike
-- and only the fielding side may challenge a called ball. The feed states it
-- twice over: the standing implied by call_original names one team, and that
-- team is challengeTeamId on 10,168 of 10,168 MLB 2026 records, while the same
-- rule read on call_final names the wrong team on the 5,490 overturns
-- (W2.16). So eligibility is read from call_original, the umpire's call, never
-- from call_final, the call that stood after the challenge.
--
-- THE TOKEN LEDGER. tokens_own is the side's starting allotment minus the
-- challenges it has already lost in that game, counted from
-- int_challenge_resolved, which is also where tokens_start and its estimator
-- are documented. tokens_opp is the same count for the other side. A side with
-- no token has no opportunity, which is what eligible says.
--
-- NOT BUILT HERE. m_star_in and g_wp in the fct_challenge_opportunity contract
-- are model quantities: the indifference distance and the win-probability
-- weight come from Chapter 2's fit in W4.6 and Chapter 3's surface in W5.3.
-- This model is their input, not their author.

with called as (

    select
        pitch_uid,
        game_pk,
        at_bat_number,
        pitch_number,
        level,
        season,
        official_date,
        regime,
        analysis_set,
        home_team_id,
        away_team_id,
        inning,
        inning_topbot,
        balls,
        strikes,
        outs_when_up,
        batter,
        pitcher,
        fielder_2,
        call_original,
        call_final,
        challenged,
        challenge_team_id,
        is_overturned,
        d_signed_in,
        at_bat_number * 1000 + pitch_number                    as pitch_ord
    from {{ ref('int_called_pitch') }}
    where regime in ('abs_2026', 'aaa_challenge')

),

tokens as (

    select
        game_pk,
        home_remaining + home_used_failed                      as home_tokens_start,
        away_remaining + away_used_failed                      as away_tokens_start
    from {{ ref('stg_feed_game') }}

),

-- The challenges each team lost, as a sorted list of pitch ordinals per
-- team-game. A list keeps the join to the called pitches an equi-join on
-- (game_pk, team_id); counting the losses before a pitch is then a filter on
-- the list rather than a second pass over 1.6 million rows.
losses as (

    select
        game_pk,
        challenge_team_id                                      as team_id,
        list_sort(list(at_bat_number * 1000 + pitch_number))    as loss_ords
    from {{ ref('int_challenge_resolved') }}
    where is_overturned = false
      and pitch_number is not null
    group by 1, 2

),

sides as (

    select 'bat' as acting_side
    union all
    select 'fld' as acting_side

),

paired as (

    select
        called.*,
        sides.acting_side                                      as acting_side,
        case
            when sides.acting_side = 'bat' then 'batter'
            else 'defense'
        end                                                    as role,
        case
            when (sides.acting_side = 'bat') = (called.inning_topbot = 'Top')
                then called.away_team_id
            else called.home_team_id
        end                                                    as acting_team_id,
        case
            when (sides.acting_side = 'bat') = (called.inning_topbot = 'Top')
                then called.home_team_id
            else called.away_team_id
        end                                                    as opponent_team_id
    from called
    cross join sides

)

select
    paired.pitch_uid                                           as pitch_uid,
    paired.game_pk                                             as game_pk,
    paired.at_bat_number                                       as at_bat_number,
    paired.pitch_number                                        as pitch_number,
    paired.acting_side                                         as acting_side,
    paired.acting_team_id                                      as acting_team_id,
    paired.opponent_team_id                                    as opponent_team_id,
    paired.role                                                as role,
    paired.level                                               as level,
    paired.season                                              as season,
    paired.official_date                                       as official_date,
    paired.regime                                              as regime,
    paired.analysis_set                                        as analysis_set,
    paired.inning                                              as inning,
    paired.inning_topbot                                       as inning_topbot,
    paired.balls                                               as balls,
    paired.strikes                                             as strikes,
    paired.outs_when_up                                        as outs_when_up,
    paired.batter                                              as batter,
    paired.pitcher                                             as pitcher,
    paired.fielder_2                                           as fielder_2,
    paired.call_original                                       as call_original,
    paired.call_final                                          as call_final,
    paired.d_signed_in                                         as d_signed_in,
    case
        when paired.acting_team_id = paired.home_team_id then own.home_tokens_start
        else own.away_tokens_start
    end
        - coalesce(len(list_filter(own_losses.loss_ords, o -> o < paired.pitch_ord)), 0)
                                                               as tokens_own,
    case
        when paired.opponent_team_id = paired.home_team_id then own.home_tokens_start
        else own.away_tokens_start
    end
        - coalesce(len(list_filter(opp_losses.loss_ords, o -> o < paired.pitch_ord)), 0)
                                                               as tokens_opp,
    case
        when paired.acting_side = 'bat' then paired.call_original = 'strike'
        else paired.call_original = 'ball'
    end                                                        as call_went_against,
    coalesce(
        case
            when paired.acting_team_id = paired.home_team_id then own.home_tokens_start
            else own.away_tokens_start
        end
            - coalesce(len(list_filter(own_losses.loss_ords, o -> o < paired.pitch_ord)), 0)
        > 0, false)
        and case
            when paired.acting_side = 'bat' then paired.call_original = 'strike'
            else paired.call_original = 'ball'
        end                                                    as eligible,
    paired.challenged and paired.challenge_team_id = paired.acting_team_id
                                                               as challenged,
    paired.is_overturned                                       as is_overturned
from paired
left join tokens as own
    on paired.game_pk = own.game_pk
left join losses as own_losses
    on paired.game_pk = own_losses.game_pk
   and paired.acting_team_id = own_losses.team_id
left join losses as opp_losses
    on paired.game_pk = opp_losses.game_pk
   and paired.opponent_team_id = opp_losses.team_id
