{#-
  dbt/macros/umpire_column_is_blank.sql -- SOP step W2.17, assertion DT-03.

  DT-03 in SOP section 6.3: `umpire` non-empty count == 0.

  The Statcast CSV carries a column named `umpire` in every export from 2015 to
  2026 and never fills it. The home-plate umpire of this study comes from the
  schedule endpoint's officials block, which W2.5 lands in `game_official`. A
  row where the CSV column is not blank would mean the export changed under the
  project, and every umpire-season number would then have two possible sources.

  The test returns one row per distinct non-blank value, with its count, so a
  failure names what appeared rather than only that something did. Null, the
  empty string and whitespace are all blank.
-#}

{%- test umpire_column_is_blank(model, column_name) -%}

select
    {{ column_name }}                                          as umpire_value,
    count(*)                                                   as n_rows
from {{ model }}
where nullif(trim(coalesce(cast({{ column_name }} as varchar), '')), '') is not null
group by 1

{%- endtest -%}
