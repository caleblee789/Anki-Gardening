"""Catalog-driven economy simulation and frozen report artifacts.

The package deliberately has no Anki/Qt dependency.  Production mechanics are
read through :mod:`ankigarden.balance_catalog`; report generation consumes only
the JSON produced by the simulator.
"""

from .model import (
    APPROVED_COHORTS,
    APPROVED_EDGE_CASES,
    APPROVED_STRATEGIES,
    DEFAULT_SEED_COUNT,
    SimulationConfig,
    approved_scenarios,
)

__all__ = [
    "APPROVED_COHORTS",
    "APPROVED_EDGE_CASES",
    "APPROVED_STRATEGIES",
    "DEFAULT_SEED_COUNT",
    "SimulationConfig",
    "approved_scenarios",
]
