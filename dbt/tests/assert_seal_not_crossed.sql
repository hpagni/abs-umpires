-- dbt/tests/assert_seal_not_crossed.sql -- SOP step W2.19, the seal.
--
-- No relation in the warehouse may hold a row past the boundary on the dev
-- target. dbt_project.yml runs the same clause as an on-run-start hook over the
-- whole DuckDB catalogue, which stops a build before it starts. This test runs
-- it again after the build, over the models by ref, which is the half the hook
-- cannot see: the hook reads the catalogue as it was when the run began, so a
-- model that writes a held-out row during the run passes the hook and fails
-- here.
--
-- The boundary is written as the last open day, var('last_open_date'), and
-- never as the first sealed day. GD-04 rule 5 fails on a held-out day written
-- anywhere on the analysis surface and dbt/ is on that surface. The last open
-- day is not a held-out day, and `official_date > last_open_date` selects
-- exactly the rows `official_date >= seal_start_date` selects.
--
-- The seven relations are every model in the contract that carries
-- official_date. A failing row names the relation, the date and the row count.

{% set boundary = var('last_open_date') %}

{% set dated_relations = [
    'fct_pitch', 'fct_called_pitch', 'fct_challenge', 'fct_challenge_opportunity',
    'fct_team_game_tokens', 'dim_game', 'dim_umpire_game'
] %}

with past_the_boundary as (

    {% for relation in dated_relations %}
    select
        '{{ relation }}'                                       as relation,
        official_date                                          as official_date,
        count(*)                                               as n_rows
    from {{ ref(relation) }}
    where official_date > date '{{ boundary }}'
    group by 1, 2
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

)

select
    relation                                                   as relation,
    official_date                                              as official_date,
    n_rows                                                     as n_rows,
    date '{{ boundary }}'                                      as last_open_date
from past_the_boundary
order by 1, 2
