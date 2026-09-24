{{ config(materialized='view') }}

-- v_challenge_open -- SOP step W2.18, the marts layer.
--
-- SOP section 2.6: model code reads only the v_*_open views. This is
-- fct_challenge restricted to the open analysis set, and it is the table every
-- Chapter 2 fit reads.

select *
from {{ ref('fct_challenge') }}
where analysis_set = 'open'
