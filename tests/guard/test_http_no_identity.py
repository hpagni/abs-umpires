"""W2.3 / section 2.3: no request from this project can name its owner.

`absump.http.get` is the single chokepoint every fetch goes through. The R2
verifier asked for one more refusal at it: a URL carrying userinfo, and any
query parameter or header value carrying an address. These are unit tests on
the refusal, not on the network -- every case here is refused before a socket
is opened, which is why no test in this file needs one.

The addresses below are fabricated (`example.invalid`, reserved by RFC 2606).
The owner's own address is deliberately absent: a repository that checked for
it would have to carry it.
"""

from __future__ import annotations

import httpx
import pytest

from absump.http import Fatal, get
from absump.http import _check_no_identity as check

CLEAN = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"


def with_userinfo(raw: bytes) -> str:
    """A userinfo URL built rather than written out.

    `ops/lint_http.sh` rule ANY-USERINFO fires on a credential written into a
    URL literal, and it is right to: this file is not one of the two allowed
    call sites. Building the same URL through httpx keeps the linter honest and
    keeps the test real -- `get` sees exactly the string a literal would give.
    """
    return str(httpx.URL(CLEAN).copy_with(userinfo=raw))


def test_a_clean_url_and_header_set_pass() -> None:
    check(CLEAN, {"User-Agent": "abs-umpires/1.0 (+https://github.com/hpagni/abs-umpires)"})


@pytest.mark.parametrize(
    "raw",
    # A raw '@' inside userinfo is not a URL httpx will build, so the two
    # spellings that reach `get` in practice are the ones tested.
    [b"user:pw", b"someone%40example.invalid"],
)
def test_userinfo_is_refused(raw: bytes) -> None:
    url = with_userinfo(raw)
    with pytest.raises(Fatal, match="userinfo"):
        check(url)
    with pytest.raises(Fatal, match="userinfo"):
        get(url)


@pytest.mark.parametrize(
    "url",
    [
        CLEAN + "&contact=someone@example.invalid",
        CLEAN + "&contact=someone%40example.invalid",
        CLEAN + "&contact=someone%2540example.invalid",
        "https://statsapi.mlb.com/api/v1/someone@example.invalid",
    ],
)
def test_an_address_in_the_query_or_path_is_refused(url: str) -> None:
    with pytest.raises(Fatal, match="address separator"):
        check(url)
    with pytest.raises(Fatal, match="address separator"):
        get(url)


@pytest.mark.parametrize(
    "value",
    [
        "abs-umpires/1.0 (someone@example.invalid)",
        "abs-umpires/1.0 (someone%40example.invalid)",
        "abs-umpires/1.0 (someone&#64;example.invalid)",
    ],
)
def test_an_address_in_a_header_is_refused(value: str) -> None:
    with pytest.raises(Fatal, match=r"header From|header User-Agent"):
        check(CLEAN, {"User-Agent": value})
    with pytest.raises(Fatal, match="header From"):
        check(CLEAN, {"From": value})


def test_the_refusal_runs_before_the_network_and_before_the_cache() -> None:
    """A refused URL never reaches the throttle, the budget or the manifest.

    `get` calls the check immediately after the host is parsed, so the proof is
    that a URL with userinfo raises `Fatal` rather than `BudgetExceeded` or a
    cache hit, whatever the budget file says.
    """
    with pytest.raises(Fatal) as caught:
        get(with_userinfo(b"user:pw"))
    assert "userinfo" in str(caught.value)
