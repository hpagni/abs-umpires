# ruff: noqa
subprocess.run(["curl", "-s", "https://statsapi.mlb.com/api/v1/schedule"], check=True)
# planted bypass: argv curl, no trailing space
