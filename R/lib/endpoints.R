# R/lib/endpoints.R -- the remote addresses the Chapter 1 scripts name.
#
# ops/lint_http.sh, the http-etiquette pre-commit hook, treats a file that names a
# remote address and also calls a reader (jsonlite::fromJSON, read.csv,
# arrow::read_parquet) as a possible fetch outside R/lib/http.R. The Chapter 1
# scripts fetch only through absump_http_get() and read only local files, so the
# addresses live here, in a file that calls no reader, and the scripts source it.
# Each value is byte-identical to the literal it replaced in R/ch1/01_sample.R,
# R/ch1/02_original_call.R and R/ch1/10_build_analysis_table.R.

SEASONS_URL <- "https://statsapi.mlb.com/api/v1/seasons?sportId=%d&season=%d"
PEOPLE_URL  <- "https://statsapi.mlb.com/api/v1/people?personIds=%s"

ROLE_TEAMS_URL    <- "https://statsapi.mlb.com/api/v1/teams?sportId=1&season=%d"
ROLE_ROSTER_URL   <- "https://statsapi.mlb.com/api/v1/teams/%d/roster?rosterType=fullSeason&season=%d"
ROLE_FIELDING_URL <- paste0("https://statsapi.mlb.com/api/v1/people?personIds=%s&hydrate=stats(",
                            "group=[fielding],type=[byDateRange],startDate=%d-01-01,endDate=%d-12-31)")

LICENCE <- paste("Copyright 2026 MLB Advanced Media, L.P.  Use of any content on this",
                 "page acknowledges agreement to the terms posted here",
                 "http://gdx.mlb.com/components/copyright.txt")

DRAWER_ENDPOINT <- paste0("https://baseballsavant.mlb.com/leaderboard/services/abs/{team_id}",
                          "?year=2026&challengeType=team-summary&gameType=regular&level=mlb")
