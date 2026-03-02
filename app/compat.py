"""Backward-compatibility shim for numpy 2.0+.

chromadb==0.4.22 references ``np.float_``, ``np.int_``, and ``np.uint``
which were removed in NumPy 2.0.  This module restores the aliases so
that the rest of the stack can import chromadb without crashing.

Import this module **before** any ``import chromadb`` statement.
It is safe to call multiple times — subsequent imports are a no-op.
"""

import numpy as np

_ALIASES = {
    "float_": "float64",
    "int_": "int64",
    "uint": "uint64",
}

for _old, _new in _ALIASES.items():
    if not hasattr(np, _old):
        setattr(np, _old, getattr(np, _new))
