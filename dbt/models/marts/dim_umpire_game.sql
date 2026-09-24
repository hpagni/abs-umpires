{{ config(materialized='table') }}

-- dim_umpire_game -- SOP step W2.18, the marts layer.
--
-- One row per game, grain game_pk, naming the home-plate umpire. SOP section
-- 2.6 calls the two columns hp_umpire_id and hp_umpire_name. This is the only
-- umpire source in the warehouse: DT-03 asserts on every build that the
-- Statcast CSV's own umpire column is empty.
--
-- The officials block names four umpires per game and the home-plate row is the
-- one Chapter 1 groups on. DT-14 asserts exactly one Home Plate official per
-- Final game, so the row_number is a guard against a duplicated feed record
-- rather than a choice between two candidates.
--
-- The five carried columns come from int_regime. A game with officials but no
-- schedule row would carry a null regime and a null analysis_set, which is
-- visible in a group-by; official_date is taken from the officials row instead,
-- which is never null, because a null there would make the dev target's seal
-- guard count the row as sealed.

with officials as (

    select
        game_pk,
        level,
        season,
        official_date,
        official_id                                            as hp_umpire_id,
        official_name                                          as hp_umpire_name
    from {{ ref('stg_game_official') }}
    where official_type = 'Home Plate'
      and official_date <= date '{{ var("last_open_date") }}'
    qualify row_number() over (partition by game_pk order by official_id) = 1

),

games as (

    select
        game_pk,
        regime,
        analysis_set
    from {{ ref('int_regime') }}

)

select
    officials.game_pk                                          as game_pk,
    officials.hp_umpire_id                                     as hp_umpire_id,
    officials.hp_umpire_name                                   as hp_umpire_name,
    officials.level                                            as level,
    officials.season                                           as season,
    officials.official_date                                    as official_date,
    games.regime                                               as regime,
    games.analysis_set                                         as analysis_set
from officials
left join games
    on officials.game_pk = games.game_pk
