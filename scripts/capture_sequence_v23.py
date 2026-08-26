#!/usr/bin/env python3
"""Compatibility alias for the repository-owned v25 capture runner.

The v24 AST migration adapter remains frozen in the v25 implementation, but
new orchestration belongs to :mod:`scripts.capture_sequence`.
"""

from __future__ import annotations

import sys

from scripts import capture_sequence as _implementation


if __name__ == "__main__":
    try:
        raise SystemExit(_implementation.main())
    except _implementation.CaptureError as error:
        print(
            _implementation.json.dumps({"error": str(error), "status": "failed"}),
            file=sys.stderr,
        )
        raise SystemExit(1)
else:
    # Returning the canonical module object keeps monkeypatching and private
    # helper imports compatible while ensuring there is one implementation.
    sys.modules[__name__] = _implementation
