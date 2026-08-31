"""Compatibility coverage for the public 2.2 economy simulation wrapper.

Detailed cadence, consumable, environment, and progression behavior belongs to
the focused catalog-ledger and kernel tests. This keeps the legacy wrapper
test from reasserting the retired 2.1 profile-report shape while ensuring it
still yields the canonical 2.2 scenario matrix and reconciliation assertions.
"""

from pathlib import Path

from scripts.balance_analysis.catalog import load_catalog_facts
from scripts.balance_analysis.kernel import simulate_balance
from scripts.balance_analysis.model import SimulationConfig
from scripts.balance_analysis.shards import (
    merge_balance_shards,
    write_balance_shard,
)
from scripts.simulate_balance_profiles import simulate_profiles


def test_simulation_wrapper_emits_the_canonical_2_2_matrix():
    report = simulate_profiles(seeds=1, days=7)
    matrix = report["scenario_matrix"]

    assert report["run"]["report_schema_version"] == 2
    assert report["run"]["days"] == 7
    assert matrix["canonical_scenario_count"] == 66
    assert len(matrix["canonical_scenario_ids"]) == 66
    assert len(matrix["scenarios"]) == 66
    assert len(matrix["cohorts"]) == 6
    assert all(row["status"] == "pass" for row in report["assertions"])


def test_seed_shards_merge_to_the_exact_monolithic_report(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    config = SimulationConfig(seeds=2, days=1, checkpoint_days=(1,))
    facts = load_catalog_facts()
    expected = simulate_balance(config, facts=facts)
    shard_paths = []
    for shard_index in range(2):
        shard_path = tmp_path / f"shard-{shard_index}.zip"
        write_balance_shard(
            config,
            shard_index=shard_index,
            shard_count=2,
            output_path=shard_path,
            repository_root=repository_root,
            facts=facts,
        )
        shard_paths.append(shard_path)

    actual = merge_balance_shards(
        config,
        shard_paths=shard_paths,
        shard_count=2,
        repository_root=repository_root,
    )

    assert actual == expected
