-- dbt/tests/assert_row_count_by_day.sql -- SOP step W2.19, assertion DT-01.
--
-- DT-01 in SOP section 6.3: rows per Statcast day < 25,000, on 100% of days,
-- against a maximum observed of 4,500.
--
-- The bound is a ceiling on a day's pull, not a description of a day. Baseball
-- Savant caps a single CSV export, and a day that reaches the cap has been
-- truncated: the rows that came back are then a prefix of the day rather than
-- the day. A full MLB slate is about 5,400 pitch rows, so any day near 25,000
-- is either a truncated export or two days written into one partition.
--
-- The count is per official_date, which is the partition key the lake is
-- written on, and it is taken on the staging model rather than on a mart so
-- that a truncated day is caught before any filter removes rows from it. The
-- comparison is >= because DT-01 states the bound as a strict less-than.

{% set max_rows_per_day = 25000 %}

select
    official_date                                              as official_date,
    level                                                      as level,
    count(*)                                                   as n_rows,
    {{ max_rows_per_day }}                                     as max_rows_per_day
from {{ ref('stg_statcast_pitches') }}
group by 1, 2
having count(*) >= {{ max_rows_per_day }}
order by 3 desc
