import urllib3

urllib3.PoolManager().request("GET", "https://statsapi.mlb.com/api/v1/schedule?sportId=1")
