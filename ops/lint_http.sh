#!/bin/sh
# ops/lint_http.sh -- SOP section 0.5 rule 2, in executable form.
#
# There are exactly two places in this repository allowed to issue an HTTP
# request: src/absump/http.py on the Python side and R/lib/http.R on the R
# side. Both read config/throttle.yml, so both honour one User-Agent, one
# per-host delay and one daily cap. A third call site would put a pull outside
# the throttle, outside the daily budget and outside data/raw/_manifest.csv,
# which is the audit trail for the legal posture.
#
# Scope. Section 2.3 names src/, R/, tools/ and notebooks/ and six idioms. The
# W1.7 / W2.3 verifier planted thirty realistic bypasses and this script caught
# three, because ops/ and scripts/ were never read and because the six idioms
# are spellings, not behaviours. The scan set is now every directory that holds
# code -- ops scripts R src app dbt notebooks tests tools sql quality -- plus
# the Makefile, and the rules below are grouped by how a request actually gets
# made: a client library, a shell-out, an interpreter one-liner, a library that
# fetches a URL on your behalf, or a credential riding in a URL.
#
# Usage: ops/lint_http.sh [-q|--quiet] [-l|--list] [ROOT]
#   -q     print only failures and the final line.
#   -l     print the rule table and the scan set, then exit 0. Nothing is read.
#   ROOT   scan this directory instead of the repository root. Used by
#          tests/unit/test_lint_http_bypasses.py to plant bypasses in a
#          temporary tree and prove each one is caught.
#
# Exit: 0 clean, 1 a call site outside the two allowed files, 2 misuse.
# POSIX sh. No network, no package load.

set -u

QUIET=0
LIST=0
ROOT=""
for arg in "$@"; do
    case "$arg" in
        -q|--quiet) QUIET=1 ;;
        -l|--list)  LIST=1 ;;
        -h|--help)  sed -n '2,27p' "$0"; exit 0 ;;
        -*) printf 'lint_http: unknown option: %s\n' "$arg" >&2; exit 2 ;;
        *)  ROOT="$arg" ;;
    esac
done

if [ -z "$ROOT" ]; then
    ROOT=$(cd "$(dirname "$0")/.." && pwd)
fi
if [ ! -d "$ROOT" ]; then
    printf 'lint_http: not a directory: %s\n' "$ROOT" >&2
    exit 2
fi

# The only two files allowed to hold a request idiom, by exact path.
ALLOWED='^src/absump/http\.py:|^R/lib/http\.R:'

# Files that carry these idioms as data rather than as code:
#   ops/lint_http.sh              this file, which spells out every rule
#   ops/ci-pending/               parked GitHub Actions workflows. They are not
#                                 repository code, they run on a runner, and the
#                                 one curl there installs gitleaks. They cannot
#                                 be committed at all without the workflow scope.
#   tests/unit/fixtures/lint_http/ the planted bypasses this linter is tested on
#   test_lint_http*.py, test_http_etiquette.py, test_http_delegation.py
#                                 the three tests that plant call sites in a
#                                 temporary tree to prove this linter fires
# Each one would otherwise report its own alphabet. Nothing else may be added
# here without a DECISIONS.md entry, and test_lint_http_bypasses.py pins the
# list to exactly these six.
EXEMPT='^ops/lint_http\.sh:|^ops/ci-pending/|^tests/unit/fixtures/lint_http/|^tests/unit/test_lint_http[a-z_]*\.py:|^tests/unit/test_http_etiquette\.py:|^tests/unit/test_http_delegation\.py:'

SCAN_DIRS=""
for dir in ops scripts R src app dbt notebooks tests tools sql quality; do
    if [ -d "$ROOT/$dir" ]; then SCAN_DIRS="$SCAN_DIRS $dir"; fi
done
SCAN_FILES=""
if [ -f "$ROOT/Makefile" ]; then SCAN_FILES="Makefile"; fi

if [ -z "$SCAN_DIRS$SCAN_FILES" ]; then
    printf 'lint_http: nothing to scan under %s\n' "$ROOT" >&2
    exit 2
fi

SKIP='--exclude-dir=__pycache__ --exclude-dir=.ipynb_checkpoints
--exclude-dir=.Rproj.user --exclude-dir=renv --exclude-dir=.git
--exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=target
--exclude-dir=.pytest_cache --exclude-dir=.ruff_cache'

PY_INC="--include=*.py --include=*.ipynb --include=*.pyi"
R_INC="--include=*.R --include=*.r --include=*.Rmd --include=*.rmd --include=*.qmd --include=*.Rnw"
SH_INC="--include=*.sh --include=*.bash --include=*.zsh --include=*.mk --include=Makefile --include=*.yml --include=*.yaml --include=*.toml"
ANY_INC=""

# ---------------------------------------------------------------------------
# The rule table.
#
#   rule ID LANG REGEX CONJUNCT MESSAGE
#
# LANG picks the file types: py, R, sh, or any. CONJUNCT is a second regex the
# same line must also match, or '-' for none; it is what keeps a rule like
# "subprocess" or "Rscript -e" from firing on the many legitimate uses that
# carry no URL. The six idioms section 2.3 names -- requests., httpx.get,
# httpx.Client, urllib, curl and httr2::request -- are each still caught, by
# PY-REQUESTS, PY-HTTPX, PY-URLLIB, SH-CURL and R-HTTR2 respectively; this
# table is a superset of that acceptance criterion, never a replacement.
# ---------------------------------------------------------------------------

HITS=""
NET='(curl|wget|urllib|requests|httpx|aiohttp|http\.client|socket|urlopen|httr|download\.file|fromJSON|readLines|baseballr|httpfs|https?://)'
ARGV='[[(][[:space:]]*["'"'"'](curl|wget)["'"'"'][[:space:]]*,[[:space:]]*(["'"'"']-|["'"'"']https?://|c\(|[A-Za-z_][A-Za-z0-9_]*[[:space:]]*[],)(])'

rule() {
    _id=$1; _lang=$2; _re=$3; _conj=$4; _msg=$5
    case "$_lang" in
        py) _inc="$PY_INC"; _files="" ;;
        R)  _inc="$R_INC";  _files="" ;;
        sh) _inc="$SH_INC"; _files="$SCAN_FILES" ;;
        *)  _inc="$ANY_INC"; _files="$SCAN_FILES" ;;
    esac
    # shellcheck disable=SC2086
    _out=$(cd "$ROOT" && grep -rnE --binary-files=without-match $SKIP $_inc \
             -- "$_re" $SCAN_DIRS $_files 2>/dev/null)
    if [ -n "$_out" ] && [ "$_conj" != "-" ]; then
        _out=$(printf '%s\n' "$_out" | grep -E -- "$_conj")
    fi
    if [ -n "$_out" ]; then
        _out=$(printf '%s\n' "$_out" | grep -vE "$ALLOWED" | grep -vE "$EXEMPT")
    fi
    if [ -n "$_out" ]; then
        _out=$(printf '%s\n' "$_out" | sed "s/^/  [$_id] /")
        HITS=$(printf '%s\n%s' "$HITS" "$_out")
    fi
    RULES_SEEN="$RULES_SEEN $_id"
    if [ "$LIST" -eq 1 ]; then printf '%-16s %-4s %s\n' "$_id" "$_lang" "$_msg"; fi
}
RULES_SEEN=""

# -- Python client libraries -------------------------------------------------
rule PY-REQUESTS py \
  '(^|[^A-Za-z0-9_])requests\.[a-zA-Z_]+[[:space:]]*\(|(^|[^A-Za-z0-9_])(import|from)[[:space:]]+requests([[:space:]]|$|\.)' \
  '-' 'requests, in any spelling including from requests import get'
rule PY-HTTPX py \
  '(^|[^A-Za-z0-9_])httpx\.(get|post|put|patch|delete|head|options|request|stream|Client|AsyncClient)[[:space:]]*\(|from[[:space:]]+httpx[[:space:]]+import' \
  '-' 'httpx, every verb and both client classes, not only get and Client'
rule PY-URLLIB py \
  'urllib\.(request|parse|error)|from[[:space:]]+urllib|import[[:space:]]+urllib([[:space:]]|$|\.)|urlopen[[:space:]]*\(' \
  '-' 'urllib and urlopen'
rule PY-HTTPCLIENT py \
  'http\.client|HTTPSConnection[[:space:]]*\(|HTTPConnection[[:space:]]*\(|from[[:space:]]+http[[:space:]]+import[[:space:]]+client' \
  '-' 'http.client, the stdlib connection the SOP forgot'
rule PY-AIOHTTP py 'aiohttp' '-' 'aiohttp'
rule PY-SOCKET py \
  'socket\.(socket|create_connection)[[:space:]]*\(|ssl\.(wrap_socket|create_default_context)[[:space:]]*\(' \
  '-' 'a raw socket or TLS context, which is HTTP with extra steps'

# -- shell-outs and interpreter one-liners -----------------------------------
rule PY-SHELLOUT py \
  '(subprocess\.[a-zA-Z_]+|os\.system|os\.popen|os\.execvp?)[[:space:]]*\(' \
  '(curl|wget|https?://|httpie)' \
  'subprocess or os.system carrying curl, wget or a URL'
rule PY-ARGV-CURL py "$ARGV" '-' 'curl or wget as an argv element, no trailing space needed'
rule SH-CURL sh \
  '(^|[^A-Za-z0-9_.-])curl([[:space:]]+(-|["'"'"']?https?://|\$)|[[:space:]]*$)' \
  '-' 'curl in a shell script or the Makefile'
rule SH-WGET sh \
  '(^|[^A-Za-z0-9_.-])wget([[:space:]]+(-|["'"'"']?https?://|\$)|[[:space:]]*$)' \
  '-' 'wget in a shell script or the Makefile'
rule SH-ARGV-CURL sh "$ARGV" '-' 'curl or wget quoted as an argument'
rule SH-HTTPIE sh \
  'httpie|(^|[^A-Za-z0-9_.-])https?[[:space:]]+(GET|POST|PUT|DELETE|HEAD)[[:space:]]|openssl[[:space:]]+s_client' \
  '-' 'httpie or openssl s_client'
rule SH-PYTHON-C sh \
  'python3?[[:space:]]+(-[a-zA-Z]*[[:space:]]+)*-c|uv[[:space:]]+run[[:space:]][^|;]*[[:space:]]-c[[:space:]]' \
  "$NET" 'a python -c one-liner that names a network idiom'
rule R-RSCRIPT sh \
  'Rscript[[:space:]]+(--[a-zA-Z-]+[[:space:]]+)*-e|(^|[[:space:]])R[[:space:]]+(--[a-zA-Z-]+[[:space:]]+)*-e' \
  "$NET" 'an Rscript -e one-liner that names a network idiom'

# -- R client libraries ------------------------------------------------------
rule R-HTTR R 'httr::|library\(httr\)|require\(httr\)' '-' 'httr'
rule R-HTTR2 R \
  'httr2::|library\(httr2\)|require\(httr2\)|(^|[^A-Za-z0-9_.])(request|req_perform)[[:space:]]*\(' \
  '-' 'httr2, including a bare request() after library(httr2)'
rule R-CURLPKG R \
  'curl::|library\(curl\)|require\(curl\)|curl_fetch|curl_download' '-' 'the curl R package'
rule R-DOWNLOAD R 'download\.file[[:space:]]*\(' '-' 'download.file'
rule R-URLCONN R '(^|[^A-Za-z0-9_.])url[[:space:]]*\(' '-' 'a url() connection; local files use file()'
rule R-READLINES R 'readLines[[:space:]]*\(' '(url[[:space:]]*\(|https?://)' 'readLines on a URL'
rule R-SYSTEM R '(^|[^A-Za-z0-9_.])system2?[[:space:]]*\(' \
  '(curl|wget|https?://|httpie)' 'system() or system2() carrying curl, wget or a URL'
rule R-ARGV-CURL R "$ARGV" '-' 'curl or wget as an element of an argv vector'
rule R-BASEBALLR R \
  'baseballr::|statcast_search[[:space:]]*\(|scrape_statcast|mlb_(pbp|schedule|game_pks|batting_orders|probables)[[:space:]]*\(|chadwick_player_lu[[:space:]]*\(' \
  '-' 'baseballr fetches over HTTP itself; baseballr 2.0.0 is installed'

# -- libraries that fetch a URL for you --------------------------------------
rule PY-FETCHLIB py \
  '(read_csv|read_json|read_parquet|read_csv_auto|read_table|read_html|read_excel|read_ipc|scan_csv|scan_parquet|open_dataset|from_uri|get_dataset)[[:space:]]*\(' \
  'https?://' 'a reader given an https URL: polars, pandas, duckdb, pyarrow'
rule R-FETCHLIB R \
  '(read_csv_arrow|read_parquet|open_dataset|fromJSON|read\.csv|read\.delim|read\.table|read_csv|read_tsv|read_json|read_feather)[[:space:]]*\(' \
  '(https?://|url[[:space:]]*\()' 'an R reader given a URL: arrow, jsonlite, readr, utils'
rule ANY-URLREAD any \
  '(read_csv_auto|read_csv|read_json_auto|read_json|read_parquet|read_ndjson|parquet_scan|read_csv_arrow|fromJSON|from_uri|open_dataset|read\.csv)[[:space:]]*\(' \
  'https?://' 'a reader pointed at a URL, in any language including SQL and dbt'
rule ANY-HTTPFS any 'httpfs' 'https?://' \
  'duckdb httpfs on a line carrying a URL turns a SQL read into an HTTP GET'

# -- credentials in a URL ----------------------------------------------------
rule ANY-USERINFO any \
  'https?://[^[:space:]"'"'"'/]*:[^[:space:]"'"'"'/@]*@' \
  '-' 'userinfo in a URL becomes an Authorization: Basic header'
rule ANY-ODDSKEY any \
  '(the-odds-api\.com[^[:space:]"'"'"']*[?&][aA]pi[_-]?[kK]ey=|[?&]apiKey=[A-Za-z0-9]{8,})' \
  '-' 'an api key written into a URL; the-odds-api key belongs in the environment'

if [ "$LIST" -eq 1 ]; then
    printf '\nscan dirs:%s\nscan files: %s\n' "$SCAN_DIRS" "${SCAN_FILES:-none}"
    exit 0
fi

if [ -n "$HITS" ]; then
    printf 'LINT HTTP FAIL: request idiom outside the two allowed call sites.\n' >&2
    printf '%s\n' "$HITS" | sed '/^$/d' >&2
    printf 'Allowed: src/absump/http.py and R/lib/http.R. Route the call through absump.http.get()\n' >&2
    printf 'or absump_http_get(), so it is throttled, budgeted and written to the manifest.\n' >&2
    exit 1
fi

if [ "$QUIET" -eq 0 ]; then
    _n=$(printf '%s' "$RULES_SEEN" | wc -w | tr -d ' ')
    printf 'scanned:%s %s under %s (%s rules)\n' "$SCAN_DIRS" "$SCAN_FILES" "$ROOT" "$_n"
fi
printf 'LINT HTTP OK\n'
exit 0
