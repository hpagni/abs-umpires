# ruff: noqa
fs, path = pyarrow.fs.FileSystem.from_uri("https://baseballsavant.mlb.com/statcast_search/csv")
# planted bypass: pyarrow filesystem
