-- dbt/tests/assert_join_complete.sql -- SOP step W2.19, assertions DT-04 and DT-06.
--
-- GD-04-EXEMPT: construction -- this file's output is an assertion about a fact
-- table: the assertion is about the join's own completeness: every
-- feed pitch, every Statcast row and every review, matched or not. Counting only the
-- open set would let an unmatched row hide behind the seal.
--
-- DT-06 in SOP section 6.3: per game n_api == n_csv == n_matched, with
-- api_only == csv_only == 0. DT-04: blank-coordinate rows are exactly
-- automatic_ball plus untracked, and none of them reach fct_called_pitch.
--
-- Both clauses are about what the join leaves behind and what it lets through,
-- so they are asserted together on the two relations that carry the answer.
--
-- Four clauses:
--
--   api_only / csv_only    a feed pitch with no Statcast row, or a Statcast row
--                          with no feed pitch, in stg_pitch_joined. The third
--                          match_side value, api_unnumbered, is a feed pitch
--                          slot the feed never numbered; it is a known shape of
--                          the source, it is not an unmatched pitch, and it is
--                          not counted here.
--   challenge_without_pitch
--                          an MLB review that resolved to no Statcast pitch.
--                          AAA 2024 reviews carry a null pitch_uid because no
--                          AAA 2024 Statcast day is on disk to match against,
--                          which is an absent source and not a broken join, so
--                          the clause is MLB only.
--   automatic_ball_in_mart an automatic_ball row inside fct_called_pitch. That
--                          is DT-04's 0 leaks: an automatic ball is a pitch the
--                          umpire never called, so a single one in the mart
--                          would enter every umpire-accuracy number as a call.
--
-- DT-04's blank-coordinate rows are the other half. They are bounded rather
-- than zero, at the count tests/data/test_warehouse_pack.py publishes: the mart
-- keeps 762 called pitches whose tracking columns are blank and 22 more whose
-- raw coordinate exists without the kinematics the mid-plane re-projection
-- needs. Each carries tracked = false, W3.7's analysis table filters on that
-- flag, and the count is published in out/tables/data_quality.csv. The bound
-- catches a regression that starts dropping coordinates without failing on the
-- 784 rows that are flagged and explained.
--
-- Re-cut 2026-09-24 from 700 to 900 after the 110-day MLB 2022 backfill grew
-- the mart from 1,610,220 to 1,836,071 rows. The blank rate barely moved,
-- 0.038% to 0.043%, and every blank row is still exactly untracked or missing
-- kinematics, so this is a count bound following its corpus, not a relaxed
-- assertion. Kept in step with test_warehouse_pack.BLANK_MID_IN_MART_MAX.

{% set blank_mid_in_mart_max = 900 %}

with join_sides as (

    select
        'stg_pitch_joined'                                     as relation,
        level                                                  as level,
        season                                                 as season,
        match_side                                             as failure,
        count(*)                                               as n_rows,
        cast(null as bigint)                                   as n_allowed
    from {{ ref('stg_pitch_joined') }}
    where match_side in ('api_only', 'csv_only')
    group by 1, 2, 3, 4

),

challenge_without_pitch as (

    select
        'fct_challenge'                                        as relation,
        level                                                  as level,
        season                                                 as season,
        'challenge_without_pitch'                              as failure,
        count(*)                                               as n_rows,
        cast(0 as bigint)                                      as n_allowed
    from {{ ref('fct_challenge') }}
    where level = 'mlb'
      and (pitch_uid is null or not pitch_matched)
    group by 1, 2, 3, 4

),

automatic_ball_in_mart as (

    select
        'fct_called_pitch'                                     as relation,
        level                                                  as level,
        season                                                 as season,
        'automatic_ball_in_mart'                               as failure,
        count(*)                                               as n_rows,
        cast(0 as bigint)                                      as n_allowed
    from {{ ref('fct_called_pitch') }}
    where description = 'automatic_ball'
    group by 1, 2, 3, 4

),

blank_mid_plane as (

    select
        'fct_called_pitch'                                     as relation,
        cast(null as varchar)                                  as level,
        cast(null as integer)                                  as season,
        'blank_mid_plane_above_bound'                          as failure,
        count(*)                                               as n_rows,
        cast({{ blank_mid_in_mart_max }} as bigint)            as n_allowed
    from {{ ref('fct_called_pitch') }}
    where plate_x_mid is null
       or plate_z_mid is null
    having count(*) > {{ blank_mid_in_mart_max }}

)

select * from join_sides
union all
select * from challenge_without_pitch
union all
select * from automatic_ball_in_mart
union all
select * from blank_mid_plane
