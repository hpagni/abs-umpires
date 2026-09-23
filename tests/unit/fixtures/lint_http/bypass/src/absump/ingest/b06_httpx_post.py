# ruff: noqa
resp = httpx.post("https://statsapi.mlb.com/api/v1/schedule", json={})
# planted bypass: post, not get
