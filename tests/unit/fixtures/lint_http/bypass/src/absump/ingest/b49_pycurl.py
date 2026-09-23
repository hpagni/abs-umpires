import pycurl

c = pycurl.Curl()
c.setopt(c.URL, "https://statsapi.mlb.com/api/v1/schedule")
c.perform()
