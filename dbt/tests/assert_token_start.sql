-- dbt/tests/assert_token_start.sql -- SOP step W2.19, assertion DT-08.
--
-- GD-04-EXEMPT: construction -- this file's output is an assertion about a fact
-- table: the assertion is about the token ledger the challenge fact
-- is built on, per team-game. It must see every row it validates; an open-set filter
-- would let a broken allotment hide behind the seal.
--
-- DT-08 in SOP section 6.3: the starting allotment per team-game is the
-- per-game maximum of `remaining` observed across the play-by-play, not the
-- end-of-game block. MLB 2026 reads 2 for 100%. For AAA the assertion is the
-- per-season modal allotment with every exception enumerated in
-- out/tables/aaa_allotment_audit.csv, and a game where the play-by-play maximum
-- and the end-of-game block disagree is an audit row, not a silent drop.
--
-- So this test is not "every team-game reads the modal allotment". It is the
-- set of conditions under which a team-game is a silent drop rather than an
-- audit row:
--
--   below_modal_allotment   a team-game that starts with fewer tokens than the
--                           season's mode. Above the mode is an audit row, the
--                           36 MLB 2026 extra-innings team-games among them.
--                           Below the mode is a lost token and it is a failure.
--   start_below_used_failed a team-game that spent more tokens on failed
--                           reviews than it ever had. A successful review is
--                           retained under the challenge system, so used
--                           totals above the allotment are ordinary and only
--                           the failed count is bounded by it.
--   missing_start_with_evidence
--                           no allotment, although the end-of-game block
--                           carries at least one of used_successful,
--                           used_failed and remaining. A team-game with no
--                           evidence at all carries a null allotment by
--                           design and is published in the audit table; a
--                           team-game with evidence and no allotment is a
--                           reconstruction that dropped a number it had.
--   unknown_start_source    tokens_start_source outside the two names
--                           fct_team_game_tokens defines.
--
-- The mode is computed per level and season from the table itself rather than
-- written down, so the AAA clause needs no second copy of a rule that changed
-- format mid-season.

with modal as (

    select
        level                                                  as level,
        season                                                 as season,
        mode(tokens_start)                                     as modal_allotment
    from {{ ref('fct_team_game_tokens') }}
    where tokens_start is not null
    group by 1, 2

),

judged as (

    select
        tokens.team_game_key                                   as team_game_key,
        tokens.game_pk                                         as game_pk,
        tokens.team_id                                         as team_id,
        tokens.level                                           as level,
        tokens.season                                          as season,
        tokens.tokens_start                                    as tokens_start,
        tokens.tokens_start_source                             as tokens_start_source,
        tokens.used_successful                                 as used_successful,
        tokens.used_failed                                     as used_failed,
        tokens.remaining                                       as remaining,
        modal.modal_allotment                                  as modal_allotment
    from {{ ref('fct_team_game_tokens') }} as tokens
    left join modal
        on tokens.level = modal.level
       and tokens.season = modal.season

)

select
    team_game_key                                              as team_game_key,
    game_pk                                                    as game_pk,
    team_id                                                    as team_id,
    level                                                      as level,
    season                                                     as season,
    tokens_start                                               as tokens_start,
    modal_allotment                                            as modal_allotment,
    tokens_start_source                                        as tokens_start_source,
    used_successful                                            as used_successful,
    used_failed                                                as used_failed,
    remaining                                                  as remaining,
    case
        when tokens_start_source not in ('play_by_play_max', 'end_of_game_block')
            then 'unknown_start_source'
        when tokens_start is null
            then 'missing_start_with_evidence'
        when tokens_start < used_failed
            then 'start_below_used_failed'
        else 'below_modal_allotment'
    end                                                        as failure
from judged
where tokens_start_source not in ('play_by_play_max', 'end_of_game_block')
   or (tokens_start is null
       and coalesce(used_successful, used_failed, remaining) is not null)
   or tokens_start < used_failed
   or tokens_start < modal_allotment
order by 4, 5, 2, 3
