{{ config(materialized='view') }}

-- v_called_pitch_open -- SOP step W2.18, the marts layer.
--
-- SOP section 2.6: model code reads only the v_*_open views. This is
-- fct_called_pitch restricted to the open analysis set, and it is the table
-- every Chapter 1 fit reads.

select *
from {{ ref('fct_called_pitch') }}
where analysis_set = 'open'
