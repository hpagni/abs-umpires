{{ config(materialized='table') }}

-- dim_game -- SOP step W2.18, the marts layer.
--
-- One row per scheduled game, grain game_pk, carrying the dim_game column list
-- of SOP section 2.6 plus the five columns every mart carries: regime, level,
-- season, official_date, analysis_set.
--
-- TWO NAMES FOR ONE VALUE. Section 2.6 names the regime column abs_regime in
-- the dim_game row of the contract table and regime in the sentence that says
-- every mart carries it. Both are written here and they hold the same value, so
-- either name reads the same label and neither statement is broken.
--
-- THE BOUNDARY. The where clause keeps games on or before the last open day,
-- the same filter int_pitch applies, written against the last_open_date
-- variable because GD-04 rule 5 fails on a held-out day written under dbt/.
-- Without it a mart table would carry sealed rows and the dev target's
-- on-run-start hook would fail the next run.
--
-- SCORES. No schedule or feed source on this machine carries a final score, so
-- the two score columns are taken from the Statcast pitch rows: scores are
-- monotone within a game, so the maximum over the game is the final value, and
-- post_bat_score is folded in on the batting side of each half inning so a run
-- scored on the last pitch is counted. A game with no tracked pitch on disk
-- carries null scores and a null home_win rather than a zero, because a zero
-- would be read as a shutout.

with games as (

    select *
    from {{ ref('int_regime') }}
    where official_date <= date '{{ var("last_open_date") }}'

),

schedule as (

    select
        game_pk,
        game_date_utc
    from {{ ref('stg_schedule_game') }}

),

scores as (

    select
        game_pk,
        max(case when inning_topbot = 'Bot'
                 then greatest(home_score, post_bat_score)
                 else home_score end)                          as home_score,
        max(case when inning_topbot = 'Top'
                 then greatest(away_score, post_bat_score)
                 else away_score end)                          as away_score
    from {{ ref('int_pitch') }}
    group by 1

)

select
    games.game_pk                                              as game_pk,
    games.season                                               as season,
    games.game_type                                            as game_type,
    games.official_date                                        as official_date,
    schedule.game_date_utc                                     as game_date_utc,
    games.level                                                as level,
    games.regime                                               as abs_regime,
    games.regime                                               as regime,
    games.regime_source                                        as regime_source,
    games.has_abs_challenges                                   as has_abs_challenges,
    games.doubleheader                                         as double_header,
    games.game_number                                          as game_number,
    games.venue_id                                             as venue_id,
    games.home_team_id                                         as home_team_id,
    games.away_team_id                                         as away_team_id,
    scores.home_score                                          as home_score,
    scores.away_score                                          as away_score,
    case
        when scores.home_score is null or scores.away_score is null then null
        else scores.home_score > scores.away_score
    end                                                        as home_win,
    games.status_abstract                                      as status_abstract,
    games.analysis_set                                         as analysis_set
from games
left join schedule
    on games.game_pk = schedule.game_pk
left join scores
    on games.game_pk = scores.game_pk
