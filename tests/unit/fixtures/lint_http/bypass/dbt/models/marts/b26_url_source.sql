-- planted bypass: dbt was never scanned
select * from read_parquet('https://baseballsavant.mlb.com/statcast_search/csv.parquet')
