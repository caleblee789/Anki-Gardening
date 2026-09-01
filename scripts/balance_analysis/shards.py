from __future__ import annotations

"""Deterministic seed-range artifacts for distributed balance analysis."""

from array import array
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Iterator, Mapping, MutableMapping, Optional, Sequence, Tuple
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .artifacts import analysis_source_hashes
from .catalog import (
    CatalogFacts,
    canonical_json_bytes,
    load_catalog_facts,
    to_primitive,
)
from .kernel import (
    CollectedCohort,
    collect_balance_seed_range,
    simulate_balance,
)
from .model import (
    APPROVED_COHORTS,
    APPROVED_SCENARIO_IDS,
    SimulationConfig,
)


SHARD_SCHEMA = "anki-garden-balance-seed-shard-v1"
_MANIFEST_NAME = "manifest.json"
_FLOAT_BYTES = 8
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MetricKey = Tuple[str, int, str]


def shard_seed_range(
    total_seeds: int,
    shard_index: int,
    shard_count: int,
) -> Tuple[int, int]:
    """Return the exact half-open range for one zero-based shard index."""

    total = int(total_seeds)
    index = int(shard_index)
    count = int(shard_count)
    if total <= 0:
        raise ValueError("total_seeds must be positive")
    if count <= 0 or count > total:
        raise ValueError("shard_count must be in [1, total_seeds]")
    if index < 0 or index >= count:
        raise ValueError("shard_index must be in [0, shard_count)")
    return total * index // count, total * (index + 1) // count


def shard_filename(shard_index: int, shard_count: int) -> str:
    width = max(2, len(str(max(0, int(shard_count) - 1))))
    return (
        f"balance-shard-{int(shard_index):0{width}d}-of-"
        f"{int(shard_count):0{width}d}.zip"
    )


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _metric_projection(key: MetricKey) -> Mapping[str, object]:
    scenario_id, checkpoint_day, metric_id = key
    return {
        "scenario_id": scenario_id,
        "checkpoint_day": checkpoint_day,
        "metric_id": metric_id,
    }


def _metric_key(row: Mapping[str, object]) -> MetricKey:
    return (
        str(row.get("scenario_id", "")),
        int(row.get("checkpoint_day", 0) or 0),
        str(row.get("metric_id", "")),
    )


def _exact_total_projection(
    key: MetricKey,
    value: int,
) -> Mapping[str, object]:
    return {**_metric_projection(key), "value": int(value)}


def _write_float_values(stream, values: Sequence[float]) -> bytes:
    encoded = array("d", values)
    if encoded.itemsize != _FLOAT_BYTES:
        raise RuntimeError("balance shards require IEEE-754 binary64 arrays")
    if sys.byteorder != "little":
        encoded.byteswap()
    payload = encoded.tobytes()
    stream.write(payload)
    return payload


def write_balance_shard(
    config: SimulationConfig,
    *,
    shard_index: int,
    shard_count: int,
    output_path: Path,
    repository_root: Path,
    workers: int = 1,
    facts: Optional[CatalogFacts] = None,
) -> Path:
    """Collect and write one deterministic compressed seed-range artifact."""

    seed_start, seed_stop = shard_seed_range(
        config.seeds, shard_index, shard_count
    )
    catalog = facts or load_catalog_facts()
    collected = collect_balance_seed_range(
        config,
        seed_start=seed_start,
        seed_stop=seed_stop,
        facts=catalog if int(workers) == 1 else None,
        workers=workers,
    )
    expected_cohorts = tuple(row.cohort_id for row in APPROVED_COHORTS)
    if tuple(collected) != expected_cohorts:
        raise ValueError("shard collection did not return canonical cohorts")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cohort_manifest: MutableMapping[str, object] = {}
    range_size = seed_stop - seed_start
    with ZipFile(output_path, "w") as archive:
        for cohort_id in expected_cohorts:
            collectors, assertions, exact_totals = collected[cohort_id]
            keys = tuple(sorted(collectors))
            value_name = f"cohorts/{cohort_id}.f64le"
            digest = sha256()
            value_count = 0
            with archive.open(_zip_info(value_name), "w") as stream:
                for key in keys:
                    values = collectors[key]
                    if len(values) != range_size:
                        raise ValueError(
                            f"{cohort_id} metric {key!r} has {len(values)} "
                            f"values; expected {range_size}"
                        )
                    payload = _write_float_values(stream, values)
                    digest.update(payload)
                    value_count += len(values)
            cohort_manifest[cohort_id] = {
                "metrics": [_metric_projection(key) for key in keys],
                "metric_count": len(keys),
                "value_count": value_count,
                "values_file": value_name,
                "values_sha256": digest.hexdigest(),
                "assertion_counts": {
                    str(key): int(value)
                    for key, value in sorted(assertions.items())
                },
                "exact_integer_totals": [
                    _exact_total_projection(key, value)
                    for key, value in sorted(exact_totals.items())
                ],
            }

        manifest = {
            "$schema": SHARD_SCHEMA,
            "archive_format": "zip-deflate-f64le-v1",
            "shard_index": int(shard_index),
            "shard_count": int(shard_count),
            "seed_start": seed_start,
            "seed_stop": seed_stop,
            "seed_count": range_size,
            "simulation_config": to_primitive(config.as_dict()),
            "seed_root_sha256": config.seed_root_sha256,
            "catalog_sha256": catalog.snapshot_sha256,
            "source_files": analysis_source_hashes(repository_root),
            "scenario_ids": list(APPROVED_SCENARIO_IDS),
            "cohorts": dict(cohort_manifest),
        }
        archive.writestr(
            _zip_info(_MANIFEST_NAME),
            canonical_json_bytes(manifest),
        )
    return output_path


def _read_manifest(path: Path) -> Mapping[str, object]:
    try:
        with ZipFile(path, "r") as archive:
            raw = archive.read(_MANIFEST_NAME)
    except (KeyError, OSError) as exc:
        raise ValueError(f"invalid balance shard {path}: {exc}") from exc
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid balance shard manifest {path}: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise ValueError(f"balance shard manifest must be an object: {path}")
    return loaded


def _read_exact(stream, byte_count: int) -> bytes:
    remaining = max(0, int(byte_count))
    chunks = []
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class _MergedShardCollections(Mapping[str, CollectedCohort]):
    """Load and merge one cohort at a time to bound merge-job memory."""

    def __init__(
        self,
        records: Sequence[Tuple[Path, Mapping[str, object]]],
        config: SimulationConfig,
    ) -> None:
        self._records = tuple(records)
        self._config = config
        self._cohort_ids = tuple(row.cohort_id for row in APPROVED_COHORTS)

    def __len__(self) -> int:
        return len(self._cohort_ids)

    def __iter__(self) -> Iterator[str]:
        return iter(self._cohort_ids)

    def __getitem__(self, cohort_id: str) -> CollectedCohort:
        if cohort_id not in self._cohort_ids:
            raise KeyError(cohort_id)
        collectors = defaultdict(lambda: array("d"))
        assertion_counts: Counter = Counter()
        exact_integer_totals: Counter = Counter()
        canonical_keys: Optional[Tuple[MetricKey, ...]] = None

        for path, manifest in self._records:
            cohorts = manifest.get("cohorts")
            if not isinstance(cohorts, Mapping):
                raise ValueError(f"shard has no cohort manifest: {path}")
            row = cohorts.get(cohort_id)
            if not isinstance(row, Mapping):
                raise ValueError(f"shard is missing cohort {cohort_id}: {path}")
            metric_rows = row.get("metrics")
            if not isinstance(metric_rows, Sequence) or isinstance(
                metric_rows, (str, bytes)
            ):
                raise ValueError(f"invalid metric index for {cohort_id}: {path}")
            keys = tuple(
                _metric_key(metric)
                for metric in metric_rows
                if isinstance(metric, Mapping)
            )
            if len(keys) != len(metric_rows):
                raise ValueError(f"invalid metric key for {cohort_id}: {path}")
            if canonical_keys is None:
                canonical_keys = keys
            elif keys != canonical_keys:
                raise ValueError(
                    f"metric index mismatch for cohort {cohort_id}: {path}"
                )

            range_size = int(manifest.get("seed_count", 0) or 0)
            expected_values = len(keys) * range_size
            if int(row.get("metric_count", -1) or -1) != len(keys):
                raise ValueError(f"metric count mismatch for {cohort_id}: {path}")
            if int(row.get("value_count", -1) or -1) != expected_values:
                raise ValueError(f"value count mismatch for {cohort_id}: {path}")
            value_name = str(row.get("values_file", ""))
            expected_digest = str(row.get("values_sha256", ""))
            digest = sha256()
            with ZipFile(path, "r") as archive:
                try:
                    stream = archive.open(value_name, "r")
                except KeyError as exc:
                    raise ValueError(
                        f"missing values payload for {cohort_id}: {path}"
                    ) from exc
                with stream:
                    bytes_per_metric = range_size * _FLOAT_BYTES
                    for key in keys:
                        payload = _read_exact(stream, bytes_per_metric)
                        if len(payload) != bytes_per_metric:
                            raise ValueError(
                                f"truncated values payload for {cohort_id}: {path}"
                            )
                        digest.update(payload)
                        values = array("d")
                        values.frombytes(payload)
                        if sys.byteorder != "little":
                            values.byteswap()
                        collectors[key].extend(values)
                    trailing = stream.read(1)
                    if trailing:
                        raise ValueError(
                            f"oversized values payload for {cohort_id}: {path}"
                        )
            if digest.hexdigest() != expected_digest:
                raise ValueError(
                    f"values checksum mismatch for {cohort_id}: {path}"
                )

            raw_assertions = row.get("assertion_counts", {})
            if not isinstance(raw_assertions, Mapping):
                raise ValueError(f"invalid assertion counts: {path}")
            assertion_counts.update({
                str(key): int(value)
                for key, value in raw_assertions.items()
            })
            raw_totals = row.get("exact_integer_totals", ())
            if not isinstance(raw_totals, Sequence) or isinstance(
                raw_totals, (str, bytes)
            ):
                raise ValueError(f"invalid exact integer totals: {path}")
            for total in raw_totals:
                if not isinstance(total, Mapping):
                    raise ValueError(f"invalid exact integer total: {path}")
                exact_integer_totals[_metric_key(total)] += int(
                    total.get("value", 0) or 0
                )

        for key, values in collectors.items():
            if len(values) != self._config.seeds:
                raise ValueError(
                    f"merged metric {key!r} has {len(values)} values; "
                    f"expected {self._config.seeds}"
                )
        return dict(collectors), assertion_counts, exact_integer_totals


def _validate_shard_manifests(
    paths: Sequence[Path],
    *,
    config: SimulationConfig,
    shard_count: int,
    catalog: CatalogFacts,
    repository_root: Path,
) -> Sequence[Tuple[Path, Mapping[str, object]]]:
    expected_config = to_primitive(config.as_dict())
    expected_sources = analysis_source_hashes(repository_root)
    expected_cohorts = tuple(row.cohort_id for row in APPROVED_COHORTS)
    indexed: MutableMapping[int, Tuple[Path, Mapping[str, object]]] = {}
    for path in paths:
        manifest = _read_manifest(path)
        if manifest.get("$schema") != SHARD_SCHEMA:
            raise ValueError(f"unknown balance shard schema: {path}")
        index = int(manifest.get("shard_index", -1) or 0)
        if index in indexed:
            raise ValueError(f"duplicate balance shard index {index}")
        if int(manifest.get("shard_count", 0) or 0) != int(shard_count):
            raise ValueError(f"shard-count mismatch: {path}")
        if manifest.get("simulation_config") != expected_config:
            raise ValueError(f"simulation-config mismatch: {path}")
        if manifest.get("seed_root_sha256") != config.seed_root_sha256:
            raise ValueError(f"seed-root mismatch: {path}")
        if manifest.get("catalog_sha256") != catalog.snapshot_sha256:
            raise ValueError(f"catalog mismatch: {path}")
        if manifest.get("source_files") != expected_sources:
            raise ValueError(f"analysis-source mismatch: {path}")
        if tuple(manifest.get("scenario_ids", ())) != APPROVED_SCENARIO_IDS:
            raise ValueError(f"scenario identity mismatch: {path}")
        cohorts = manifest.get("cohorts")
        if (
            not isinstance(cohorts, Mapping)
            or set(cohorts) != set(expected_cohorts)
        ):
            raise ValueError(f"cohort identity mismatch: {path}")
        expected_start, expected_stop = shard_seed_range(
            config.seeds, index, shard_count
        )
        if (
            int(manifest.get("seed_start", -1) or 0) != expected_start
            or int(manifest.get("seed_stop", -1) or 0) != expected_stop
            or int(manifest.get("seed_count", -1) or 0)
            != expected_stop - expected_start
        ):
            raise ValueError(f"seed-range mismatch: {path}")
        indexed[index] = (path, manifest)

    missing = sorted(set(range(shard_count)) - set(indexed))
    extra = sorted(set(indexed) - set(range(shard_count)))
    if missing or extra:
        raise ValueError(
            f"incomplete balance shard set: missing={missing}, extra={extra}"
        )
    return tuple(indexed[index] for index in range(shard_count))


def merge_balance_shards(
    config: SimulationConfig,
    *,
    shard_paths: Sequence[Path],
    shard_count: int,
    repository_root: Path,
    parity_evidence: Optional[Mapping[str, object]] = None,
    release_validation_evidence: Optional[Mapping[str, object]] = None,
) -> Mapping[str, object]:
    """Validate and merge a complete shard set through the canonical report."""

    catalog = load_catalog_facts()
    records = _validate_shard_manifests(
        tuple(Path(path) for path in shard_paths),
        config=config,
        shard_count=shard_count,
        catalog=catalog,
        repository_root=repository_root,
    )
    return simulate_balance(
        config,
        facts=catalog,
        precollected_by_cohort=_MergedShardCollections(records, config),
        parity_evidence=parity_evidence,
        release_validation_evidence=release_validation_evidence,
    )
