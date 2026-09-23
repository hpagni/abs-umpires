# ruff: noqa
con.execute("INSTALL httpfs; SELECT * FROM read_csv_auto('https://x.mlb.com/a.csv')")
# planted bypass: duckdb httpfs
