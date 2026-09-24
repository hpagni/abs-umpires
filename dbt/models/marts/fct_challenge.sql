{{ config(materialized='table') }}

-- GD-04-EXEMPT: construction -- this model's own output is a fact table, and it reads
-- the pitch fact to attach the two distance columns. Restricting the BUILD to the
-- open set would change what the warehouse holds rather than what an analysis sees;
-- `assert_seal_not_crossed` keeps the seal on official_date.

-- fct_challenge -- SOP step W2.18, the marts layer.
--
-- One row per ABS review, grain (game_pk, at_bat_number, pitch_number,
-- review_level) with review_level in ('event', 'play', 'additional'), which is
-- the SOP section 2.6 contract. The reconciliation, the token arithmetic and
-- the pitch match are int_challenge_resolved's work; this model is the
-- published shape of it, with the two distance columns attached from the pitch.
--
-- THE DECLARED KEY AND THE ROW ID. challenge_key is the four-column key
-- written out. It is unique wherever pitch_number is known, which on this
-- machine is every MLB 2026 review, 10,168 of them. The AAA 2024 reviews carry
-- a null pitch_number because no AAA 2024 Statcast day is on disk to match
-- against, so 54 of them share a key with another review in the same at-bat and
-- the same review level. challenge_uid is the row id that is unique on all
-- 12,300 rows, and DT-18 tests both: challenge_uid everywhere, the declared key
-- where it is defined.
--
-- edge_dist_calc is the pitch's signed any-part-of-ball distance in inches,
-- SOP section 2.5, which that section records as reproducing Savant's column of
-- the same name to 0.000000 in on 1,276 of 1,276 rows.
--
-- m_signed_in is SOP W4.5's m, transcribed: +edge_dist_calc when the umpire
-- called a strike, because the batting side wants the pitch outside, and
-- -edge_dist_calc when he called a ball, because the fielding side wants it
-- inside. So m > 0 is exactly the challenge that should be overturned. It is
-- null when the review has no matched pitch or no original call. DT-23 checks
-- W4's independent computation of the same quantity against the drawer.
-- M1 must not condition on it: SOP D-64 excludes every post-hoc location
-- measure from that model's covariate set.
--
-- sz_challenge_prob and sz_challenge_runs are the two columns of the section
-- 2.6 list this step does not write. They are Savant drawer fields, pulled by
-- W4.2 into data/interim/ch2/, and no feed record carries them. Reported in the
-- W2.18 return.

with reviews as (

    select *
    from {{ ref('int_challenge_resolved') }}
    where official_date <= date '{{ var("last_open_date") }}'

),

pitches as (

    select
        pitch_uid,
        edge_dist_in,
        edge_dist_r_in
    from {{ ref('fct_pitch') }}

)

select
    reviews.challenge_uid                                      as challenge_uid,
    reviews.pitch_uid                                          as pitch_uid,
    reviews.game_pk                                            as game_pk,
    reviews.at_bat_number                                      as at_bat_number,
    reviews.pitch_number                                       as pitch_number,
    reviews.pitch_slot                                         as pitch_slot,
    reviews.pitch_matched                                      as pitch_matched,
    cast(reviews.game_pk as varchar)
        || ':' || cast(reviews.at_bat_number as varchar)
        || ':' || cast(reviews.pitch_number as varchar)
        || ':' || reviews.review_level                         as challenge_key,
    reviews.review_level                                       as review_level,
    reviews.is_overturned                                      as is_overturned,
    reviews.in_progress                                        as in_progress,
    reviews.review_type                                        as review_type,
    reviews.challenge_team_id                                  as challenge_team_id,
    reviews.challenger_id                                      as challenger_id,
    reviews.challenger_role                                    as challenger_role,
    reviews.challenger_identified                              as challenger_identified,
    reviews.opponent_id                                        as opponent_id,
    reviews.call_original                                      as call_original,
    reviews.call_final                                         as call_final,
    reviews.tokens_remaining_before                            as tokens_remaining_before,
    reviews.tokens_start                                       as tokens_start,
    pitches.edge_dist_in                                       as edge_dist_calc,
    pitches.edge_dist_r_in                                     as edge_dist_r_in,
    case
        when pitches.edge_dist_in is null then null
        when reviews.call_original = 'strike' then pitches.edge_dist_in
        when reviews.call_original = 'ball' then -pitches.edge_dist_in
    end                                                        as m_signed_in,
    reviews.batter_id                                          as batter_id,
    reviews.pitcher_id                                         as pitcher_id,
    reviews.catcher_id                                         as catcher_id,
    reviews.inning                                             as inning,
    reviews.is_top_inning                                      as is_top_inning,
    reviews.play_id                                            as play_id,
    reviews.level                                              as level,
    reviews.season                                             as season,
    reviews.official_date                                      as official_date,
    reviews.regime                                             as regime,
    reviews.analysis_set                                       as analysis_set
from reviews
left join pitches
    on reviews.pitch_uid = pitches.pitch_uid
