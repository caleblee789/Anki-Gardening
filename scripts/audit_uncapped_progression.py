#!/usr/bin/env python3
"""Bounded paired progression audit over immutable source roots.

Example: python scripts/audit_uncapped_progression.py --source build/.../baseline-source
--output build/.../baseline.json --workers 4. Repeat for candidate, supplying
--openings baseline.json. Use --resume and --only for 200-seed expansions.
This imports the selected source root, never changes its mechanics, and retains
per-seed observations so paired reports do not discard unfinished populations.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import sys
from time import perf_counter


def use_source(root):
    sys.path.insert(0, str(root))
    os.environ['ANKI_GARDEN_SKIP_STARTUP'] = '1'


def run_cell(task):
    root, spec, openings, previous = task
    use_source(root)
    from scripts.balance_analysis.catalog import load_catalog_facts
    from scripts.balance_analysis.model import (APPROVED_STRATEGIES, CohortSpec,
        ScenarioSpec, SimulationConfig, OpeningState, DEFAULT_SEED_ROOT)
    from scripts.balance_analysis.kernel import simulate_scenario
    from scripts.balance_analysis import kernel
    from scripts.balance_analysis.quick import METRICS
    facts = load_catalog_facts()
    # Read-only observation: purchase timing is already committed in RunState.
    original = kernel._checkpoint_metrics
    def metrics(state, catalog):
        row = original(state, catalog)
        for species in catalog.species_ids:
            row['species.' + species + '.purchase_day'] = next(
                (day for day, item, _cost in state.purchases if item == species),
                0 if species == catalog.species_ids[0] else None)
        return row
    kernel._checkpoint_metrics = metrics
    scenario = ScenarioSpec(spec['id'], CohortSpec(**spec['cohort']),
        next(s for s in APPROVED_STRATEGIES if s.strategy_id == spec['policy']),
        rotate_completed_plants=True, starting_profile=spec['profile'],
        missed_week_start_day=spec.get('missed'),
        opening=OpeningState(**openings[spec['profile']]))
    checkpoints = tuple(sorted({d for d in (7,14,30,60,90,180) if d <= spec['days']} | {spec['days']}))
    config = SimulationConfig(seeds=spec['seeds'], days=spec['days'],
        seed_root=DEFAULT_SEED_ROOT, checkpoint_days=checkpoints)
    rows = list(previous.get('samples', [])) if previous else []
    start = perf_counter()
    try:
        for seed in range(len(rows), spec['seeds']):
            result = simulate_scenario(facts, scenario, config, seed, capture_choices=True)
            if result.assertion_failures:
                raise AssertionError((spec['id'], seed, result.assertion_failures))
            observations = {str(day): {key: value for key, value in data.items()
                if key in METRICS or key.startswith(('species.', 'consumables.'))}
                for day, data in result.checkpoints.items()}
            rows.append({'seed':seed, 'checkpoints':observations, 'choices':result.checkpoint_choices})
    finally:
        kernel._checkpoint_metrics = original
    finishes = [r['checkpoints'][str(spec['days'])]['plants.all_catalog_full_bloom_day'] for r in rows]
    reached = sorted(d for d in finishes if d is not None)
    # Nearest-rank population median with unobserved finishes ordered after the horizon.
    middle = (len(rows)-1)//2
    median = reached[middle] if len(reached) > middle else None
    return {**spec, 'samples':rows, 'median':median,
        'earliest':min(reached) if reached else None,
        'day30_finishers':sum(d <= 30 for d in reached),
        'unfinished':len(rows)-len(reached),
        'borderline':any(25 <= d <= 35 for d in reached),
        'runtime_seconds':perf_counter()-start}


def cells():
    rows=[]
    policies=('collection_first','optimal_growth','optimal_coin')
    for profile in ('fresh','established'):
        for answers in (100,200,400,1000):
            for policy in policies:
                cohort_id = ({100:'headline',200:'heavy',400:'power',1000:'quick_stress'}[answers]
                    if profile == 'fresh' else f'established_{answers}')
                rows.append(dict(id=f'{profile}:{answers}:{policy}', profile=profile, policy=policy,
                    cohort=dict(cohort_id=cohort_id,cards_per_study_day=answers,study_days_per_week=7,
                                completion_percent=100),
                    seeds=50 if profile=='fresh' and answers<1000 else 25,
                    days=180 if profile=='fresh' and answers<1000 else 45))
    for name,answers,study,completion,days,missed in (
        ('light',25,6,90,90,None),('inconsistent',200,7,80,180,15)):
        rows.append(dict(id=name,profile='fresh',policy='collection_first',
            cohort=dict(cohort_id='quick_'+name,cards_per_study_day=answers,study_days_per_week=study,
                        completion_percent=completion),seeds=25,days=days,missed=missed))
    assert sum(row['seeds'] for row in rows)==875
    return rows


def compare(paths, output):
    baseline,candidate=(json.loads(Path(p).read_text()) for p in paths)
    assert baseline['openings']==candidate['openings'], 'Opening states differ'
    before={c['id']:c for c in baseline['cells']}
    lines=['# Paired uncapped progression audit','',
        'Frozen capped baseline compared with the full candidate. The historical 55-day median is a comparison point.', '',
        '| Scenario | Median baseline → candidate | Earliest baseline → candidate | Day-30 finishers baseline → candidate | Unfinished baseline → candidate |',
        '|---|---:|---:|---:|---:|']
    pairs=[]
    for after in candidate['cells']:
        old=before[after['id']]
        assert all(old[k]==after[k] for k in ('profile','cohort','policy','days','seeds'))
        def fmt(value): return str(value) if value is not None else 'Unreached'
        values=[' → '.join(fmt(c[k]) for c in (old,after))
            for k in ('median','earliest','day30_finishers','unfinished')]
        lines.append('| '+after['id']+' | '+' | '.join(values)+' |')
        for a,b in zip(old['samples'],after['samples']):
            assert a['seed']==b['seed']
            pairs.append({'scenario':after['id'],'seed':a['seed'],
                'deltas':{day:{key:(b['checkpoints'][day][key]-value
                    if value is not None and b['checkpoints'][day][key] is not None else None)
                    for key,value in metrics.items()} for day,metrics in a['checkpoints'].items()}})
    failed=[c['id'] for c in candidate['cells'] if c['id'] not in ('light','inconsistent')
        and (c['day30_finishers'] or before[c['id']]['day30_finishers'])]
    lines += ['',f"Guardrail: {'FAIL — keep unshipped' if failed else 'PASS for tested scenarios'}.",
        f"Runtime: baseline {baseline['runtime_seconds']:.1f}s; candidate {candidate['runtime_seconds']:.1f}s.",
        '','Per-seed JSON retains Finds, Coins, Growth, supply accounting, species purchase days, and equipment choices.',
        'Daily equipment/purchase heuristics and batched sampling are bounded scenarios, not proof for every player strategy.','']
    output.write_text('\n'.join(lines))
    output.with_suffix('.json').write_text(json.dumps({'failed_cells':failed,'paired_deltas':pairs},indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--openings',type=Path)
    p.add_argument('--resume',type=Path)
    p.add_argument('--only',nargs='+')
    p.add_argument('--seeds',type=int)
    p.add_argument('--compare',nargs=2)
    args=p.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.compare: return compare(args.compare,args.output)
    started=perf_counter(); root=args.source.resolve(); use_source(root)
    from scripts.balance_analysis.quick import source_manifest
    from scripts.balance_analysis.catalog import load_catalog_facts
    from scripts.balance_analysis.opening import production_opening
    from scripts.balance_analysis.model import DEFAULT_SEED_ROOT
    before=source_manifest(root)
    openings=(json.loads(args.openings.read_text())['openings'] if args.openings else
        {profile:asdict(production_opening(profile)) for profile in ('fresh','established')})
    previous=json.loads(args.resume.read_text()) if args.resume else None
    if previous:
        assert previous['source']==before and previous['openings']==json.loads(json.dumps(openings))
    selected=[row for row in cells() if not args.only or row['id'] in args.only]
    if not selected: raise ValueError('No selected cells')
    if args.seeds:
        for row in selected: row['seeds']=args.seeds
    old={c['id']:c for c in previous['cells']} if previous else {}
    results=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(run_cell,[(str(root),row,openings,old.get(row['id'])) for row in selected]):
            results.append(result)
            print(f"{result['id']}: median={result['median']}, day30={result['day30_finishers']}/{result['seeds']}, {result['runtime_seconds']:.1f}s",flush=True)
    assert source_manifest(root)==before, 'Source changed during audit'
    report=dict(source=before,seed_root=DEFAULT_SEED_ROOT,catalog=load_catalog_facts().snapshot,
        openings=openings,cells=results,runtime_seconds=perf_counter()-started,
        resumed_from=str(args.resume) if args.resume else None)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"Saved {args.output}; {report['runtime_seconds']:.1f}s",flush=True)

if __name__=='__main__': main()
