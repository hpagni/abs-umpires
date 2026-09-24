{{ config(materialized='table') }}

-- fct_team_game_tokens -- SOP step W2.18, the marts layer.
--
-- One row per team per game, grain (game_pk, team_id), with the challenge
-- tokens that team used and had left: used_successful, used_failed, remaining,
-- tokens_start, the SOP section 2.6 contract.
--
-- The three used and remaining counts come from the end-of-game absChallenges
-- block, which the feed writes once per team. tokens_start does not: DT-08 is
-- explicit that the starting allotment is the per-game maximum of remaining
-- observed across the play-by-play, not the end-of-game block, because the
-- block can disagree with the play-by-play and a game where they disagree is an
-- audit row rather than a silent drop. int_challenge_resolved already carries
-- that per-challenge maximum as tokens_start, so this model takes it where a
-- team challenged at all, and falls back to the block's own arithmetic,
-- used_successful + used_failed + remaining, for a team that never challenged
-- and therefore has no play-by-play evidence. tokens_start_source records which
-- of the two produced the number, so the audit does not have to guess.

with blocks as (

    select
        game_pk,
        level,
        season,
        official_date,
        'home'                                                 as side,
        home_used_successful                                   as used_successful,
        home_used_failed                                       as used_failed,
        home_remaining                                         as remaining
    from {{ ref('stg_feed_game') }}
    where official_date <= date '{{ var("last_open_date") }}'

    union all

    select
        game_pk,
        level,
        season,
        official_date,
        'away'                                                 as side,
        away_used_successful                                   as used_successful,
        away_used_failed                                       as used_failed,
        away_remaining                                         as remaining
    from {{ ref('stg_feed_game') }}
    where official_date <= date '{{ var("last_open_date") }}'

),

games as (

    select
        game_pk,
        home_team_id,
        away_team_id,
        regime,
        analysis_set
    from {{ ref('int_regime') }}

),

observed as (

    select
        game_pk,
        challenge_team_id                                      as team_id,
        max(tokens_start)                                      as tokens_start_pbp
    from {{ ref('int_challenge_resolved') }}
    where challenge_team_id is not null
    group by 1, 2

),

joined as (

    select
        blocks.game_pk                                         as game_pk,
        case when blocks.side = 'home'
             then games.home_team_id else games.away_team_id end as team_id,
        blocks.side                                            as side,
        blocks.used_successful                                 as used_successful,
        blocks.used_failed                                     as used_failed,
        blocks.remaining                                       as remaining,
        blocks.level                                           as level,
        blocks.season                                          as season,
        blocks.official_date                                   as official_date,
        games.regime                                           as regime,
        games.analysis_set                                     as analysis_set
    from blocks
    left join games
        on blocks.game_pk = games.game_pk

)

select
    cast(joined.game_pk as varchar)
        || ':' || cast(joined.team_id as varchar)                  as team_game_key,
    joined.game_pk                                             as game_pk,
    joined.team_id                                             as team_id,
    joined.side                                                as side,
    joined.used_successful                                     as used_successful,
    joined.used_failed                                         as used_failed,
    joined.remaining                                           as remaining,
    coalesce(observed.tokens_start_pbp,
             joined.used_successful + joined.used_failed + joined.remaining)
                                                               as tokens_start,
    case
        when observed.tokens_start_pbp is not null then 'play_by_play_max'
        else 'end_of_game_block'
    end                                                        as tokens_start_source,
    joined.level                                               as level,
    joined.season                                              as season,
    joined.official_date                                       as official_date,
    joined.regime                                              as regime,
    joined.analysis_set                                        as analysis_set
from joined
left join observed
    on joined.game_pk = observed.game_pk
   and joined.team_id = observed.team_id
