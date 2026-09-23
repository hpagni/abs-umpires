-- ANALYSIS SET v1. OWNER DECISION 2026-09-22. Frozen at tag prereg-v1. Do not edit after.
-- gameType codes verified live against statsapi 2026-09-22:
--   R regular, F wild card, D division, L championship, W world series, S spring, A all-star, E exhibition
CASE
  WHEN game_type IN ('S','A','E')                                        THEN 'excluded'
  WHEN season = 2026 AND game_type = 'R' AND official_date >= DATE '2026-09-22' THEN 'sealed'
  WHEN season = 2026 AND game_type IN ('F','D','L','W')                  THEN 'sealed'
  ELSE 'open'
END AS analysis_set
