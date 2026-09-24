{{ config(materialized='table') }}

-- dim_batter_season -- SOP step W2.18, the marts layer.
--
-- One row per batter-season, grain (batter, season), carrying the height the
-- ABS zone is drawn from. SOP section 2.6 names height_in, height_source,
-- h_abs_in, h_roster_in and roster_offset_in. The first four are on disk in the
-- lake table the heights step wrote; roster_offset_in is the per-batter
-- residual of the calibration SOP W2 section 2 defines, h_abs_in minus
-- h_roster_in, and it is null when either side is missing.
--
-- WHY THIS MODEL READS THE LAKE DIRECTLY. interim/dim_batter_season is not one
-- of the ten tables declared in dbt/models/sources.yml, and that file belongs
-- to another step. The read is the same read the source would issue, guarded by
-- the same lake_has_parquet probe the staging layer uses, so a clean clone with
-- no lake builds this model green and empty rather than failing on a Parquet
-- file that is absent by design. The glob names the two partition keys instead
-- of a bare **, because the directory also holds a _cache file whose columns do
-- not carry the partitions and which makes a ** read fail on a hive mismatch.
--
-- NO official_date COLUMN. The grain is a season, not a day. A null date column
-- here would be counted as a sealed row by the dev target's on-run-start guard,
-- which compares by subtraction, so the four carried columns on this mart are
-- regime, level, season and analysis_set.


{%- set src -%}
read_parquet('{{ env_var("ABS_DATA_ROOT", "data") }}/interim/dim_batter_season/level=*/season=*/*.parquet',
             hive_partitioning=true, union_by_name=true)
{%- endset %}

with source_rows as (

{%- if lake_has_parquet('dim_batter_season') %}
    select
        cast(batter as bigint)                                 as batter,
        cast(season as integer)                                as season,
        cast(level as varchar)                                 as level,
        cast(height_in as double)                              as height_in,
        cast(height_source as varchar)                         as height_source,
        cast(h_abs_in as double)                               as h_abs_in,
        cast(h_roster_in as double)                            as h_roster_in,
        cast(n_called as bigint)                               as n_called,
        cast(n_pitches as bigint)                              as n_pitches
    from {{ src }}
{%- else %}
    select
        cast(null as bigint)                                   as batter,
        cast(null as integer)                                  as season,
        cast(null as varchar)                                  as level,
        cast(null as double)                                   as height_in,
        cast(null as varchar)                                  as height_source,
        cast(null as double)                                   as h_abs_in,
        cast(null as double)                                   as h_roster_in,
        cast(null as bigint)                                   as n_called,
        cast(null as bigint)                                   as n_pitches
    where false
{%- endif %}

),

deduped as (

    select *
    from source_rows
    where batter is not null
      and season is not null
    qualify row_number() over (
        partition by batter, season
        order by coalesce(n_pitches, 0) desc, level
    ) = 1

)

select
    cast(deduped.batter as varchar)
        || ':' || cast(deduped.season as varchar)                  as batter_season_key,
    deduped.batter                                             as batter,
    deduped.season                                             as season,
    deduped.level                                              as level,
    deduped.height_in                                          as height_in,
    deduped.height_source                                      as height_source,
    deduped.h_abs_in                                           as h_abs_in,
    deduped.h_roster_in                                        as h_roster_in,
    deduped.h_abs_in - deduped.h_roster_in                     as roster_offset_in,
    deduped.n_called                                           as n_called,
    deduped.n_pitches                                          as n_pitches,
    case
        when deduped.level = 'aaa' then null
        when deduped.season between 2022 and 2024 then 'pre_buffer'
        when deduped.season = 2025 then 'buffer_2025'
        when deduped.season = 2026 then 'abs_2026'
    end                                                        as regime,
    'open'                                                     as analysis_set
from deduped
