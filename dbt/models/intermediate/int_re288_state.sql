{{ config(materialized='view') }}

-- int_re288_state -- SOP step W2.17, the intermediate layer.
--
-- Run expectancy by base-out-count state, grain (outs, base_state, balls,
-- strikes): 3 out states x 8 base states x 12 counts = 288 cells, which is what
-- the 288 in the name counts. fct_re288 in SOP section 2.6 takes this grain and
-- these two measures, re and n.
--
-- re is the mean number of runs the batting team scores from that state to the
-- end of the half inning. The runs are taken from the Statcast score columns:
-- the batting team's score after the last play of the half inning, minus its
-- score at the pitch. No Retrosheet event file is read. SOP risk R-35 says the
-- RE288 table comes from Statcast regardless, and DT-27 cross-checks it against
-- delta_run_exp to 0.01 runs per cell.
--
-- base_state is a three-character string, first base then second then third,
-- with 1 for occupied and - for empty, so '1-3' is first and third.
--
-- POPULATION. MLB regular-season pitches in the open analysis set, every season
-- on disk, which is 2022 to 2026 here. AAA is left out because its run
-- environment is not the one Chapter 1 prices a call in. A half inning that
-- ends without a pitch, on a pickoff or a balk, contributes no row, and a run
-- that scores on such a play is still inside the end-of-inning score, so it is
-- counted where it happened.

with pitches as (

    select
        game_pk,
        inning,
        inning_topbot,
        outs_when_up,
        balls,
        strikes,
        on_1b,
        on_2b,
        on_3b,
        bat_score,
        post_bat_score
    from {{ ref('int_pitch') }}
    where analysis_set = 'open'
      and level = 'mlb'
      and game_type = 'R'
      and balls between 0 and 3
      and strikes between 0 and 2
      and outs_when_up between 0 and 2

),

half_innings as (

    select
        game_pk,
        inning,
        inning_topbot,
        max(post_bat_score)                                    as end_bat_score
    from pitches
    group by 1, 2, 3

),

states as (

    select
        pitches.outs_when_up                                   as outs,
        case when pitches.on_1b is not null then '1' else '-' end
            || case when pitches.on_2b is not null then '2' else '-' end
            || case when pitches.on_3b is not null then '3' else '-' end
                                                               as base_state,
        pitches.balls                                          as balls,
        pitches.strikes                                        as strikes,
        half_innings.end_bat_score - pitches.bat_score         as runs_rest_of_inning
    from pitches
    join half_innings
        on pitches.game_pk = half_innings.game_pk
       and pitches.inning = half_innings.inning
       and pitches.inning_topbot = half_innings.inning_topbot

)

select
    outs                                                       as outs,
    base_state                                                 as base_state,
    balls                                                      as balls,
    strikes                                                    as strikes,
    avg(runs_rest_of_inning)                                   as re,
    count(*)                                                   as n
from states
group by 1, 2, 3, 4
