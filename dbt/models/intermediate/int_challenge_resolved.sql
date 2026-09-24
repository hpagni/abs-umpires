{{ config(materialized='view') }}

-- int_challenge_resolved -- SOP step W2.17, the intermediate layer.
--
-- One row per ABS challenge, grain (game_pk, at_bat_number, pitch_slot,
-- review_level), resolved onto the Statcast pitch key and onto the team that
-- spent the token. This is the model that turns the feed's challenge records
-- into rows the pitch models can join.
--
-- THE PITCH KEY. The feed counts pitch slots inside a plate appearance and
-- Statcast numbers pitches, and an unnumbered feed event moves the two apart,
-- so a challenge reaches its Statcast pitch only through stg_pitch_joined.
-- pitch_matched says whether it did. On this machine every MLB 2026 challenge
-- matches and no AAA 2024 challenge does, because interim/pitch_joined holds
-- MLB 2026 only; the test on this model asserts the MLB 2026 half, so a
-- regression there is a failure and the AAA gap stays a stated gap.
--
-- THE TOKEN LEDGER. A successful challenge is returned and a failed one is
-- spent, so the tokens a team still holds before a challenge are its starting
-- allotment minus the challenges it has already lost in that game.
-- tokens_start is read from feed_game as remaining + used_failed for the side
-- that challenged. DT-08 asserts the canonical estimator, the per-game maximum
-- of `remaining` across the play-by-play, and that is W2.16's; the end-of-game
-- form used here disagrees with the MLB 2026 allotment of 2 on 36 of 4,632
-- team-games that carry the block, so tokens_start_source names the estimator
-- on every row rather than leaving the disagreement implicit.
--
-- AAA 2024 has no feed_game row on this machine, so its tokens are null. A null
-- is visible; a default of 2 would be a guess about a league whose allotment
-- SOP decision D-12 says is not settled.

with challenges as (

    select *
    from {{ ref('stg_abs_challenges') }}
    where official_date <= date '{{ var("last_open_date") }}'

),

games as (

    select
        game_pk,
        level,
        season,
        regime,
        analysis_set,
        home_team_id,
        away_team_id
    from {{ ref('int_regime') }}

),

tokens as (

    select
        game_pk,
        home_remaining + home_used_failed                      as home_tokens_start,
        away_remaining + away_used_failed                      as away_tokens_start
    from {{ ref('stg_feed_game') }}

),

bridge as (

    select
        game_pk,
        at_bat_number,
        pitch_slot,
        pitch_number
    from {{ ref('stg_pitch_joined') }}
    where pitch_number is not null

),

joined as (

    select
        challenges.*,
        games.regime                                           as regime,
        games.analysis_set                                     as analysis_set,
        games.home_team_id                                     as home_team_id,
        games.away_team_id                                     as away_team_id,
        bridge.pitch_number                                    as pitch_number,
        case
            when challenges.challenge_team_id = games.home_team_id
                then tokens.home_tokens_start
            when challenges.challenge_team_id = games.away_team_id
                then tokens.away_tokens_start
        end                                                    as tokens_start,
        case
            when challenges.challenge_team_id = games.home_team_id
                then games.away_team_id
            when challenges.challenge_team_id = games.away_team_id
                then games.home_team_id
        end                                                    as opponent_id,
        challenges.at_bat_number * 1000 + challenges.pitch_slot as challenge_ord
    from challenges
    left join games
        on challenges.game_pk = games.game_pk
    left join tokens
        on challenges.game_pk = tokens.game_pk
    left join bridge
        on challenges.game_pk = bridge.game_pk
       and challenges.at_bat_number = bridge.at_bat_number
       and challenges.pitch_slot = bridge.pitch_slot

),

ledger as (

    select
        joined.*,
        coalesce(sum(case when joined.is_overturned then 0 else 1 end) over (
            partition by joined.game_pk, joined.challenge_team_id
            order by joined.challenge_ord, joined.review_level
            rows between unbounded preceding and 1 preceding), 0) as failed_before
    from joined

)

select
    challenge_uid                                              as challenge_uid,
    slot_uid                                                   as slot_uid,
    case
        when pitch_number is null then null
        else cast(game_pk as varchar)
            || ':' || cast(at_bat_number as varchar)
            || ':' || cast(pitch_number as varchar)
    end                                                        as pitch_uid,
    game_pk                                                    as game_pk,
    at_bat_number                                              as at_bat_number,
    pitch_slot                                                 as pitch_slot,
    pitch_number                                               as pitch_number,
    pitch_number is not null                                   as pitch_matched,
    level                                                      as level,
    season                                                     as season,
    official_date                                              as official_date,
    regime                                                     as regime,
    analysis_set                                               as analysis_set,
    review_level                                               as review_level,
    review_type                                                as review_type,
    review_location                                            as review_location,
    resolved_by                                                as resolved_by,
    is_overturned                                              as is_overturned,
    in_progress                                                as in_progress,
    call_original                                              as call_original,
    call_final                                                 as call_final,
    challenge_team_id                                          as challenge_team_id,
    opponent_id                                                as opponent_id,
    home_team_id                                               as home_team_id,
    away_team_id                                               as away_team_id,
    challenger_id                                              as challenger_id,
    challenger_role                                            as challenger_role,
    challenger_id is not null and challenger_role <> 'unknown' as challenger_identified,
    batter_id                                                  as batter_id,
    pitcher_id                                                 as pitcher_id,
    catcher_id                                                 as catcher_id,
    inning                                                     as inning,
    is_top_inning                                              as is_top_inning,
    play_id                                                    as play_id,
    challenge_ord                                              as challenge_ord,
    tokens_start                                               as tokens_start,
    'feed_game_remaining_plus_used_failed'                     as tokens_start_source,
    failed_before                                              as failed_before,
    tokens_start - failed_before                               as tokens_remaining_before
from ledger
