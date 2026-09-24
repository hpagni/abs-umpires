{{ config(materialized='table') }}

-- fct_challenge_opportunity -- SOP step W2.18, the marts layer.
--
-- One row per called pitch per acting side that could have challenged it,
-- grain (game_pk, at_bat_number, pitch_number, acting_side), which is the SOP
-- section 2.6 contract. The eligibility rule, the token counts and the
-- role assignment are int_challenge_opportunity's work; this model is the
-- published shape of it.
--
-- acting_side is 'bat' or 'fld'. role is the player who would have made the
-- call: batter, catcher or pitcher. eligible is whether that side still held a
-- token at that moment, which is what makes the row an opportunity rather than
-- a pitch.
--
-- m_star_in and g_wp are the two columns of the section 2.6 list this step does
-- not write. m_star_in is the perception threshold and g_wp the win-probability
-- gain from overturning, and SOP W5.2 to W5.6 build both from the WP surface
-- and the perception model, neither of which exists in the warehouse. Reported
-- in the W2.18 return.

with opportunities as (

    select *
    from {{ ref('int_challenge_opportunity') }}
    where official_date <= date '{{ var("last_open_date") }}'

)

select
    opportunities.pitch_uid                                    as pitch_uid,
    opportunities.game_pk                                      as game_pk,
    opportunities.at_bat_number                                as at_bat_number,
    opportunities.pitch_number                                 as pitch_number,
    opportunities.acting_side                                  as acting_side,
    cast(opportunities.game_pk as varchar)
        || ':' || cast(opportunities.at_bat_number as varchar)
        || ':' || cast(opportunities.pitch_number as varchar)
        || ':' || opportunities.acting_side                    as opportunity_key,
    opportunities.acting_team_id                               as acting_team_id,
    opportunities.opponent_team_id                             as opponent_team_id,
    opportunities.role                                         as role,
    opportunities.eligible                                     as eligible,
    opportunities.tokens_own                                   as tokens_own,
    opportunities.tokens_opp                                   as tokens_opp,
    opportunities.challenged                                   as challenged,
    opportunities.is_overturned                                as is_overturned,
    opportunities.call_original                                as call_original,
    opportunities.call_final                                   as call_final,
    opportunities.call_went_against                            as call_went_against,
    opportunities.d_signed_in                                  as d_signed_in,
    opportunities.balls                                        as balls,
    opportunities.strikes                                      as strikes,
    opportunities.outs_when_up                                 as outs_when_up,
    opportunities.inning                                       as inning,
    opportunities.inning_topbot                                as inning_topbot,
    opportunities.batter                                       as batter,
    opportunities.pitcher                                      as pitcher,
    opportunities.fielder_2                                    as fielder_2,
    opportunities.level                                        as level,
    opportunities.season                                       as season,
    opportunities.official_date                                as official_date,
    opportunities.regime                                       as regime,
    opportunities.analysis_set                                 as analysis_set
from opportunities
