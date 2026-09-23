"""GD-10, the pairing half: an UNSEALED claim must be backed by a receipt.

`ops/unseal.sh` appends one line to `docs/prereg/SEAL.md`:

    UNSEALED | utc=... | madrid=... | tag=<tag> | commit=<sha> | head=<sha> | remote=<r>

A line in a markdown file is a claim, and a claim anyone can type. The R2
verifier's GD-09 finding was that nothing tied that claim to an event. This
module defines the artefact that ties it:

    THE UNSEAL RECEIPT.  For an UNSEALED line carrying `tag=<tag>`, the file

        quality/receipts/unseal-<tag>.log

    must exist and must carry the same `commit=<sha>` the line carries. One
    receipt per tag, written by `ops/unseal.sh` at the moment it appends the
    line, never by hand afterwards.

WHAT THIS ASSERTS, AND WHAT IT CANNOT.  The pairing is asserted over the real
tree for every UNSEALED line present. The writer side is asserted too, and since
round 4 it is unconditional: `ops/unseal.sh` writes the receipt, it writes it
BEFORE it appends the claim, and it refuses a second unseal of the same tag.
That closes owner item O-G1. What remains true is that phase 01 has no UNSEALED
line, so the pairing itself is still proved against fixtures rather than against
a real unseal; the first real unseal is the first end-to-end proof, and by then
the writer is already in place rather than being hand-made after the fact.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEAL_DOC = REPO_ROOT / "docs" / "prereg" / "SEAL.md"
UNSEAL_SCRIPT = REPO_ROOT / "ops" / "unseal.sh"
RECEIPTS = REPO_ROOT / "quality" / "receipts"

RECEIPT_GLOB = "unseal-{tag}.log"
_FIELD = re.compile(r"\b(tag|commit)=([^\s|]+)")


def unseal_claims(seal_text: str) -> list[dict[str, str]]:
    """Every real UNSEALED line in the seal log, as {tag, commit}.

    A line carrying `<` is documentation of the format, not an event.
    """
    claims = []
    for line in seal_text.splitlines():
        if not line.strip().startswith("UNSEALED") or "<" in line:
            continue
        fields = dict(_FIELD.findall(line))
        claims.append({"tag": fields.get("tag", ""), "commit": fields.get("commit", "")})
    return claims


def unpaired(seal_text: str, receipts: Path) -> list[str]:
    """The claims with no receipt, or with a receipt naming another commit."""
    bad = []
    for claim in unseal_claims(seal_text):
        tag, commit = claim["tag"], claim["commit"]
        if not tag or not commit:
            bad.append(f"UNSEALED line with no tag= or no commit=: {claim}")
            continue
        receipt = receipts / RECEIPT_GLOB.format(tag=tag)
        if not receipt.is_file():
            bad.append(f"{tag}: no receipt at quality/receipts/{receipt.name}")
        elif commit not in receipt.read_text(encoding="utf-8", errors="replace"):
            bad.append(f"{tag}: receipt does not carry commit={commit}")
    return bad


def test_the_pairing_rule_itself_holds(tmp_path: Path) -> None:
    """The logic, against fixtures, so it is proved even with an empty seal log."""
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    # The stamp is a pre-boundary date on purpose: GD-04 rule 4 reads this file
    # like any other, and a fixture has no business carrying a held-out day.
    line = "UNSEALED | utc=2026-09-01T00:00:00Z | tag=unseal-01 | commit=deadbeef\n"
    assert unpaired(line, receipts), "a claim with no receipt must be reported"
    (receipts / "unseal-unseal-01.log").write_text("commit=cafe\n", encoding="utf-8")
    assert unpaired(line, receipts), "a receipt naming another commit must be reported"
    (receipts / "unseal-unseal-01.log").write_text(
        "tag=unseal-01 commit=deadbeef\n", encoding="utf-8"
    )
    assert not unpaired(line, receipts), "a matching receipt must satisfy the pairing"
    assert not unpaired("UNSEALED | tag=<tag> | commit=<sha>\n", receipts), (
        "the format line in the document is not an event"
    )


def test_every_unsealed_line_has_its_receipt() -> None:
    """GD-10 over the real tree."""
    assert SEAL_DOC.is_file(), f"{SEAL_DOC} is absent; GD-10 has no log to read"
    text = SEAL_DOC.read_text(encoding="utf-8")
    claims = unseal_claims(text)
    bad = unpaired(text, RECEIPTS)
    assert not bad, "GD-10 FAIL: unseal claims with no receipt behind them:\n" + "\n".join(bad)
    if not claims:
        warnings.warn(
            "GD-10 pairing vacuous: docs/prereg/SEAL.md records no UNSEALED line in phase 01",
            stacklevel=1,
        )


def test_the_unseal_script_writes_the_receipt() -> None:
    """The writer side. Unconditional since round 4: the writer exists (O-G1 closed)."""
    assert UNSEAL_SCRIPT.is_file(), "ops/unseal.sh is absent"
    body = UNSEAL_SCRIPT.read_text(encoding="utf-8")
    assert "quality/receipts" in body and "unseal-$TAG.log" in body, (
        "GD-10 FAIL: ops/unseal.sh does not write quality/receipts/unseal-<tag>.log. "
        "The pairing rule is asserted here; without the writer the receipts are hand-made, "
        "which is the one thing the rule exists to forbid."
    )
    receipt_at = body.index("unseal-$TAG.log")
    append_at = body.index('>> "$SEAL_DOC"')
    assert receipt_at < append_at, (
        "GD-10 FAIL: ops/unseal.sh appends the UNSEALED line before it writes the receipt. "
        "The receipt must be written first, so no window exists in which a claim "
        "stands with nothing behind it."
    )
    assert 'if [ -e "$RECEIPT" ]' in body, (
        "GD-10 FAIL: ops/unseal.sh does not refuse a second unseal of the same tag; "
        "the rule is one receipt per tag, never overwritten."
    )
