{{ config(materialized='view', tags=['smoke']) }}

-- stg_abs_challenges -- SOP step W2.17, the staging layer. W1.11 wrote the
-- skeleton; this is the same model over the feed_challenge table W2.16 built.
--
-- One row per ABS challenge, grain (game_pk, at_bat_number, pitch_slot,
-- review_level). Renames and casts only. On this machine the source holds
-- 12,300 rows, MLB 2026 (10,168) and AAA 2024 (2,132), and that key is unique
-- on every one of them.
--
-- review_level is the one value mapping this model does. W2.16 stores the JSON
-- location the record was read from, and the warehouse contract names the three
-- levels:
--
--   playEvents[].reviewDetails          -> event        pitch level
--   allPlays[].reviewDetails            -> play         at-bat-ending pitch
--   reviewDetails.additionalReviews[]   -> additional   a second review
--
-- A location outside those three produces a null review_level and a null
-- challenge_uid, which the not_null test on challenge_uid fails loudly rather
-- than dropping the row.
--
-- THE PITCH KEY. The feed counts pitch slots and Statcast numbers pitches, so
-- this model carries slot_uid, on the feed key, and not pitch_uid. The bridge
-- is stg_pitch_joined and the join is int_challenge_resolved's. The ci branch
-- keeps pitch_uid because the synthetic seed is one flat table with no slots in
-- it, and W1.11's smoke build reads that branch.
--
-- The lake read goes through lake_scan, so a clone with no data/ directory
-- builds this model empty instead of failing the run on a missing file.
--
-- call_original is the umpire's call before the challenge and call_final is the
-- call that stood, both in the feed vocabulary, 'ball' or 'strike'.

{% if target.name == 'ci' %}

with source as (
    select *
    from {{ ref('seed_synthetic_pitches') }}
    where challenged
)

select
    cast(game_pk as varchar)
        || ':' || cast(at_bat_number as varchar)
        || ':' || cast(pitch_number as varchar)
        || ':' || cast(review_level as varchar)                as challenge_uid,
    cast(game_pk as varchar)
        || ':' || cast(at_bat_number as varchar)
        || ':' || cast(pitch_number as varchar)                as pitch_uid,
    cast(game_pk as bigint)                                    as game_pk,
    cast(at_bat_number as integer)                             as at_bat_number,
    cast(pitch_number as integer)                              as pitch_number,
    cast(official_date as date)                                as official_date,
    cast(level as varchar)                                     as level,
    cast(review_level as varchar)                              as review_level,
    cast(is_overturned as boolean)                             as is_overturned,
    cast(challenge_team_id as bigint)                          as challenge_team_id,
    cast(challenger_id as bigint)                              as challenger_id,
    cast(challenger_role as varchar)                           as challenger_role,
    cast(tokens_remaining_before as integer)                   as tokens_remaining_before,
    cast(call_original as varchar)                             as call_original,
    cast(call_final as varchar)                                as call_final
from source

{% else %}

with source as ( {{ lake_scan('feed_challenge', [
    'game_pk', 'at_bat_index', 'at_bat_number', 'pitch_slot', 'feed_pitch_number',
    'play_index', 'play_id', 'review_type', 'review_location', 'review_locations',
    'resolved_by', 'is_overturned', 'in_progress', 'call_code_stored', 'call_final',
    'call_original', 'challenger_id', 'challenger_role', 'challenge_team_id',
    'standing_side', 'standing_team_id', 'batter_id', 'pitcher_id', 'catcher_id',
    'is_top_inning', 'inning', 'result_event_type', 'level', 'season', 'official_date']) }} ),

levelled as (
    select
        source.*,
        case review_location
            when 'playEvents[].reviewDetails'        then 'event'
            when 'allPlays[].reviewDetails'          then 'play'
            when 'reviewDetails.additionalReviews[]' then 'additional'
        end                                                    as review_level
    from source
)

select
    cast(game_pk as varchar)
        || ':' || cast(at_bat_number as varchar)
        || ':' || cast(pitch_slot as varchar)
        || ':' || review_level                                 as challenge_uid,
    cast(game_pk as varchar)
        || ':' || cast(at_bat_number as varchar)
        || ':' || cast(pitch_slot as varchar)                  as slot_uid,
    cast(game_pk as bigint)                                    as game_pk,
    cast(at_bat_index as integer)                              as at_bat_index,
    cast(at_bat_number as integer)                             as at_bat_number,
    cast(pitch_slot as integer)                                as pitch_slot,
    cast(feed_pitch_number as integer)                         as feed_pitch_number,
    cast(play_index as integer)                                as play_index,
    cast(play_id as varchar)                                   as play_id,
    cast(level as varchar)                                     as level,
    cast(season as integer)                                    as season,
    cast(official_date as date)                                as official_date,
    cast(review_level as varchar)                              as review_level,
    cast(review_type as varchar)                               as review_type,
    cast(review_location as varchar)                           as review_location,
    cast(review_locations as varchar)                          as review_locations,
    cast(resolved_by as varchar)                               as resolved_by,
    cast(is_overturned as boolean)                             as is_overturned,
    cast(in_progress as boolean)                               as in_progress,
    cast(call_code_stored as varchar)                          as call_code_stored,
    cast(call_original as varchar)                             as call_original,
    cast(call_final as varchar)                                as call_final,
    cast(challenge_team_id as bigint)                          as challenge_team_id,
    cast(challenger_id as bigint)                              as challenger_id,
    cast(challenger_role as varchar)                           as challenger_role,
    cast(standing_side as varchar)                             as standing_side,
    cast(standing_team_id as bigint)                           as standing_team_id,
    cast(batter_id as bigint)                                  as batter_id,
    cast(pitcher_id as bigint)                                 as pitcher_id,
    cast(catcher_id as bigint)                                 as catcher_id,
    cast(is_top_inning as boolean)                             as is_top_inning,
    cast(inning as integer)                                    as inning,
    cast(result_event_type as varchar)                         as result_event_type
from levelled

{% endif %}
