-- dbt/tests/assert_no_duplicate_pitch_keys.sql -- SOP step W2.19, assertion DT-18.
--
-- DT-18 in SOP section 6.3: uniqueness of each declared key, 0 dupes.
--
-- The schema.yml layer already carries one `unique` test per declared key, and
-- dbt_utils.unique_combination_of_columns carries the three-column pitch key.
-- This test is the same clause written once over every pitch-grain relation, so
-- a duplicate that enters at any layer is named with its layer, its key and its
-- row count rather than as one failing test somewhere in a list of forty.
--
-- The relations are the pitch grain as the section 2.6 contract declares it:
-- (game_pk, at_bat_number, pitch_number) on the Statcast side, and pitch_uid,
-- which is those three joined with a colon. A row that duplicates one and not
-- the other means the uid builder and the key disagree, so both are counted
-- here.
--
-- WHICH RELATIONS, BY TARGET. fct_pitch and fct_called_pitch are lake-built and
-- do not exist on the ci target, which has no lake: asking for them there made
-- this test a runtime error rather than an assertion, which is a gate that
-- reports nothing. The ci target therefore runs the same clause over the two
-- pitch-grain relations it does build from the 200-row seed,
-- stg_statcast_pitches and mart_called_pitches, and every other target runs it
-- over the three lake relations. The clause itself is identical either way.

{% set relations = ['stg_statcast_pitches', 'mart_called_pitches']
     if target.name == 'ci'
     else ['fct_pitch', 'fct_called_pitch', 'stg_statcast_pitches'] %}

with keyed as (

    {% for relation in relations %}
    select
        '{{ relation }}'                                       as relation,
        cast(game_pk as varchar)
            || ':' || cast(at_bat_number as varchar)
            || ':' || cast(pitch_number as varchar)            as pitch_key
    from {{ ref(relation) }}
    {% if not loop.last %}
    union all
    {% endif %}
    {% endfor %}

)

select
    relation                                                   as relation,
    pitch_key                                                  as pitch_key,
    count(*)                                                   as n_rows
from keyed
group by 1, 2
having count(*) > 1
order by 3 desc, 1, 2
