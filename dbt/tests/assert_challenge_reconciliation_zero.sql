-- dbt/tests/assert_challenge_reconciliation_zero.sql -- SOP step W2.19, DT-15.
--
-- GD-04-EXEMPT: construction -- this file's output is an assertion about a fact
-- table: the assertion is about the challenge fact
-- reconciling to zero against the token ledger. A reconciliation that skipped rows
-- would reconcile to zero by leaving them out.
--
-- DT-15 in SOP section 6.3: the league overturn rate computed from the
-- reconstructed call_original equals the rate the feed reports as
-- sum(usedSuccessful) over sum(challenges), with 0 record difference.
--
-- Two independent counts of the same events. One side is fct_challenge, which
-- is one row per review reconstructed from the play-by-play, where an overturn
-- is is_overturned. The other side is fct_team_game_tokens, which carries the
-- end-of-game absChallenges block the feed writes once per team, where an
-- overturn is used_successful and a challenge is used_successful + used_failed.
-- Nothing flows between them, so an equal count is evidence that the
-- reconstruction found every review and invented none.
--
-- The comparison is per level and season, because a compensating pair of
-- errors in two seasons would cancel in a league total. A level-season whose
-- token block is absent is skipped rather than failed: AAA 2024 feeds carry
-- absChallenges reviews and no end-of-game block, so there is no second count
-- to compare against, and a null is not a difference. The MJ exclusion rule is
-- DT-10 and lives in the accepted_values test on review_type.

with reconstructed as (

    select
        level                                                  as level,
        season                                                 as season,
        count(*)                                               as n_challenges_reconstructed,
        count(*) filter (where is_overturned)                  as n_overturned_reconstructed
    from {{ ref('fct_challenge') }}
    group by 1, 2

),

reported as (

    select
        level                                                  as level,
        season                                                 as season,
        sum(used_successful) + sum(used_failed)                as n_challenges_reported,
        sum(used_successful)                                   as n_overturned_reported
    from {{ ref('fct_team_game_tokens') }}
    group by 1, 2

),

compared as (

    select
        reconstructed.level                                    as level,
        reconstructed.season                                   as season,
        reconstructed.n_challenges_reconstructed               as n_challenges_reconstructed,
        reported.n_challenges_reported                         as n_challenges_reported,
        reconstructed.n_overturned_reconstructed               as n_overturned_reconstructed,
        reported.n_overturned_reported                         as n_overturned_reported
    from reconstructed
    inner join reported
        on reconstructed.level = reported.level
       and reconstructed.season = reported.season
    where reported.n_challenges_reported is not null
      and reported.n_overturned_reported is not null

)

select
    level                                                      as level,
    season                                                     as season,
    n_challenges_reconstructed                                 as n_challenges_reconstructed,
    n_challenges_reported                                      as n_challenges_reported,
    n_overturned_reconstructed                                 as n_overturned_reconstructed,
    n_overturned_reported                                      as n_overturned_reported,
    n_challenges_reconstructed - n_challenges_reported          as challenge_difference,
    n_overturned_reconstructed - n_overturned_reported          as overturn_difference
from compared
where n_challenges_reconstructed <> n_challenges_reported
   or n_overturned_reconstructed <> n_overturned_reported
order by 1, 2
