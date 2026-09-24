{{ config(materialized='table', tags=['smoke']) }}

-- mart_called_pitches -- SOP step W1.11, the smoke-build called-pitch table.
--
-- SUPERSEDED BY fct_called_pitch, SOP step W2.18, which is the contract table
-- SOP section 2.6 declares. New analysis code reads v_called_pitch_open. This
-- model is kept because dbt/models/sources.yml carries its three tests and that
-- file belongs to another step, and because the ci target needs one mart it can
-- build with no lake and no warehouse file.
--
-- One row per called pitch: description in ('called_strike', 'ball',
-- 'blocked_ball'). Every row carries regime, level, season, official_date and
-- analysis_set, so a filter mistake is visible rather than silent
-- (SOP section 2.6).
--
-- TWO TARGETS, ONE COLUMN VOCABULARY. Every target but ci reads
-- int_called_pitch, the intermediate W2.17 built over the lake, and takes its
-- column names unchanged. The ci target has no lake: it builds over the
-- 200-row synthetic seed through stg_statcast_pitches, whose ci branch keeps
-- the flat seed shape. The two branches now agree on every column name they
-- share, so a query written against one does not silently mean something else
-- on the other.
--
-- WHAT THE ci BRANCH DOES NOT CARRY. plate_x and plate_z: the seed's raw pair
-- has no re-projected counterpart, and publishing a bare plate_x invites the
-- mistake the whole plane transition is about -- raw Statcast coordinates are
-- front-plane through 2025 and mid-plane from 2026, so a column called plate_x
-- means two different measurements depending on the season. The real branch
-- publishes plate_x_mid, plate_z_mid, plate_x_front, plate_z_front and
-- plane_source, which say which plane they are on; the ci branch publishes
-- neither pair. play_id and pitch_slot are likewise absent on ci: play_id is
-- not in the Statcast CSV at all and reaches the models through
-- stg_pitch_joined, and the feed's pitch_slot, which is what ABS challenges are
-- keyed on, has no meaning in a flat seed with no slots in it.
--
-- The regime split is SOP W2.17's int_regime: 2022-2024 pre_buffer, 2025
-- buffer_2025, 2026 abs_2026 at MLB level. The AAA split is taken from
-- has_abs_challenges, never from the weekday.

{% if target.name == 'ci' %}

with pitches as (
    select *
    from {{ ref('stg_statcast_pitches') }}
    where description in ('called_strike', 'ball', 'blocked_ball')
      and official_date <= date '{{ var("last_open_date") }}'
),

challenges as (
    select
        pitch_uid,
        is_overturned,
        challenge_team_id,
        challenger_role,
        call_original,
        call_final
    from {{ ref('stg_abs_challenges') }}
    where review_level = 'event'
)

select
    pitches.pitch_uid,
    pitches.game_pk,
    pitches.at_bat_number,
    pitches.pitch_number,
    pitches.level,
    pitches.season,
    pitches.official_date,
    pitches.game_type,
    case
        when pitches.level = 'aaa' and pitches.has_abs_challenges then 'aaa_challenge'
        when pitches.level = 'aaa' then 'aaa_full_abs'
        when pitches.season <= 2024 then 'pre_buffer'
        when pitches.season = 2025 then 'buffer_2025'
        else 'abs_2026'
    end                                                        as regime,
    case
        when pitches.game_type in ('S', 'A', 'E') then 'excluded'
        else 'open'
    end                                                        as analysis_set,
    pitches.sz_top,
    pitches.sz_bot,
    pitches.balls,
    pitches.strikes,
    pitches.outs_when_up,
    pitches.inning,
    pitches.inning_topbot,
    pitches.stand,
    pitches.p_throws,
    pitches.batter,
    pitches.pitcher,
    pitches.fielder_2,
    pitches.pitch_type,
    pitches.release_speed,
    pitches.description,
    pitches.delta_run_exp,
    case when pitches.description = 'called_strike' then 1 else 0 end as cs,
    challenges.pitch_uid is not null                           as challenged,
    challenges.is_overturned                                   as is_overturned,
    challenges.challenge_team_id                               as challenge_team_id,
    challenges.challenger_role                                 as challenger_role,
    challenges.call_original                                   as call_original,
    coalesce(challenges.call_final, pitches.description)       as call_final
from pitches
left join challenges
    on pitches.pitch_uid = challenges.pitch_uid

{% else %}

select
    called.pitch_uid,
    called.game_pk,
    called.at_bat_number,
    called.pitch_number,
    called.pitch_slot,
    called.play_id,
    called.level,
    called.season,
    called.official_date,
    called.game_type,
    called.regime,
    called.analysis_set,
    called.plate_x_mid,
    called.plate_z_mid,
    called.plate_x_front,
    called.plate_z_front,
    called.plane_source,
    called.sz_top,
    called.sz_bot,
    called.balls,
    called.strikes,
    called.outs_when_up,
    called.inning,
    called.inning_topbot,
    called.stand,
    called.p_throws,
    called.batter,
    called.pitcher,
    called.fielder_2,
    called.pitch_type,
    called.release_speed,
    called.description,
    called.delta_run_exp,
    called.cs,
    called.d_signed_in,
    called.edge_dist_r_in,
    called.challenged,
    called.is_overturned,
    called.challenge_team_id,
    called.challenger_role,
    called.call_original,
    called.call_final,
    called.umpire_hp_id,
    called.umpire_season
from {{ ref('int_called_pitch') }} as called

{% endif %}
