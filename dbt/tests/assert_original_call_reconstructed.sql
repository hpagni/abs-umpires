-- dbt/tests/assert_original_call_reconstructed.sql -- SOP step W2.19, DT-15.
--
-- GD-04-EXEMPT: construction -- this file's output is an assertion about a fact
-- table: the assertion is about the reconstruction of the
-- original call in the fact tables themselves. It must see every challenged pitch it
-- validates, not the subset an analysis reads.
--
-- call_original is the call the umpire made. call_final is the call the game
-- recorded after any ABS review. Statcast publishes the second one, so the
-- first is reconstructed: on a challenged pitch that was overturned the two
-- differ, and everywhere else they are the same call. Every umpire-accuracy
-- number in the project is computed against call_original, so a reconstruction
-- that silently fell back to call_final would make the whole study measure the
-- ABS system instead of the umpire.
--
-- Four clauses, each a way the reconstruction can be wrong:
--
--   overturned_but_unchanged   a review was upheld and the call did not move
--   upheld_but_changed         a review failed and the call moved anyway
--   unchallenged_but_changed   no review, and the two calls still differ
--   call_outside_vocabulary    a call that is neither ball nor strike
--
-- The population is fct_called_pitch, where both columns are non-null by
-- contract, and fct_challenge, where a review that is still in progress can
-- carry a null call. A null is skipped rather than failed: an in-progress
-- review has no outcome yet, which is not a reconstruction error. DT-22 checks
-- the same reconstruction against the Savant drawer's own original call and is
-- paper tier under D-62.

with called_pitch as (

    select
        'fct_called_pitch'                                     as relation,
        pitch_uid                                              as row_key,
        level                                                  as level,
        season                                                 as season,
        call_original                                          as call_original,
        call_final                                             as call_final,
        challenged                                             as challenged,
        coalesce(is_overturned, false)                         as is_overturned
    from {{ ref('fct_called_pitch') }}

),

challenge as (

    select
        'fct_challenge'                                        as relation,
        challenge_uid                                          as row_key,
        level                                                  as level,
        season                                                 as season,
        call_original                                          as call_original,
        call_final                                             as call_final,
        true                                                   as challenged,
        coalesce(is_overturned, false)                         as is_overturned
    from {{ ref('fct_challenge') }}
    where call_original is not null
      and call_final is not null

),

judged_rows as (

    select * from called_pitch
    union all
    select * from challenge

)

select
    relation                                                   as relation,
    row_key                                                    as row_key,
    level                                                      as level,
    season                                                     as season,
    call_original                                              as call_original,
    call_final                                                 as call_final,
    challenged                                                 as challenged,
    is_overturned                                              as is_overturned,
    case
        when call_original not in ('ball', 'strike')
          or call_final not in ('ball', 'strike')      then 'call_outside_vocabulary'
        when is_overturned and call_original = call_final  then 'overturned_but_unchanged'
        when challenged and not is_overturned
             and call_original <> call_final               then 'upheld_but_changed'
        else 'unchallenged_but_changed'
    end                                                        as failure
from judged_rows
where call_original not in ('ball', 'strike')
   or call_final not in ('ball', 'strike')
   or (is_overturned and call_original = call_final)
   or (challenged and not is_overturned and call_original <> call_final)
   or (not challenged and call_original <> call_final)
order by 1, 2
