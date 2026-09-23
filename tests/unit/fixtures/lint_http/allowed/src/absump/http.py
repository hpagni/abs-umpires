# ruff: noqa
# The Python chokepoint. Every idiom the linter knows appears here on purpose.
import http.client
import socket
import subprocess
import urllib.request
from urllib.request import urlopen

import aiohttp
import httpx
import requests
from httpx import get
from requests import get as g


def fetch(url: str) -> bytes:
    client = httpx.Client()
    httpx.post(url, json={})
    requests.get(url)
    http.client.HTTPSConnection("statsapi.mlb.com")
    socket.create_connection(("statsapi.mlb.com", 443))
    subprocess.run(["curl", "-s", url], check=True)
    return client.get(url).content
