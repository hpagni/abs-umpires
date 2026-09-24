-- dbt/tests/assert_null_rate_thresholds.sql -- SOP step W2.19, assertion DT-17.
--
-- GD-04-EXEMPT: construction -- this file's output is an assertion about a fact
-- table: the assertion is about the completeness of the columns
-- the mart publishes, measured on every row of the called-pitch fact. A null rate over
-- a filtered subset is not the mart's null rate.
--
-- DT-17 in SOP section 6.3: on the called-pitch population, each of
-- plate_x_mid, plate_z_mid, sz_top, sz_bot, zone, fielder_2, delta_run_exp,
-- delta_home_win_exp, balls, strikes, outs_when_up, inning, inning_topbot,
-- stand and p_throws is at least 99.5% non-null.
--
-- The share is measured per season, not once over the corpus, because a single
-- season that lost a column would sit far inside a corpus-wide 99.5% and never
-- show. A column is measured on the mart that publishes it. `zone` is a
-- Statcast CSV column that the mart contract does not carry, so it is joined
-- back from stg_statcast_pitches on pitch_uid and measured there.
--
-- DT-17's second clause, `arm_angle` at 99.9%, is not asserted here. No
-- warehouse table carries arm_angle: it is a CSV column that the normalisation
-- keeps in the lake and drops at the staging cast, and
-- tests/data/test_statcast_days.py asserts it where it exists. Reported to the
-- reconciler rather than asserted against a column that is not there.
--
-- A failing row names the season, the column, the row count and the share, so
-- the failure says which season lost which column and by how much.

{% set non_null_floor = 0.995 %}

-- WHICH MART, BY TARGET. fct_called_pitch is lake-built and does not exist on
-- the ci target, which has no lake: asking for it there made this test a
-- runtime error rather than an assertion. The ci target measures the same
-- clause on mart_called_pitches over the 200-row seed, minus the four columns
-- the seed cannot carry -- plate_x_mid and plate_z_mid, because the seed has
-- no re-projected coordinates, and delta_home_win_exp and zone, which are not
-- in the seed's column list. Every other target measures all fifteen on
-- fct_called_pitch, which is what DT-17 asserts.

{% set on_ci = target.name == 'ci' %}
{% set called_relation = 'mart_called_pitches' if on_ci else 'fct_called_pitch' %}

{% set mart_columns = [
    'plate_x_mid', 'plate_z_mid', 'sz_top', 'sz_bot', 'fielder_2',
    'delta_run_exp', 'delta_home_win_exp', 'balls', 'strikes',
    'outs_when_up', 'inning', 'inning_topbot', 'stand', 'p_throws'
] %}

{% if on_ci %}
{% set mart_columns = [
    'sz_top', 'sz_bot', 'fielder_2', 'delta_run_exp', 'balls', 'strikes',
    'outs_when_up', 'inning', 'inning_topbot', 'stand', 'p_throws'
] %}
{% endif %}

{% set measured_columns = mart_columns if on_ci else mart_columns + ['zone'] %}

with population as (

    select
        called.level                                           as level,
        called.season                                          as season,
        {% for column in measured_columns -%}
        {% if column == 'zone' %}staged.zone{% else %}called.{{ column }}{% endif %} as {{ column }}
        {%- if not loop.last %},{% endif %}
        {% endfor %}
    from {{ ref(called_relation) }} as called
    {%- if not on_ci %}
    left join {{ ref('stg_statcast_pitches') }} as staged
        on called.pitch_uid = staged.pitch_uid
    {%- endif %}

),

measured as (

    {% for column in measured_columns %}
    select
        level                                                  as level,
        season                                                 as season,
        '{{ column }}'                                         as column_name,
        count(*)                                               as n_rows,
        count({{ column }})                                    as n_non_null,
        cast(count({{ column }}) as double)
            / nullif(cast(count(*) as double), 0)              as non_null_share
    from population
    group by 1, 2
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

)

select
    level                                                      as level,
    season                                                     as season,
    column_name                                                as column_name,
    n_rows                                                     as n_rows,
    n_non_null                                                 as n_non_null,
    non_null_share                                             as non_null_share,
    {{ non_null_floor }}                                       as non_null_floor
from measured
where non_null_share < {{ non_null_floor }}
order by 6, 1, 2, 3
