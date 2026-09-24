{{ config(materialized='view') }}

-- int_called_pitch -- SOP step W2.17, the intermediate layer.
--
-- int_pitch filtered to the called-pitch population the whole project is built
-- on: description in ('called_strike', 'ball', 'blocked_ball'). On this machine
-- that is 1,610,220 of 3,108,070 pitches.
--
-- WHAT THIS MODEL ADDS. cs, the outcome every Chapter 1 fit models, 1 on a
-- called strike and 0 on a ball. d_signed_in, the signed distance from the
-- zone edge in inches, which W2.14 already computed as edge_dist_in under the
-- rule SOP section 2.5 settles: any part of the ball, 17-inch plate,
-- r = 1.45 in, Euclidean at the corners, on the mid-plate plane. It is negative
-- inside the zone, so a called strike at a negative d_signed_in is a correct
-- call and one at a positive d_signed_in is not. edge_dist_r_in carries the
-- radius beside it, because the distance means nothing without it. And the
-- home-plate umpire, from stg_game_official, which is the only umpire source:
-- DT-03 asserts on every build that the Statcast CSV's own umpire column is
-- empty.
--
-- WHAT THIS MODEL DOES NOT ADD. nearest_edge, z_norm, count_class and
-- pitch_group are fct_called_pitch columns in SOP section 2.6 whose definitions
-- the SOP fixes in W3.7, where the Chapter 1 analysis table derives them. They
-- are left to that step rather than guessed here, because a bin boundary
-- invented in the warehouse would be a pre-registered quantity nobody agreed.

with pitches as (

    select *
    from {{ ref('int_pitch') }}
    where description in ('called_strike', 'ball', 'blocked_ball')

),

-- One home-plate umpire per game. The officials block names four umpires and
-- the home-plate row is the one Chapter 1 groups on.
umpires as (

    select
        game_pk,
        official_id                                            as umpire_hp_id,
        official_name                                          as umpire_hp_name
    from {{ ref('stg_game_official') }}
    where official_type = 'Home Plate'
    qualify row_number() over (partition by game_pk order by official_id) = 1

)

select
    pitches.*,
    case when pitches.description = 'called_strike' then 1 else 0 end as cs,
    pitches.edge_dist_in                                       as d_signed_in,
    umpires.umpire_hp_id                                       as umpire_hp_id,
    umpires.umpire_hp_name                                     as umpire_hp_name,
    case
        when umpires.umpire_hp_id is null then null
        else cast(umpires.umpire_hp_id as varchar)
            || ':' || cast(pitches.season as varchar)
    end                                                        as umpire_season
from pitches
left join umpires
    on pitches.game_pk = umpires.game_pk
