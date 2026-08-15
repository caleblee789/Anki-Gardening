"""Capabilities fixed when the add-on archive is built.

The source checkout uses the fail-closed production defaults. The package
builder replaces this module only for an explicitly requested capture build.
"""

from __future__ import annotations


BUILD_MODE = "production"
CAPTURE_HARNESS_ENABLED = False
DEVELOPMENT_MUTATION_ENABLED = False
