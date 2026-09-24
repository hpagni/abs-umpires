{{ config(materialized='table') }}

-- GD-04-EXEMPT: construction -- this model's own output is a fact table, built from
-- the pitch fact one layer down. Restricting the BUILD to the open set would change
-- what the warehouse holds rather than what an analysis sees, and the seal is kept
-- here by `assert_seal_not_crossed` on official_date, not by a WHERE clause.

-- fct_called_pitch -- SOP step W2.18, the marts layer. W3 called this
-- mart.called_pitches; SOP section 2.6 renames it.
--
-- fct_pitch filtered to the called-pitch population the whole project is built
-- on, description in ('called_strike', 'ball', 'blocked_ball'), plus the
-- columns section 2.6 adds. Same grain, same key.
--
-- d_signed_in is edge_dist_in, the any-part-of-ball signed distance from the
-- zone edge in inches that W2.14 computed under the rule SOP section 2.5
-- settles: 17-inch plate, r = 1.45 in, Euclidean at the corners, on the
-- mid-plate plane. It is negative inside the zone, so a called strike at a
-- negative d_signed_in is a correct call. SOP section 2.5 records that this
-- reproduces Savant's own edge_dist_calc to 0.000000 in on 1,276 of 1,276 rows.
--
-- nearest_edge and z_norm are the two SOP section 2.5 functions of the same
-- names, transcribed. nearest_edge takes the largest of the three signed
-- distances to the side, top and bottom edges and names it, with the R
-- function's first-match tie rule written out as the case order. The three are
-- measured in inches against the published zone, which is the zone
-- edge_dist_in was measured against, so the name and the distance agree.
-- z_norm is the plate height in units of batter height, z_ft * 12 / h_in.
--
-- count_class and pitch_group are the two columns of the section 2.6 list that
-- this step does not write. The SOP fixes their bin boundaries in W3.7, where
-- the Chapter 1 analysis table derives them, and a bin boundary invented in the
-- warehouse would be a pre-registered quantity nobody agreed. Reported in the
-- W2.18 return.

with called as (

    select *
    from {{ ref('fct_pitch') }}
    where description in ('called_strike', 'ball', 'blocked_ball')

)

select
    called.*,
    case when called.description = 'called_strike' then 1 else 0 end as cs,
    called.edge_dist_in                                        as d_signed_in,
    case
        when called.plate_x_mid is null
             or called.plate_z_mid is null
             or called.sz_top is null
             or called.sz_bot is null then null
        when abs(called.plate_x_mid) * 12 - 8.5
             >= greatest(called.plate_z_mid * 12 - called.sz_top * 12,
                         called.sz_bot * 12 - called.plate_z_mid * 12)
            then 'side'
        when called.plate_z_mid * 12 - called.sz_top * 12
             >= called.sz_bot * 12 - called.plate_z_mid * 12
            then 'top'
        else 'bot'
    end                                                        as nearest_edge,
    case
        when called.batter_height_in is null or called.batter_height_in = 0 then null
        else called.plate_z_mid * 12 / called.batter_height_in
    end                                                        as z_norm,
    case
        when called.umpire_hp_id is null then null
        else cast(called.umpire_hp_id as varchar)
            || ':' || cast(called.season as varchar)
    end                                                        as umpire_season
from called
