{{ config(materialized='table') }}

-- fct_wp_state -- SOP step W2.18, the marts layer.
--
-- Win probability by game state, grain (half_inning, score_diff, outs,
-- base_state, count), which is the SOP section 2.6 contract and the shape SOP
-- W5.2 names for the count-composed cube: 26 x 21 x 3 x 8 x 12 = 157,248 cells.
-- wp is the batting team's win probability in that state; n is the number of
-- pitches observed in it.
--
-- WHERE wp COMES FROM. Statcast carries bat_win_exp on every pitch, on the same
-- measurement system as the rest of the pitch record, so the empirical cube is
-- the mean of that column over the pitches in the cell. This is the warehouse
-- table. W5.2 to W5.6 build the smoothed count-composed surface and the
-- gradient-boosted comparator from the same population; they read this table
-- and do not replace it.
--
-- THE FIVE AXES. half_inning is 0 for the top of the first and counts up by
-- one each half inning, capped at 25 so extra innings fold into the last cell,
-- giving 26 values. score_diff is the batting team's lead, clipped to the range
-- -10 to +10, giving 21. outs is 0 to 2. base_state is the three-character
-- string int_re288_state uses, first base then second then third, 1 for
-- occupied and - for empty. count is balls and strikes joined by a hyphen,
-- giving 12.
--
-- POPULATION. MLB regular-season pitches in the open analysis set, the same
-- population fct_re288 uses, written out as two constant columns for the same
-- reason: a state table has no game and no day of its own. No official_date
-- column, because the table pools every day by design.

with pitches as (

    select
        least(greatest((inning - 1) * 2
              + case when inning_topbot = 'Bot' then 1 else 0 end, 0), 25) as half_inning,
        least(greatest(bat_score_diff, -10), 10)               as score_diff,
        outs_when_up                                           as outs,
        case when on_1b is not null then '1' else '-' end
            || case when on_2b is not null then '1' else '-' end
            || case when on_3b is not null then '1' else '-' end as base_state,
        cast(balls as varchar) || '-' || cast(strikes as varchar) as "count",
        bat_win_exp                                            as bat_win_exp
    from {{ ref('fct_pitch') }}
    where analysis_set = 'open'
      and level = 'mlb'
      and game_type = 'R'
      and balls between 0 and 3
      and strikes between 0 and 2
      and outs_when_up between 0 and 2
      and inning is not null
      and bat_score_diff is not null
      and bat_win_exp is not null

)

select
    cast(half_inning as varchar) || ':' || cast(score_diff as varchar)
        || ':' || cast(outs as varchar) || ':' || base_state
        || ':' || "count"                                      as wp_state_key,
    half_inning                                                as half_inning,
    score_diff                                                 as score_diff,
    outs                                                       as outs,
    base_state                                                 as base_state,
    "count"                                                    as "count",
    avg(bat_win_exp)                                           as wp,
    count(*)                                                   as n,
    'mlb'                                                      as level,
    'open'                                                     as analysis_set
from pitches
group by half_inning, score_diff, outs, base_state, "count"
