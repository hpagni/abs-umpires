"""The coverage contract. SOP section 6.2, step W9.5.

SOP section 6.2 closes the unit pack with this clause: a named test is required
for every public function in `absump.joinkey`, `absump.challenges`,
`absump.zone`, `absump.seal` and `absump.geometry`, and a new public function
with no test fails the build.

Three definitions make that clause mechanical.

PUBLIC FUNCTION. A function object whose name does not start with an
underscore and whose `__module__` is the module under test, plus any name the
module exports in `__all__` that resolves to such a function. The union is
deliberate: a function added without touching `__all__` is still public, and a
name exported in `__all__` is public whatever it looks like. Classes and
constants are out of scope, because the SOP clause says function. A re-export,
for example `datetime` imported into the module namespace, is out of scope
because its `__module__` is not this module.

NAMED TEST. A `test_*` function in `tests/unit/` whose name carries the
function's name as a run of whole underscore-separated tokens. `pitch_keys` is
named by `test_pitch_keys` and by `test_ut03_pitch_keys_on_an_intentional_walk`,
and is not named by `test_naive_pitch_keys_lose_keys`, which names
`naive_pitch_keys` instead. Token matching rather than substring matching is
what keeps those two apart. Test names are read out of the files with `ast`, so
nothing in `tests/unit/` is imported or executed to build the list.

NOT YET BUILT. `absump.zone` and `absump.geometry` are written by later steps.
A module that does not import yet, or that holds no code yet, reports skipped
with the reason, and the five module names are asserted separately. That is the
part a reader should check: the contract cannot be satisfied by quietly
dropping a module from the list, because `test_the_contract_names_the_five_sop_modules`
pins the list, and it cannot be satisfied by a module being empty, because
`test_no_module_is_silently_empty` prints which modules carry no public
function at all.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_DIR = REPO_ROOT / "tests" / "unit"

# SOP section 6.2, verbatim and in its own order.
SOP_MODULES: tuple[str, ...] = (
    "absump.joinkey",
    "absump.challenges",
    "absump.zone",
    "absump.seal",
    "absump.geometry",
)


# ---------------------------------------------------------------------------
# reading the two sides
# ---------------------------------------------------------------------------


def _test_names() -> frozenset[str]:
    """Every `test_*` function name in `tests/unit/`, read with `ast`."""
    names: set[str] = set()
    for path in sorted(UNIT_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test"
            ):
                names.add(node.name)
    return frozenset(names)


def _public_functions(module: ModuleType) -> list[str]:
    """The public functions of one module, sorted, by the definition above."""
    found: set[str] = set()
    exported = set(getattr(module, "__all__", ()) or ())
    for name, value in vars(module).items():
        if not inspect.isfunction(value):
            continue
        if getattr(value, "__module__", None) != module.__name__:
            continue
        if name.startswith("_") and name not in exported:
            continue
        found.add(name)
    return sorted(found)


def _is_named_by(function: str, test_name: str, others: frozenset[str] = frozenset()) -> bool:
    """True when `test_name` carries `function` as whole tokens, maximally.

    Two rules, and the second is the one that earns its place. Tokens, not
    substrings, so `pitch_keys` is not named by `test_pitch_keyset`. And the
    matched run must be maximal against `others`, the module's remaining public
    function names: if the run can be extended by one token on either side into
    another public function's name, it names that function and not this one, so
    `test_naive_pitch_keys_lose_keys` names `naive_pitch_keys` alone.
    """
    wanted = function.split("_")
    tokens = test_name.split("_")
    span = len(wanted)
    for i in range(len(tokens) - span + 1):
        if tokens[i : i + span] != wanted:
            continue
        if i > 0 and "_".join(tokens[i - 1 : i + span]) in others:
            continue
        if "_".join(tokens[i : i + span + 1]) in others:
            continue
        return True
    return False


def _import(module: str) -> ModuleType | None:
    try:
        return importlib.import_module(module)
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------


def test_the_contract_names_the_five_sop_modules() -> None:
    """The list is the SOP's list. A module cannot be dropped to pass."""
    assert SOP_MODULES == (
        "absump.joinkey",
        "absump.challenges",
        "absump.zone",
        "absump.seal",
        "absump.geometry",
    )


@pytest.mark.parametrize("module_name", SOP_MODULES)
def test_every_public_function_has_a_named_test(module_name: str) -> None:
    """SOP section 6.2. A new public function with no test fails here."""
    module = _import(module_name)
    if module is None:
        pytest.skip(f"{module_name} is not built yet, so it exports nothing to cover")
    tests = _test_names()
    functions = _public_functions(module)
    missing = [
        f
        for f in functions
        if not any(_is_named_by(f, t, frozenset(set(functions) - {f})) for t in tests)
    ]
    assert missing == [], (
        f"{module_name} exports {len(functions)} public functions and "
        f"{len(missing)} of them have no named test in tests/unit/: "
        f"{', '.join(missing)}. SOP section 6.2 requires one test whose name "
        f"carries the function name, for example test_{missing[0]}."
    )


def test_no_module_is_silently_empty() -> None:
    """A module with no public function passes vacuously, so name the ones that do.

    This does not fail. It is the line a reader needs in order to tell a
    covered module from a module that is not written yet. When the later steps
    land `absump.zone` and `absump.geometry`, this list shrinks and the
    parametrised test above starts doing real work on them.
    """
    empty = []
    for module_name in SOP_MODULES:
        module = _import(module_name)
        if module is None or not _public_functions(module):
            empty.append(module_name)
    covered = [m for m in SOP_MODULES if m not in empty]
    assert covered, f"no module in {list(SOP_MODULES)} carries a public function"
    if empty:
        pytest.skip("no public function yet, so nothing to cover: " + ", ".join(empty))


# ---------------------------------------------------------------------------
# the matcher itself
# ---------------------------------------------------------------------------


def test_token_matching_separates_a_function_from_its_longer_neighbour() -> None:
    """The two matcher rules, each shown failing the naive alternative."""
    neighbours = frozenset({"naive_pitch_keys", "game_pitch_keys"})
    # Tokens, not substrings.
    assert _is_named_by("pitch_keys", "test_pitch_keys", neighbours)
    # Kept short on purpose. A longer literal here ("..._pitch_keys_on_a_walk")
    # carries enough entropy beside the word "keys" that gitleaks' generic-api-key
    # rule reports it as a secret, and this is a test name, not a credential. The
    # shape under test is unchanged: an id run before the token and a run after it.
    assert _is_named_by("pitch_keys", "test_ut03_pitch_keys_up", neighbours)
    assert not _is_named_by("pitch_keys", "test_pitch_keyset", neighbours)
    assert not _is_named_by("frame", "test_frames_are_read")
    assert _is_named_by("frame", "test_frame_refuses_an_unknown_view")
    # Maximal against the neighbours: the longer name claims the run.
    assert not _is_named_by("pitch_keys", "test_naive_pitch_keys_lose_keys", neighbours)
    assert not _is_named_by("pitch_keys", "test_game_pitch_keys_over_a_feed", neighbours)
    assert _is_named_by("naive_pitch_keys", "test_naive_pitch_keys_lose_keys", neighbours)
    # With no neighbours declared, the run is matched as it stands.
    assert _is_named_by("pitch_keys", "test_naive_pitch_keys_lose_keys")


def test_the_test_name_index_is_not_empty() -> None:
    """A broken reader would report full coverage over an empty index."""
    names = _test_names()
    assert len(names) > 100, f"only {len(names)} test names read from {UNIT_DIR}"
    assert "test_every_public_function_has_a_named_test" in names
