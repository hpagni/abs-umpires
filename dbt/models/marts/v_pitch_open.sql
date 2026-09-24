{{ config(materialized='view') }}

-- v_pitch_open -- SOP step W2.18, the marts layer.
--
-- SOP section 2.6: model code reads only the v_*_open views. Each one is
-- SELECT * FROM fct_... WHERE analysis_set = 'open', and nothing else. The
-- point is that a filter mistake in a fit is impossible to make silently: a
-- script that reads this view cannot pick up a spring game, an all-star game or
-- an exhibition, and cannot reach a held-out row, because the fact table it
-- reads was already cut at the last open day.

select *
from {{ ref('fct_pitch') }}
where analysis_set = 'open'
