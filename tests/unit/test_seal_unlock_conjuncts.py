"""Every conjunct of `seal._unlocked()`, pinned by flipping it.

The verifier's finding, in one line: the six preconditions were present and
correct, and not one of them was load-bearing. Three mutants -- drop the pushed
tag check, drop five of the six, drop the environment variable itself -- each
passed the whole suite and the registered W1.8 verify command. They could,
because the only assertion was that `_unlocked()` is False in a repository where
the variable is unset and the tag does not exist. In that state the chain is
False whatever it contains, so no assertion on its value can tell six conjuncts
from one.

The fix is to assert on the chain with the other five held true. Each test below
stubs all six preconditions to pass, flips exactly one to fail, and demands a
refusal. A deleted conjunct makes its own test return True where False is
required, so each of the six mutants now has a test that fails on it.

Nothing here touches the real environment, the real repository or any data.
`seal._os` is replaced by a stub whose `environ` is a dictionary, so the
process's own ABS_SEAL_UNLOCK is never written: SOP rule 0.5.1 says only the
owner sets that variable, in one shell, and a test is not the owner.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from absump import seal

# The six, in the order SOP phase 5 lists them and the chain applies them.
ENV, EXISTS, ANCESTOR, CLEAN, HASH, PUSHED = (
    "env",
    "tag_exists",
    "is_ancestor",
    "worktree_clean",
    "prereg_hash",
    "tag_pushed",
)
CONJUNCTS = (ENV, EXISTS, ANCESTOR, CLEAN, HASH, PUSHED)

# Which clause of unlock_report() each conjunct owns, by a word from its name.
CLAUSE_WORD = {
    ENV: seal.UNLOCK_ENV,
    EXISTS: "exists",
    ANCESTOR: "ancestor",
    CLEAN: "clean",
    HASH: "prereg.lock",
    PUSHED: "pushed",
}


def gate(monkeypatch: pytest.MonkeyPatch, failing: str | None = None) -> None:
    """Hold all six preconditions true, except `failing`, which is made false."""
    environ = {seal.UNLOCK_ENV: "0" if failing == ENV else "1"}
    monkeypatch.setattr(seal, "_os", SimpleNamespace(environ=environ))
    monkeypatch.setattr(seal, "_tag_exists", lambda tag: failing != EXISTS)
    monkeypatch.setattr(seal, "_is_ancestor", lambda earlier, later: failing != ANCESTOR)
    monkeypatch.setattr(seal, "_worktree_clean", lambda: failing != CLEAN)
    monkeypatch.setattr(seal, "_prereg_hash_matches", lambda: failing != HASH)
    monkeypatch.setattr(seal, "_tag_is_pushed", lambda remote=seal._REMOTE: failing != PUSHED)


def test_all_six_preconditions_open_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control. Without it, a chain that always refuses would pass every
    other test in this file while being useless."""
    gate(monkeypatch)
    assert seal._unlocked() is True
    assert seal.unlock_report()["ok"] is True
    assert seal.unlock_report()["failed"] == []


@pytest.mark.parametrize("failing", CONJUNCTS)
def test_one_failing_precondition_shuts_the_gate(
    monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    """Five true, one false, in every position. The gate is shut, six times."""
    gate(monkeypatch, failing=failing)
    assert seal._unlocked() is False, f"{failing} is not load-bearing in the chain"


@pytest.mark.parametrize("failing", CONJUNCTS)
def test_the_report_names_the_clause_that_failed(
    monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    """`unlock_report()` is the diagnostic half, and it drifted once already:
    it kept printing six clauses while the chain checked one. It has to name the
    clause that actually failed, and no other."""
    gate(monkeypatch, failing=failing)
    report = seal.unlock_report()
    assert report["ok"] is False
    failed = report["failed"]
    assert len(failed) == 1, failed
    assert CLAUSE_WORD[failing] in failed[0]


def test_the_environment_variable_takes_only_the_documented_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented value is the string 1. Nothing else opens the gate."""
    for value in ("", "0", "true", "yes", "1 ", "TRUE"):
        gate(monkeypatch)
        monkeypatch.setattr(seal, "_os", SimpleNamespace(environ={seal.UNLOCK_ENV: value}))
        assert seal._unlocked() is False, f"{value!r} was accepted"
    gate(monkeypatch)
    monkeypatch.setattr(seal, "_os", SimpleNamespace(environ={}))
    assert seal._unlocked() is False, "an unset variable was accepted"


def test_the_chain_still_has_all_six_conjuncts() -> None:
    """The static half of the same pinning, and the one the W1.8 self-check runs.

    A conjunct can be deleted without changing the chain's value in any allowed
    state of the repository, so the source text is read and counted too.
    """
    import inspect

    chain = inspect.getsource(seal._unlocked).split("return (", 1)[-1]
    assert len(seal._UNLOCK_CONJUNCTS) == 6
    for text in seal._UNLOCK_CONJUNCTS:
        assert text in chain, f"_unlocked() no longer checks {text}"
    assert chain.count(" and ") == 5, "the chain joins something other than six conjuncts"


def test_the_gate_is_shut_in_this_repository() -> None:
    """GD-03, unstubbed: nothing above leaked into the real module state."""
    assert seal._unlocked() is False
    assert seal.unlock_report()["failed"]
