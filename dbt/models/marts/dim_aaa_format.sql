{{ config(materialized='table') }}

-- dim_aaa_format -- SOP step W2.18, the marts layer. W3 called this
-- mart.game_format_aaa; SOP section 2.6 renames it and fixes its columns:
-- official_date, weekday, has_abs_challenges, n_mj, agree_rate, format_class.
--
-- One row per AAA game. It exists so the AAA arm can be audited game by game
-- rather than argued from a weekday. SOP W2.17 is explicit that the full-ABS
-- and challenge formats are derived from has_abs_challenges and never from the
-- weekday, and SOP risk R-10 records why: the Tuesday-and-Friday alternation is
-- real in early 2024 and gone by August. weekday is carried here as evidence,
-- not as a source: format_class reads has_abs_challenges alone, and a game
-- whose feed record is not on disk is classed unknown rather than guessed.
--
-- n_mj counts the machine-judgment reviews in the game at the two levels DT-07
-- reconciles, the pitch-level event record and the play-level record, and
-- leaves additionalReviews out of the count so the two sides of that identity
-- are the same quantity.
--
-- agree_rate is the share of those reviews that were not overturned, which is
-- the rate at which the umpire's call and the machine agreed. It is null when
-- the game has no review, because a rate over zero reviews is not zero.

with games as (

    select
        game_pk,
        level,
        season,
        official_date,
        game_type,
        has_abs_challenges,
        regime,
        regime_source,
        analysis_set
    from {{ ref('int_regime') }}
    where level = 'aaa'
      and official_date <= date '{{ var("last_open_date") }}'

),

reviews as (

    select
        game_pk,
        count(*)                                               as n_mj,
        count(*) filter (where is_overturned)                  as n_overturned
    from {{ ref('int_challenge_resolved') }}
    where level = 'aaa'
      and review_level in ('event', 'play')
    group by 1

)

select
    games.game_pk                                              as game_pk,
    games.official_date                                        as official_date,
    dayname(games.official_date)                               as weekday,
    games.has_abs_challenges                                   as has_abs_challenges,
    coalesce(reviews.n_mj, 0)                                  as n_mj,
    case
        when coalesce(reviews.n_mj, 0) = 0 then null
        else 1.0 - (reviews.n_overturned * 1.0 / reviews.n_mj)
    end                                                        as agree_rate,
    case
        when games.has_abs_challenges is null then 'unknown'
        when games.has_abs_challenges then 'challenge'
        else 'full_abs'
    end                                                        as format_class,
    games.regime                                               as regime,
    games.regime_source                                        as regime_source,
    games.level                                                as level,
    games.season                                               as season,
    games.game_type                                            as game_type,
    games.analysis_set                                         as analysis_set
from games
left join reviews
    on games.game_pk = reviews.game_pk
