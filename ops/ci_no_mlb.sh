#!/usr/bin/env bash
# ops/ci_no_mlb.sh -- SOP step W9.10: no CI runner makes a network call to an MLB host.
#
# SOP project-level clause 3, verbatim: "CI is green on every push in under 8 minutes
# with **zero network calls to MLB hosts from any runner**." CI sees the synthetic
# fixtures and the fixture DuckDB only. This script is how the clause is enforced on
# the runner itself, in every job of ci.yml and seal-guard.yml, rather than trusted.
#
# HOW IT IS ENFORCED. Three parts.
#   1. Prevention (arm). Every MLB-family host this repository names is written into
#      /etc/hosts as 0.0.0.0 and ::. glibc reads /etc/hosts before DNS, so a lookup
#      returns the any-address and a connection to it is refused on the runner. No
#      packet leaves for those hosts. ops/ci_check.py fails if a tracked file names an
#      MLB-family host that is missing from the list below, so the list cannot fall
#      behind the code.
#   2. Detection (arm, then audit). The runner's resolver is systemd-resolved. arm
#      starts `resolvectl monitor`, which logs every query the resolver answers, and
#      proves it is observing by looking up a random canary name and finding it in the
#      log. If that fails it falls back to a packet capture on port 53, with the same
#      canary proof. audit stops the observer and fails the job if any name in the MLB
#      family was asked for: mlb.com, milb.com, mlbstatic.com, mlbinfra.com, mlbam.com,
#      mlbam.net, mlb.tv, and every subdomain of each. A sinkholed name is answered
#      from /etc/hosts and never reaches the resolver, which is why part 1 covers the
#      named hosts and part 2 covers every other name in the family.
#   3. Integrity (audit). The sinkhole must still be in /etc/hosts at the end of the
#      job, so a step that rewrote the file cannot pass quietly.
# If no observer can be started and proved, arm exits 1. Enforcement that cannot see
# is not enforcement, so the job goes red instead of passing unobserved.
#
# Usage:
#   ops/ci_no_mlb.sh arm         Linux runner only, first step after checkout
#   ops/ci_no_mlb.sh audit       last step of every job, under if: always()
#   ops/ci_no_mlb.sh scan FILE   exit 1 if FILE names an MLB-family host, print the lines
#   ops/ci_no_mlb.sh hosts       print the sinkhole list, one host per line
#   ops/ci_no_mlb.sh selftest    any machine, no root, no network: proves scan and list
#
# Exit: 0 clean, 1 an MLB-family name observed or enforcement not in place, 2 misuse.
# No network call is made by this script except the canary lookup, which is a random
# name under example.com, a domain IANA reserves for exactly this use.

set -uo pipefail

# The sinkhole list. Every MLB-family host named in a tracked file, plus the hosts
# baseballr, pybaseball and the Gameday and Savant front ends are known to reach.
HOSTS="
statsapi.mlb.com
ws.statsapi.mlb.com
beta-statsapi.mlb.com
baseballsavant.mlb.com
gdx.mlb.com
gd2.mlb.com
x.mlb.com
www.mlb.com
mlb.com
content.mlb.com
lookup-service-prod.mlb.com
builds.mlbstatic.com
img.mlbstatic.com
midfield.mlbstatic.com
bdfed.stitch.mlbinfra.com
www.milb.com
milb.com
"

# The family. A name matches when one of these is its registrable suffix, on a label
# boundary: statsapi.mlb.com and MLB.COM. match, notmlb.com and mlb.community do not.
FAMILY='(^|[^a-z0-9-])([a-z0-9-]+\.)*(mlb\.com|milb\.com|mlbstatic\.com|mlbinfra\.com|mlbam\.com|mlbam\.net|mlb\.tv)([^a-z0-9-]|$)'

STATE="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ci-no-mlb"
LOG="$STATE/dns.log"
MARK_BEGIN="# ci_no_mlb sinkhole begin"
MARK_END="# ci_no_mlb sinkhole end"

say() { printf 'NO-MLB %s\n' "$*"; }
die() {
    printf 'NO-MLB FAIL: %s\n' "$*" >&2
    exit 1
}

host_list() { printf '%s\n' "$HOSTS" | sed '/^$/d'; }

scan() {
    # Prints every line of $1 that names an MLB-family host, with its line number.
    # Exit 1 on a hit, 0 when clean, 2 when the file is absent.
    [ -f "$1" ] || {
        printf 'NO-MLB scan: no such file %s\n' "$1" >&2
        return 2
    }
    if grep -Ein -- "$FAMILY" "$1"; then
        return 1
    fi
    return 0
}

canary_seen() {
    # $1 the observer log, $2 the canary name. Wait up to 10 s for the line to land.
    local i=0
    while [ "$i" -lt 20 ]; do
        grep -qi -- "$2" "$1" 2>/dev/null && return 0
        sleep 0.5
        i=$((i + 1))
    done
    return 1
}

start_observer() {
    # $1 the method: resolvectl or tcpdump. Starts it in the background, writes the
    # pid and method into $STATE, and proves it sees a query. Returns 0 when proved.
    local method="$1" pid canary
    : >"$LOG"
    case "$method" in
        resolvectl)
            command -v resolvectl >/dev/null 2>&1 || return 1
            sudo -n stdbuf -oL -eL resolvectl monitor >>"$LOG" 2>&1 &
            ;;
        tcpdump)
            command -v tcpdump >/dev/null 2>&1 || return 1
            sudo -n stdbuf -oL -eL tcpdump -l -n -i any 'port 53' >>"$LOG" 2>&1 &
            ;;
        *) return 1 ;;
    esac
    pid=$!
    sleep 2
    if ! ps -p "$pid" >/dev/null 2>&1; then
        say "observer $method exited at start: $(tail -3 "$LOG" | tr '\n' ' ')"
        return 1
    fi
    printf '%s\n' "$pid" >"$STATE/observer.pid"
    printf '%s\n' "$method" >"$STATE/observer.method"
    canary="ci-no-mlb-canary-$RANDOM$RANDOM.example.com"
    getent hosts "$canary" >/dev/null 2>&1 || true
    if canary_seen "$LOG" "$canary"; then
        say "observer $method is live: canary $canary seen in the log"
        return 0
    fi
    say "observer $method did not log the canary $canary; stopping it"
    stop_observer
    return 1
}

stop_observer() {
    local pid i=0
    [ -f "$STATE/observer.pid" ] || return 0
    pid=$(cat "$STATE/observer.pid")
    # $pid is sudo's; sudo relays the signal to the observer, which flushes and exits.
    sudo -n kill -INT "$pid" >/dev/null 2>&1 || true
    while ps -p "$pid" >/dev/null 2>&1 && [ "$i" -lt 10 ]; do
        sleep 0.5
        i=$((i + 1))
    done
    sudo -n kill -TERM "$pid" >/dev/null 2>&1 || true
    rm -f "$STATE/observer.pid"
}

arm() {
    [ "$(uname -s)" = "Linux" ] || die "arm runs on a Linux CI runner; use selftest here"
    sudo -n true 2>/dev/null || die "arm needs passwordless sudo, which GitHub-hosted runners have"
    mkdir -p "$STATE"

    # 1. prevention
    {
        printf '%s\n' "$MARK_BEGIN"
        host_list | while read -r h; do printf '0.0.0.0 %s\n:: %s\n' "$h" "$h"; done
        printf '%s\n' "$MARK_END"
    } | sudo -n tee -a /etc/hosts >/dev/null || die "could not append the sinkhole to /etc/hosts"
    local h addr n=0
    for h in $(host_list); do
        addr=$(getent ahostsv4 "$h" 2>/dev/null | awk 'NR == 1 { print $1 }')
        [ "$addr" = "0.0.0.0" ] || die "$h resolves to '${addr:-nothing}', not the sinkhole"
        n=$((n + 1))
    done
    say "sinkhole in place: $n hosts resolve to 0.0.0.0 on this runner"

    # 2. detection
    if start_observer resolvectl || start_observer tcpdump; then
        say "armed: $(cat "$STATE/observer.method") observing every lookup; log $LOG"
        return 0
    fi
    die "no observer could be started and proved; the no-MLB clause cannot be enforced on this runner"
}

audit() {
    [ -d "$STATE" ] && [ -f "$STATE/observer.method" ] \
        || die "arm did not run in this job, so nothing was observed"
    local method rc hits n
    method=$(cat "$STATE/observer.method")
    stop_observer

    # 3. integrity
    grep -qxF "$MARK_BEGIN" /etc/hosts && grep -qxF "$MARK_END" /etc/hosts \
        || die "the sinkhole is no longer in /etc/hosts"
    for h in $(host_list); do
        grep -qE "^0\.0\.0\.0 ${h//./\\.}\$" /etc/hosts || die "sinkhole line for $h is gone"
    done

    n=$(wc -l <"$LOG" | tr -d ' ')
    hits=$(scan "$LOG")
    rc=$?
    if [ "$rc" -eq 1 ]; then
        printf 'NO-MLB FAIL: this job asked the resolver for an MLB-family host:\n%s\n' "$hits" >&2
        exit 1
    fi
    [ "$rc" -eq 0 ] || die "the observer log $LOG is missing"
    say "PASS: $method logged $n lines, 0 MLB-family names; sinkhole intact"
}

selftest() {
    local fails=0 line h
    # global, not local: the EXIT trap runs after this function has returned.
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/ci_no_mlb.XXXXXX") || exit 2
    trap 'rm -rf "${tmp:-}"' EXIT
    # Planted observer lines. Each positive must be caught, each negative must pass.
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        printf '%s\n' "$line" >"$tmp/log"
        if scan "$tmp/log" >/dev/null; then
            printf 'selftest FAIL: missed   %s\n' "$line"
            fails=$((fails + 1))
        else
            printf 'selftest ok:   caught   %s\n' "$line"
        fi
    done <<'POS'
→ Q: statsapi.mlb.com IN A
← A: baseballsavant.mlb.com IN AAAA 2600:1901::1
12:00:01 IP 10.1.0.4.40111 > 168.63.129.16.53: 4242+ A? gdx.mlb.com. (29)
Q: img.MLBSTATIC.com IN A
Q: prod-gameday.mlbinfra.com IN A
Q: www.milb.com IN A
Q: MLB.COM. IN A
Q: media.mlbam.net IN A
Q: tv.mlb.tv IN A
POS
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        printf '%s\n' "$line" >"$tmp/log"
        if scan "$tmp/log" >/dev/null; then
            printf 'selftest ok:   passed   %s\n' "$line"
        else
            printf 'selftest FAIL: flagged  %s\n' "$line"
            fails=$((fails + 1))
        fi
    done <<'NEG'
→ Q: github.com IN A
Q: objects.githubusercontent.com IN AAAA
Q: pypi.org IN A
Q: packagemanager.posit.co IN A
Q: notmlb.com IN A
Q: mlb.community.example.org IN A
Q: ci-no-mlb-canary-1234.example.com IN A
NEG
    # The list itself: every entry is in the family, and none is repeated.
    for h in $(host_list); do
        printf '%s\n' "$h" >"$tmp/log"
        if scan "$tmp/log" >/dev/null; then
            printf 'selftest FAIL: %s is on the sinkhole list but outside the family\n' "$h"
            fails=$((fails + 1))
        fi
    done
    if [ -n "$(host_list | sort | uniq -d)" ]; then
        printf 'selftest FAIL: repeated hosts: %s\n' "$(host_list | sort | uniq -d | tr '\n' ' ')"
        fails=$((fails + 1))
    fi
    if [ "$fails" -ne 0 ]; then
        printf 'NO-MLB selftest FAIL: %s problem(s)\n' "$fails"
        exit 1
    fi
    printf 'NO-MLB selftest PASS: 9 planted MLB lookups caught, 7 clean lookups passed, %s sinkhole hosts all in the family\n' \
        "$(host_list | wc -l | tr -d ' ')"
}

case "${1:-}" in
    arm) arm ;;
    audit) audit ;;
    scan)
        [ "$#" -eq 2 ] || { echo "usage: ops/ci_no_mlb.sh scan FILE" >&2; exit 2; }
        scan "$2"
        ;;
    hosts) host_list ;;
    selftest) selftest ;;
    *)
        echo "usage: ops/ci_no_mlb.sh arm | audit | scan FILE | hosts | selftest" >&2
        exit 2
        ;;
esac
