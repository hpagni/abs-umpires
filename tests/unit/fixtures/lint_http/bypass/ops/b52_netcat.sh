#!/bin/sh
printf 'GET /api/v1/schedule HTTP/1.0\r\nHost: statsapi.mlb.com\r\n\r\n' | nc statsapi.mlb.com 80
