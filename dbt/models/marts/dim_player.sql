{{ config(materialized='table') }}

-- dim_player -- SOP step W2.18, the marts layer.
--
-- One row per player, grain player_id, from the feed rosters. SOP section 2.6
-- names full_name, primary_position, key_mlbam, key_retro and key_bbref.
--
-- WHAT IS ON DISK AND WHAT IS NOT. player_id and primary_position come from
-- interim/feed_player, which stg_feed_player reads. key_mlbam is that same id
-- under the Chadwick register's name for it, so it is written here rather than
-- left for later. full_name, key_retro and key_bbref come from the Chadwick
-- register, which no step has pulled onto this machine, so the three columns
-- are cast null with their contract types. A null is visible in a join; a
-- guessed name is not. The step that lands the register fills them in place and
-- the column list does not change.
--
-- primary_position is the last one the rosters show for the player, taken by
-- the most recent game date, because a player who changed position mid-career
-- would otherwise get whichever row the scan happened to reach first.

with roster as (

    select
        player_id,
        level,
        season,
        official_date,
        primary_position
    from {{ ref('stg_feed_player') }}
    where player_id is not null
      and official_date <= date '{{ var("last_open_date") }}'

),

latest as (

    select *
    from roster
    qualify row_number() over (
        partition by player_id
        order by official_date desc, season desc
    ) = 1

)

select
    latest.player_id                                           as player_id,
    cast(null as varchar)                                      as full_name,
    latest.primary_position                                    as primary_position,
    latest.player_id                                           as key_mlbam,
    cast(null as varchar)                                      as key_retro,
    cast(null as varchar)                                      as key_bbref,
    latest.level                                               as level,
    latest.season                                              as season,
    latest.official_date                                       as official_date
from latest
