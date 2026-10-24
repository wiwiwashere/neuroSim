"""Shared marker for tests that need CS1's simulation math.

The core functions in engine/graph.py (input_normalize), perturb.py,
propagate.py, vulnerability.py and baseline.py are placeholders that raise
NotImplementedError. Tests that run them are expected to fail until CS1 fills
them in; once a test passes (XPASS), drop its marker.
"""

import pytest

needs_engine = pytest.mark.xfail(
    raises=NotImplementedError,
    strict=False,
    reason="simulation math not implemented yet (CS1, docs/ENGINE_DESIGN.md)",
)
