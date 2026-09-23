"""absump: the Python half of the abs-umpires study.

The package is named absump, not abs: abs shadows a Python builtin and reads
badly in tracebacks (SOP section 2.1, package-name resolution).

Submodules are owned by later SOP steps. Nothing is imported here, so that
`python -c "import absump"` (RP-02) stays a pure import with no side effects
and no dependency on work that has not been built yet.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
