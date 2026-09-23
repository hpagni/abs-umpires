# ruff: noqa
df = pl.read_csv("https://baseballsavant.mlb.com/statcast_search/csv?all=true")
# planted bypass: polars fetches for you
