{#-
  dbt/macros/no_rows_where.sql -- SOP step W2.17.

  A generic data test that fails when any row of a model satisfies a condition.
  dbt ships not_null, unique, accepted_values and relationships, and this
  project installs no test package, so a clause such as "every MLB 2026
  challenge resolves to a Statcast pitch" has nowhere else to live.

  The condition is SQL, written against the model's own columns, and the test
  returns the offending rows so a failure shows the data rather than only a
  count. Give every use a `name:` in the properties file, because two conditions
  on one model would otherwise collide on the default test name.
-#}

{%- test no_rows_where(model, condition) -%}

select *
from {{ model }}
where {{ condition }}

{%- endtest -%}
