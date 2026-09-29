{{ config(materialized='view') }}

-- v_umpire_game_open -- the read rule, SOP section 2.6, applied to the umpire
-- dimension. DECISIONS.md D-P4-45.
--
-- Section 2.6 names four open views, one per fact table. dim_umpire_game is a
-- dimension, but its grain is a game and every row carries the official_date
-- of that game, so a held-out game could reach it the same way it could reach
-- a fact table. Chapter 2 reads the plate umpire of each challenge from it, so
-- it gets the same treatment as the facts: model code reads this view and not
-- the table.
--
-- Two restrictions. The first is the open label, as in the four section 2.6
-- views. The second is the last open day, which the base table already applies
-- when it is built; it is written again here so that the view holds the
-- boundary itself and does not depend on how the table was built. Today the
-- two select the same rows, so this view returns exactly the open rows of its
-- base, which is what quality/verify_contract.py check C5 asserts.

select *
from {{ ref('dim_umpire_game') }}
where analysis_set = 'open'
  and official_date <= date '{{ var("last_open_date") }}'
