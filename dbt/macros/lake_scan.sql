{#-
  dbt/macros/lake_scan.sql -- SOP step W2.17.

  The staging layer reads ten lake tables through the external_location on the
  `lake` source. Two of them hold no bytes on some machines: `abs_leaderboard`
  is W4.3's pull and has not landed, and a clean clone has no lake at all. A
  model that reads a missing Parquet glob fails the whole build on a file that
  is absent by design, which hides every real failure behind it.

  `lake_scan` returns the source read when the glob has at least one file, and a
  zero-row select with the same column names when it has none. The column list
  is the one the calling model casts, so the model compiles and builds either
  way and the DAG stays complete. Every column of the stub is varchar and null;
  the model's own casts give each one its type, so a stub view and a live view
  have the same shape.

  The probe runs once per model per run, against the same DuckDB session the
  model builds in. During `dbt parse` there is no connection and `run_query`
  returns nothing, so the probe reports the source read and nothing is skipped
  at parse time.

  ABS_DATA_ROOT is the lake root, and `data` is the default that
  src/absump/paths.py and dbt/models/sources.yml already use. The path is
  relative to the process working directory, which is the repository root for
  every command in quality/steps.yml.
-#}

{%- macro lake_has_parquet(table_name) -%}
  {%- if not execute -%}
    {{- return(true) -}}
  {%- endif -%}
  {%- set root = env_var('ABS_DATA_ROOT', 'data') -%}
  {%- set probe = run_query(
        "select count(*) as n from glob('" ~ root ~ "/interim/" ~ table_name ~ "/**/*.parquet')") -%}
  {%- if probe is none or probe.rows | length == 0 -%}
    {{- return(false) -}}
  {%- endif -%}
  {{- return(probe.rows[0][0] | int > 0) -}}
{%- endmacro -%}


{%- macro lake_scan(table_name, columns) -%}
  {%- if lake_has_parquet(table_name) -%}
select * from {{ source('lake', table_name) }}
  {%- else -%}
select
    {% for column in columns %}cast(null as varchar) as {{ column }}{{ "," if not loop.last }}
    {% endfor %}
where false
  {%- endif -%}
{%- endmacro -%}
