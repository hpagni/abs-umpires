{{ config(materialized='view') }}

-- int_regime -- SOP step W2.17, the intermediate layer.
--
-- One row per scheduled game, carrying the regime label every downstream model
-- filters and groups on, and the analysis-set label that makes a filter mistake
-- visible rather than silent.
--
-- THE REGIME MAP, SOP W2.17 verbatim: pre_buffer 2022-2024, buffer_2025,
-- abs_2026, plus aaa_full_abs and aaa_challenge derived from
-- has_abs_challenges, NEVER from the weekday. AAA ran full ABS in some games
-- and the challenge system in others, and the split by weekday is a rule of
-- thumb that the schedule breaks; the feed states the format per game and that
-- is the only source this model reads.
--
-- A game whose regime cannot be named carries a null regime and a
-- regime_source that says why. Two cases produce one today: an AAA game with no
-- feed_game row, because interim/feed_game holds MLB 2026 only on this machine,
-- and an MLB season outside 2022-2026, because the SOP maps no label onto it.
-- A null is visible in a group-by; a wrong label is not.
--
-- THE ANALYSIS SET is the frozen predicate of SOP section 2.4, held in
-- quality/sql/analysis_set.sql. Its middle branch names the first held-out day,
-- which GD-04 rule 5 forbids anywhere under dbt/. The two branches written here
-- are the two that can be reached: the boundary rows are dropped by
-- official_date <= last_open_date in int_pitch, which selects exactly the rows
-- the frozen predicate leaves open, and the 2026 postseason game types cannot
-- reach this model while that filter stands. The test
-- int_regime_carries_no_2026_postseason_game asserts the second half of that
-- sentence on every build, so the unreachable branch stays unreachable.

with games as (

    select * from {{ ref('stg_schedule_game') }}

),

formats as (

    select
        game_pk,
        has_abs_challenges
    from {{ ref('stg_feed_game') }}

)

select
    games.game_pk                                              as game_pk,
    games.level                                                as level,
    games.season                                               as season,
    games.official_date                                        as official_date,
    games.game_type                                            as game_type,
    games.status_abstract                                      as status_abstract,
    games.home_team_id                                         as home_team_id,
    games.away_team_id                                         as away_team_id,
    games.venue_id                                             as venue_id,
    games.doubleheader                                         as doubleheader,
    games.game_number                                          as game_number,
    formats.has_abs_challenges                                 as has_abs_challenges,
    case
        when games.level = 'aaa' and formats.has_abs_challenges then 'aaa_challenge'
        when games.level = 'aaa' and not formats.has_abs_challenges then 'aaa_full_abs'
        when games.level = 'aaa' then null
        when games.season between 2022 and 2024 then 'pre_buffer'
        when games.season = 2025 then 'buffer_2025'
        when games.season = 2026 then 'abs_2026'
    end                                                        as regime,
    case
        when games.level = 'aaa' and formats.has_abs_challenges is not null
            then 'has_abs_challenges'
        when games.level = 'aaa' then 'unknown_no_feed_game_row'
        when games.season between 2022 and 2026 then 'season'
        else 'unknown_season_outside_the_map'
    end                                                        as regime_source,
    case
        when games.game_type in ('S', 'A', 'E') then 'excluded'
        else 'open'
    end                                                        as analysis_set
from games
left join formats
    on games.game_pk = formats.game_pk
