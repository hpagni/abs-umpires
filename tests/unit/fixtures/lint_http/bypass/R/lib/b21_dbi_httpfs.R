# planted bypass: httpfs from R
DBI::dbExecute(con, "LOAD httpfs; SELECT * FROM read_csv_auto('https://baseballsavant.mlb.com/statcast_search/csv')")
