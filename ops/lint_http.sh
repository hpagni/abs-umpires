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
# Round 2. The verifier then found five more holes, of three shapes. A module
# named as a string rather than imported by keyword, import_module("requests"),
# which PY-DYNIMPORT now reads. An interpreter started in a shell script whose
# program text is on the following lines, so a same-line conjunct never sees it;
# SH-PYTHON-C and R-RSCRIPT now read their conjunct over the whole file and know
# the stdin and here-doc forms. And a command name held in a shell variable,
# BIN="curl" then "$BIN" -sS URL, which SH-CURL, SH-EXECVAR and SH-CONCAT read.
# It also found that scanning quality/receipts made one failure permanent, since
# a receipt records this linter's own output verbatim; receipts are now excluded
# and the any-language rules carry an include list instead of reading every byte.
#
# Round 3. Eight more bypasses, of the same two shapes, so the fix this time is
# structural rather than one rule per spelling.
#   (i) a same-line conjunct beaten by moving the text one line. The SCOPE=file
#       sixth field, which round 2 added for SH-PYTHON-C, is now what the reader
#       rules use: PY-FETCHLIB, R-FETCHLIB, ANY-URLREAD and ANY-HTTPFS take the
#       URL conjunct over the whole file, so SRC = "https://..." on the line
#       above pd.read_csv(SRC) is read. PY-CMDBUILD inverts the same trick for
#       the shell-out: it matches the command text wherever it is assembled and
#       takes the subprocess call as the file-scope conjunct.
#  (ii) an enumerated list of names, so any sibling library passes. PY-NETIMPORT
#       matches an import by MORPHEME -- a module whose name contains url, http,
#       curl, request, fetch, socket, scrape, web, ftp, rest, grpc or client --
#       which is why urllib3 and pycurl are caught without being listed, and
#       R-NETPKG does the same for library()/:: on the R side. SH-RAWNET adds
#       the transports no rule had at all: nc, ncat, netcat, socat, telnet and
#       bash /dev/tcp. SQL-URI drops the reader name entirely and matches a URI
#       literal in a .sql or .jinja file, because FROM 'https://...' IS the read.
#
# LIMITS -- stated, not silently dropped. This is a text scanner, and three
# things are outside what any text scanner can decide:
#   1. A URL assembled at runtime from parts that are never adjacent in the
#      source -- "".join(["ht","tps://",host]) with host from the environment,
#      or a base64/rot13 blob decoded before use. PY-NETIMPORT, PY-CMDBUILD and
#      the socket rules catch the transport such a URL still has to reach; the
#      address itself is invisible until it exists.
#   2. A request made by a dependency of a dependency. baseballr is named
#      because it is installed here; an arbitrary package that fetches inside
#      its own source is outside this repository's text.
#   3. Whether a matched line ever runs. Every finding is a call SITE, not a
#      call; a commented-out curl is reported and should be, because a comment
#      is one keystroke from code.
#   The behavioural backstop for all three is the throttle's own record:
#   data/raw/_manifest.csv has one row per pull, and a pull that never passed
#   through absump.http.get() leaves the manifest and the on-disk raw tree
#   disagreeing. This linter makes the common shapes cheap to catch; the
#   manifest is what makes an uncaught one visible after the fact.
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
        -h|--help)  sed -n '2,32p' "$0"; exit 0 ;;
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
#   ops/env-setup.sh              machine provisioning, not a data pull: it
#                                 installs uv, R packages and CmdStan. Round 3
#                                 found the gate RED on a clean tree because of
#                                 it -- the uv installer is a curl, and the two
#                                 Rscript -e blocks trip the SCOPE=file
#                                 conjunct. Nothing it fetches is ABS data,
#                                 nothing it writes lands in data/raw, so it is
#                                 outside the throttle by construction rather
#                                 than in evasion of it. Decision recorded in
#                                 logs/decisions-pending/guard.md for DECISIONS.
# Each one would otherwise report its own alphabet. Nothing else may be added
# here without a DECISIONS.md entry, and test_lint_http_bypasses.py pins the
# list to exactly these seven.
EXEMPT='^ops/lint_http\.sh:|^ops/ci-pending/|^ops/env-setup\.sh:|^tests/unit/fixtures/lint_http/|^tests/unit/test_lint_http[a-z_]*\.py:|^tests/unit/test_http_etiquette\.py:|^tests/unit/test_http_delegation\.py:'

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

# quality/receipts and logs hold this linter's own recorded output, one
# "[RULE] path:line:text" per line. Scanning them makes a single failure permanent:
# the failure is written to a receipt, the receipt is scanned, and every later run
# fails on the receipt however clean the tree is. The round-2 verifier reproduced
# exactly that. Receipts and evidence logs are transcripts, not code, so they are
# never read -- the same two prefixes tests/guard/gd04_scan.py excludes.
#
# LIMIT, and the backstop. gd04 excludes by FORMAT and mode inside those two
# directories, so a .sh or an executable there is still scanned by it; grep's
# --exclude-dir is all-or-nothing, so this linter cannot make that distinction.
# What keeps the difference safe is
# tests/guard/test_no_sealed_reads.py::test_no_executable_or_shebang_under_an_excluded_prefix,
# which fails if any file under either directory carries the executable bit or a
# shebang. logs/env-setup.sh, the file that motivated it, now lives at
# ops/env-setup.sh, which this linter scans. If that test is ever deleted, this
# exclusion becomes a hole and must go back to a format-aware filter.
SKIP='--exclude-dir=receipts --exclude-dir=logs
--exclude-dir=__pycache__ --exclude-dir=.ipynb_checkpoints
--exclude-dir=.Rproj.user --exclude-dir=renv --exclude-dir=.git
--exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=target
--exclude-dir=.pytest_cache --exclude-dir=.ruff_cache'

PY_INC="--include=*.py --include=*.ipynb --include=*.pyi"
R_INC="--include=*.R --include=*.r --include=*.Rmd --include=*.rmd --include=*.qmd --include=*.Rnw"
SH_INC="--include=*.sh --include=*.bash --include=*.zsh --include=*.mk --include=Makefile --include=*.yml --include=*.yaml --include=*.toml"
# The any-language rules used to run with no --include at all, so they read
# every byte under the scan set including .log files. They now carry the union of
# the three lists above plus SQL and the data formats a URL can hide in.
SQL_INC="--include=*.sql --include=*.jinja --include=*.j2 --include=*.sql.j2"
ANY_INC="$PY_INC $R_INC $SH_INC --include=*.sql --include=*.json --include=*.jinja --include=*.j2 --include=*.md --include=*.txt --include=*.cfg --include=*.ini"

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
NET='(curl|wget|urllib|requests|httpx|aiohttp|http\.client|socket|urlopen|httr|download\.file|fromJSON|readLines|baseballr|httpfs|/dev/tcp|https?://)'
# URLISH is the file-scope conjunct for "this file handles a remote address".
# It is deliberately not a list of reader names: a URL hoisted to its own line,
# assigned to a variable, or held under a name containing "url" all match.
# It is a scheme, not a reader name and not a word: a bare "url" in prose would
# make every subprocess call in the test suite a finding, and a rule nobody can
# keep green is a rule that gets deleted. What it costs is stated in LIMITS.
URLISH='(https?://|ftps?://|s3://|gs://|abfss?://|wss?://|[A-Za-z0-9_]+://)'
ARGV='[[(][[:space:]]*["'"'"'](curl|wget)["'"'"'][[:space:]]*,[[:space:]]*(["'"'"']-|["'"'"']https?://|c\(|[A-Za-z_][A-Za-z0-9_]*[[:space:]]*[],)(])'

# Sixth field SCOPE: 'line' (default) reads the conjunct on the matched line;
# 'file' reads it anywhere in the same file. A shell script that starts an
# interpreter puts the program text on the following lines, so its conjunct
# cannot be a same-line test; that is how the here-doc python -c escaped.
rule() {
    _id=$1; _lang=$2; _re=$3; _conj=$4; _msg=$5; _scope=${6:-line}
    case "$_lang" in
        py) _inc="$PY_INC"; _files="" ;;
        R)  _inc="$R_INC";  _files="" ;;
        sh) _inc="$SH_INC"; _files="$SCAN_FILES" ;;
        sql) _inc="$SQL_INC"; _files="" ;;
        *)  _inc="$ANY_INC"; _files="$SCAN_FILES" ;;
    esac
    # shellcheck disable=SC2086
    _out=$(cd "$ROOT" && grep -rnE --binary-files=without-match $SKIP $_inc \
             -- "$_re" $SCAN_DIRS $_files 2>/dev/null)
    if [ -n "$_out" ] && [ "$_conj" != "-" ]; then
        if [ "$_scope" = "file" ]; then
            _out=$(printf '%s\n' "$_out" | while IFS= read -r _hit; do
                [ -n "$_hit" ] || continue
                _f=${_hit%%:*}
                if (cd "$ROOT" && grep -qE -- "$_conj" "$_f" 2>/dev/null); then
                    printf '%s\n' "$_hit"
                fi
            done)
        else
            _out=$(printf '%s\n' "$_out" | grep -E -- "$_conj")
        fi
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
  'urllib\.(request|parse|error)|from[[:space:]]+urllib|import[[:space:]]+urllib[0-9]*([[:space:]]|$|\.)|urlopen[[:space:]]*\(' \
  '-' 'urllib and urlopen'
rule PY-HTTPCLIENT py \
  'http\.client|HTTPSConnection[[:space:]]*\(|HTTPConnection[[:space:]]*\(|from[[:space:]]+http[[:space:]]+import[[:space:]]+client' \
  '-' 'http.client, the stdlib connection the SOP forgot'
rule PY-AIOHTTP py 'aiohttp' '-' 'aiohttp'
rule PY-DYNIMPORT py \
  '(importlib\.import_module|__import__)[[:space:]]*\([[:space:]]*(["'"'"'][[:space:]]*(requests|httpx|aiohttp|urllib[a-z0-9_.]*|http\.client|pycurl|urllib3|socket|ssl|websockets?|treq|grequests|pandas|polars|duckdb|pyarrow)|[A-Za-z_]|["'"'"'][^"'"'"']*["'"'"'][[:space:]]*[+%])' \
  '-' 'a module named in a string: import_module("requests"), __import__(name)'
rule PY-NETIMPORT py \
  '(^|[^A-Za-z0-9_])(import|from)[[:space:]]+[A-Za-z_][A-Za-z0-9_]*(url|http|curl|request|fetch|socket|scrape|crawl|spider|web|ftp|rest|grpc|client)[A-Za-z0-9_]*([[:space:]]|$|\.|,)|(^|[^A-Za-z0-9_])(import|from)[[:space:]]+(treq|grequests|niquests|websockets|tls_client|mechanize|scrapy|selenium|playwright|boto3|botocore|paramiko|ftplib|telnetlib|smtplib|pysftp)([[:space:]]|$|\.|,)' \
  '-' 'a module whose name carries a network morpheme (urllib3, pycurl, httplib2, requests_html) or is a known transport, imported by keyword'
rule PY-SOCKET py \
  'socket\.(socket|create_connection)[[:space:]]*\(|ssl\.(wrap_socket|create_default_context)[[:space:]]*\(' \
  '-' 'a raw socket or TLS context, which is HTTP with extra steps'

# -- shell-outs and interpreter one-liners -----------------------------------
rule PY-SHELLOUT py \
  '(subprocess\.[a-zA-Z_]+|os\.system|os\.popen|os\.execv?[lp]*e?|os\.spawn[a-z]*|pty\.spawn|shlex\.split)[[:space:]]*\(' \
  "(curl|wget|httpie|(^|[^A-Za-z0-9_.])(nc|ncat|netcat|socat|telnet)[[:space:]]|/dev/tcp|$URLISH)" \
  'subprocess, os.system or exec on a line carrying curl, wget, a raw transport or a URL'
# MISS 8, round 3: the shell-out line itself can be clean, with the command text
# built above it -- CMD = "cu" "rl -sS https://..." then shlex.split(CMD). The
# conjunct here is the shell-out, read over the whole file, so what has to be
# matched on the line is the command text however it is spelled.
rule PY-CMDBUILD py \
  '["'"'"'](c|cu|cur|curl|w|wg|wge|wget|nc|ncat|netcat|socat|telnet)["'"'"'][[:space:]]*(["'"'"']|\+[[:space:]]*["'"'"'])|=[[:space:]]*["'"'"'](curl|wget|nc|ncat|netcat|socat|telnet|httpie)([[:space:]]|["'"'"'])' \
  '(subprocess\.|os\.system|os\.popen|os\.exec|os\.spawn|pty\.spawn|shlex\.split|shell[[:space:]]*=[[:space:]]*True)' \
  'a command name assembled from string fragments or held in a variable, in a file that shells out' file
rule PY-ARGV-CURL py "$ARGV" '-' 'curl or wget as an argv element, no trailing space needed'
rule SH-CURL sh \
  '(^|[^A-Za-z0-9_.-])curl([[:space:]]+(-|["'"'"']?https?://|\$)|[[:space:]]*$|["'"'"'][[:space:]]*($|[;)&|]))' \
  '-' 'curl in a shell script or the Makefile, including a quoted BIN="curl"'
rule SH-WGET sh \
  '(^|[^A-Za-z0-9_.-])wget([[:space:]]+(-|["'"'"']?https?://|\$)|[[:space:]]*$|["'"'"'][[:space:]]*($|[;)&|]))' \
  '-' 'wget in a shell script or the Makefile, including a quoted BIN="wget"'
rule SH-EXECVAR sh \
  '(^|[|;&(][[:space:]]*)[[:space:]]*((command|exec|eval|env|sudo|time|nohup|xargs)[[:space:]]+)*["'"'"']?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?[A-Za-z0-9_.-]*["'"'"']?[[:space:]]' \
  "$NET" 'a command assembled from a shell variable -- ${C}l as well as "$BIN" -- on a line naming a network idiom'
rule SH-RAWNET sh \
  '(^|[^A-Za-z0-9_./-])(nc|ncat|netcat|socat|telnet|ssh|rsync)([[:space:]]+-[A-Za-z]|[[:space:]]+[A-Za-z0-9_.-]+[[:space:]]+[0-9]{2,5}|[[:space:]]+[A-Za-z0-9_.-]*://)|/dev/(tcp|udp)/|exec[[:space:]]+[0-9]+<>[[:space:]]*/dev/tcp' \
  '-' 'a raw transport: nc, ncat, netcat, socat, telnet or bash /dev/tcp. HTTP is a text protocol; a socket is a call site'
rule SH-CONCAT sh \
  '["'"'"'](c|cu|cur|w|wg|wge)["'"'"']["'"'"'][A-Za-z0-9_.-]*["'"'"']' \
  '-' 'curl or wget split across two adjacent quoted fragments, as in "cu""rl"'
rule SH-ARGV-CURL sh "$ARGV" '-' 'curl or wget quoted as an argument'
rule SH-HTTPIE sh \
  'httpie|(^|[^A-Za-z0-9_.-])https?[[:space:]]+(GET|POST|PUT|DELETE|HEAD)[[:space:]]|openssl[[:space:]]+s_client' \
  '-' 'httpie or openssl s_client'
rule SH-PYTHON-C sh \
  'python3?[[:space:]]+(-[a-zA-Z]*[[:space:]]+)*-c|uv[[:space:]]+run[[:space:]][^|;]*[[:space:]]-c[[:space:]]|python3?[[:space:]]+-([[:space:]]|$)|python3?[[:space:]]*<<|uv[[:space:]]+run[[:space:]][^|;]*[[:space:]]-([[:space:]]|$)' \
  "$NET" 'python -c, python - or a here-doc, in a file that names a network idiom' file
rule R-RSCRIPT sh \
  'Rscript[[:space:]]+(--[a-zA-Z-]+[[:space:]]+)*-e|(^|[[:space:]])R[[:space:]]+(--[a-zA-Z-]+[[:space:]]+)*-e|Rscript[[:space:]]+-([[:space:]]|$)|Rscript[[:space:]]*<<' \
  "$NET" 'Rscript -e or a here-doc, in a file that names a network idiom' file

# -- R client libraries ------------------------------------------------------
rule R-HTTR R 'httr::|library\(httr\)|require\(httr\)' '-' 'httr'
rule R-HTTR2 R \
  'httr2::|library\(httr2\)|require\(httr2\)|(^|[^A-Za-z0-9_.])(request|req_perform)[[:space:]]*\(' \
  '-' 'httr2, including a bare request() after library(httr2)'
rule R-CURLPKG R \
  '[A-Za-z0-9._]*[Cc]url::|(library|require|requireNamespace)\([[:space:]]*["'"'"']?[A-Za-z0-9._]*[Cc]url|curl_fetch|curl_download|(^|[^A-Za-z0-9._])(getURL|getURLContent|getBinaryURL|getForm|postForm|basicTextGatherer)[[:space:]]*\(' \
  '-' 'curl or RCurl in any capitalisation, and the RCurl verbs getURL/getBinaryURL/postForm'
rule R-NETPKG R \
  '[A-Za-z0-9._]*([Cc]url|[Hh]ttp|[Uu]rl|[Rr]equest|[Ss]crape|[Ff]etch|[Rr]vest|[Ss]ocket)[A-Za-z0-9._]*::|(library|require|requireNamespace)\([[:space:]]*["'"'"']?[A-Za-z0-9._]*([Cc]url|[Hh]ttp|[Uu]rl|[Ss]crape|rvest|xml2|[Ww]eb)' \
  '-' 'an R package whose name carries a network morpheme, loaded or called by ::'
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
  "$URLISH" 'a reader in a file that names a remote address -- the URL may be hoisted to a variable on another line' file
rule R-FETCHLIB R \
  '(read_csv_arrow|read_parquet|open_dataset|fromJSON|read\.csv|read\.delim|read\.table|read_csv|read_tsv|read_json|read_feather)[[:space:]]*\(' \
  "($URLISH|url[[:space:]]*\()" 'an R reader in a file that names a remote address; the URL need not be on the reader line' file
rule ANY-URLREAD any \
  '(read_csv_auto|read_csv|read_json_auto|read_json|read_parquet|read_ndjson|parquet_scan|read_csv_arrow|fromJSON|from_uri|open_dataset|read\.csv)[[:space:]]*\(' \
  "$URLISH" 'a reader in a file that names a remote address, in any language including SQL and dbt' file
rule ANY-HTTPFS any 'httpfs|[Ss]3_?[Rr]egion|[Ss]ET[[:space:]]+s3_' "$URLISH" \
  'duckdb httpfs or its S3 settings, in a file that also names a remote address' file
# MISS 7/8, round 3: a URI literal in SQL needs no reader name. DuckDB reads
# FROM 'https://host/x.parquet' directly, so the shape to match is the address,
# not the function around it.
rule SQL-URI sql \
  '["'"'"'][a-z][a-z0-9+.-]*://[^"'"'"'[:space:]]' \
  '-' 'a URI literal in a SQL or dbt model: FROM https://... is itself the fetch'

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
