{{ config(materialized='view') }}

-- stg_feed_game -- SOP step W2.17, the staging layer.
--
-- One row per game, from the GUMBO feed's gameData block. Renames and casts
-- only (SOP section 2.6): no filter, no join, no derived measure.
--
-- has_abs_challenges is the fact int_regime reads to tell an AAA full-ABS game
-- from an AAA challenge game. SOP W2.17: never from the weekday.
--
-- The three token columns per side are the end-of-game block. The starting
-- allotment DT-08 asserts is the per-game maximum of `remaining` across the
-- play-by-play, which is W2.16's estimator and is not in this table.

with source as ( {{ lake_scan('feed_game', [
    'game_pk', 'has_abs_challenges',
    'away_used_successful', 'away_used_failed', 'away_remaining',
    'home_used_successful', 'home_used_failed', 'home_remaining',
    'review_has_challenges', 'review_away_used', 'review_away_remaining',
    'review_home_used', 'review_home_remaining',
    'attendance', 'game_duration_minutes', 'first_pitch_utc', 'venue_id',
    'level', 'season', 'official_date']) }} )

select
    cast(game_pk as bigint)                                    as game_pk,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(official_date as date)                                as official_date,
    cast(has_abs_challenges as boolean)                        as has_abs_challenges,
    cast(away_used_successful as integer)                      as away_used_successful,
    cast(away_used_failed as integer)                          as away_used_failed,
    cast(away_remaining as integer)                            as away_remaining,
    cast(home_used_successful as integer)                      as home_used_successful,
    cast(home_used_failed as integer)                          as home_used_failed,
    cast(home_remaining as integer)                            as home_remaining,
    cast(review_has_challenges as boolean)                     as review_has_challenges,
    cast(review_away_used as integer)                          as review_away_used,
    cast(review_away_remaining as integer)                     as review_away_remaining,
    cast(review_home_used as integer)                          as review_home_used,
    cast(review_home_remaining as integer)                     as review_home_remaining,
    cast(attendance as integer)                                as attendance,
    cast(game_duration_minutes as integer)                     as game_duration_minutes,
    cast(first_pitch_utc as timestamptz)                       as first_pitch_utc,
    cast(venue_id as integer)                                  as venue_id
from source
