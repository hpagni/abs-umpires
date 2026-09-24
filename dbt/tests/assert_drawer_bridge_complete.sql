-- dbt/tests/assert_drawer_bridge_complete.sql -- SOP step W2.19, assertion DT-28.
--
-- GD-04-EXEMPT: construction -- this file's output is an assertion about a fact
-- table: the assertion is about the bridge between the fact
-- table and the Savant drawer. It must see every challenged pitch it validates, not
-- the subset an analysis reads.
--
-- DT-28 in SOP section 6.3: every Savant drawer challenge joins to exactly one
-- Statcast row on (game_pk, round(plate_X, 2), round(plate_Z, 2)), for 100% of
-- 10,167 rows, 0 ambiguous and 0 unmatched. It is the sprint's gate on the 2026
-- original call, and it is what makes DT-23 possible without the feed pull.
--
-- The drawer half of the join is not in the warehouse. W4.2 owns that pull and
-- has landed no drawer file on this machine, and stg_abs_leaderboard is the
-- leaderboard rather than the drawer. What this test asserts is the half that
-- is here: the bridge key itself, on the Statcast side, measured over the
-- challenged MLB 2026 called pitches the drawer will be joined to. If the key
-- is unbuildable or ambiguous on this side, no drawer file can fix it.
--
-- Two clauses:
--
--   bridge_key_missing   a challenged pitch with no raw plate coordinate, so no
--                        bridge key can be built for it at all. Asserted at 0.
--   bridge_key_ambiguous a challenged pitch whose key is shared with another
--                        called pitch in the same game. Bounded, not zero. 18
--                        of the challenged MLB 2026 pitches collide, which is
--                        0.18%: about 295 pitches a game land on a grid whose
--                        cells are 0.01 ft wide, so collisions are the birthday
--                        problem rather than a defect. The bound is the one
--                        tests/data/test_warehouse_pack.py publishes, and the
--                        feed pull DT-28 names as its fallback is already
--                        ingested at 691,502 pitch rows, so the 2026 original
--                        call does not rest on this key.
--
-- The rounding is on the raw plate_x and plate_z from stg_statcast_pitches, and
-- not on the re-projected columns. This test reads season 2026 only, and 2026
-- is the year the raw pair is measured at the middle of the plate: Statcast
-- reports plate_x and plate_z at the front of the plate through 2025 and at the
-- middle from 2026, which is the plane break docs/data-contract.md records and
-- the reason plate_x_mid and plate_x_front exist at all. So the raw pair here
-- is mid-plane, it is what the Savant drawer publishes for 2026, and matching
-- the drawer means rounding the same mid-plane numbers the drawer shows rather
-- than re-projecting first. On a 2025 filter the same two columns would be
-- front-plane and this key would mean something else.
--
-- WHICH CALLED-PITCH RELATION, BY TARGET. fct_called_pitch is lake-built and
-- does not exist on the ci target, which has no lake: asking for it there made
-- this test a runtime error rather than an assertion. The ci target reads
-- mart_called_pitches, which it builds from the 200-row seed and which carries
-- the same pitch_uid, level, season and challenged columns this clause needs.

{% set bridge_ambiguous_max = 40 %}
{% set called_relation = 'mart_called_pitches' if target.name == 'ci' else 'fct_called_pitch' %}

with bridged as (

    select
        called.pitch_uid                                       as pitch_uid,
        called.game_pk                                         as game_pk,
        called.challenged                                      as challenged,
        round(staged.plate_x, 2)                               as bridge_x,
        round(staged.plate_z, 2)                               as bridge_z
    from {{ ref(called_relation) }} as called
    inner join {{ ref('stg_statcast_pitches') }} as staged
        on called.pitch_uid = staged.pitch_uid
    where called.level = 'mlb'
      and called.season = 2026

),

key_counts as (

    select
        game_pk                                                as game_pk,
        bridge_x                                               as bridge_x,
        bridge_z                                               as bridge_z,
        count(distinct pitch_uid)                              as n_pitches_on_key
    from bridged
    where bridge_x is not null
      and bridge_z is not null
    group by 1, 2, 3

),

challenged_pitches as (

    select
        bridged.pitch_uid                                      as pitch_uid,
        bridged.game_pk                                        as game_pk,
        bridged.bridge_x                                       as bridge_x,
        bridged.bridge_z                                       as bridge_z,
        coalesce(key_counts.n_pitches_on_key, 0)               as n_pitches_on_key
    from bridged
    left join key_counts
        on bridged.game_pk = key_counts.game_pk
       and bridged.bridge_x = key_counts.bridge_x
       and bridged.bridge_z = key_counts.bridge_z
    where bridged.challenged

),

counted as (

    select
        count(*) filter (where bridge_x is null or bridge_z is null) as n_missing,
        count(*) filter (where n_pitches_on_key > 1)                 as n_ambiguous,
        count(*)                                                     as n_challenged
    from challenged_pitches

)

select
    'bridge_key_missing'                                       as failure,
    n_missing                                                  as n_rows,
    0                                                          as n_allowed,
    n_challenged                                               as n_challenged
from counted
where n_missing > 0

union all

select
    'bridge_key_ambiguous'                                     as failure,
    n_ambiguous                                                as n_rows,
    {{ bridge_ambiguous_max }}                                 as n_allowed,
    n_challenged                                               as n_challenged
from counted
where n_ambiguous > {{ bridge_ambiguous_max }}
