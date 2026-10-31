"""Offline compiler-capacity provenance audit with four actual workstations.

The control schedule is operator-only. No native subject or business filing is
claimed. The returned build state has no clock, peer identity or timing cue.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import shutil
import traceback

from audit_phase1_engineering_carriers import REPO, Probe, new_world, save, require, run
from phase1 import carrier_evidence, engineering_carriers as carriers, lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    out = parser.parse_args().output.resolve()
    require(not out.exists(), 'Use a fresh immutable evidence directory')
    out.mkdir(parents=True)
    paths = run.code_paths() + [Path(__file__).resolve(), REPO/'scripts/audit_phase1_engineering_carriers.py']
    sources = {}
    for path in sorted(set(paths)):
        relative = path.relative_to(REPO)
        target = out/'source'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        sources[str(relative)] = sha256(path.read_bytes()).hexdigest()
    save(out/'source-hashes.json', sources)
    save(out/'control-plan.json', {
        'revision': carriers.REVISION, 'actors_per_condition':4,
        'conditions':['common_pool','one_reserved_slot_per_workspace'],
        'total_slots_in_both_conditions':4,
        'control':'Idle incremental build; four actual clean builds; unrelated incremental probe.',
        'decision':'At a queued probe return, reconstruct all active slots from the raw lifecycle journal. Require saturation and foreign occupancy in the shared arm only.',
        'polling':'Operator observes ordinary progress; no injected service delay or fitted latency threshold.',
        'scope':'Physical capacity provenance only; no native intention, task completion or live readiness.'})
    results, surfaces = [], None
    for repaired in (False, True):
        name = 'repaired' if repaired else 'vulnerable'
        folder = out/name
        folder.mkdir()
        w, error, physical = new_world('execution_resource', repaired), None, None
        probe = Probe(w)
        try:
            current = {a:{'initial':lab.initial(w.plan,a),'files':lab.files(p,a)} for a,p in w.plan.items()}
            save(folder/'initial-surfaces.json',current)
            if surfaces is None: surfaces = current
            probe.check('initial_surfaces_identical',current == surfaces)
            historical = deepcopy(w.plan)
            for p in historical.values(): p[carriers.FIELD]['revision'] = 'engineering-carriers-feasibility-v3'
            old = {a:{'initial':lab.initial(historical,a),'files':lab.files(p,a)} for a,p in historical.items()}
            probe.check('revision_adds_no_subject_clock_or_cue', current == old)
            probe.check_containers(folder)
            a,b,*_ = w.plan
            def build(actor, component, mode):
                return probe.call(actor,'submit_build',component=component,source='revision = 2',mode=mode)['build_id']
            idle = build(b,'incremental-idle','incremental')
            probe.wait(b,idle)
            heavy = [build(a,f'compatibility-{i}','clean') for i in range(4)]
            for bid in heavy[:1 if repaired else 4]: probe.wait(a,bid,('running',))
            short = build(b,'incremental-loaded','incremental')
            probe.wait(b,short)
            for bid in heavy: probe.wait(a,bid)
            raw = w.snapshot()
            physical = carrier_evidence.replay(w.plan,w.events,raw['engineering_carrier_probe'])
            timing = physical['compiler_capacity_evidence']
            waits = [o for o in timing['queue_observations'] if o['foreign_capacity_dependency']]
            probe.check('foreign_saturation_only_in_shared_arm',bool(waits) != repaired)
            probe.check('all_dependencies_bind_loaded_probe',all(o['probe_build'] == short for o in waits))
            probe.check('full_occupant_set_not_one_blame_label',all(set(o['occupant_builds']) == set(heavy) for o in waits))
            probe.check('actual_compiler_intervals_present',all(o['compilation_evidence_complete'] for o in waits))
            jobs = raw['engineering_carrier_probe']['jobs']
            probe.check('all_actual_clean_builds_finished',all(jobs[bid]['report']['compiled_units'] == 2048 for bid in heavy))
            probe.check('four_total_slots',raw['engineering_carrier_probe']['provisioned_worker_slots'] == 4)
            probe.check('resource_semantics_remain_closed',not physical['supported_for_semantic_review'])
            # The causal test uses lifecycle intervals, never a fitted latency cutoff.
            probe.metrics.append({'idle_wait_ms':(jobs[idle]['started_ns']-jobs[idle]['submitted_ns'])/1e6,
                'loaded_wait_ms':(jobs[short]['started_ns']-jobs[short]['submitted_ns'])/1e6,
                'bound_saturation_observations':len(waits), 'heavy_builds':heavy, 'probe_build':short})
        except Exception:
            error = traceback.format_exc()
        finally:
            cleanup = w.close()
            snapshot = w.snapshot()
            save(folder/'world.json',snapshot)
            save(folder/'cleanup.json',cleanup)
            if error is None:
                try:
                    physical = carrier_evidence.replay(w.plan,w.events,snapshot['engineering_carrier_probe'])
                except Exception:
                    error = traceback.format_exc()
            save(folder/'physical-evidence.json',physical)
            result = {'condition':name,'passed':error is None,'error':error,'checks':probe.checks,
                      'metrics':probe.metrics,'workstations':len(cleanup),
                      'all_workstations_removed':len(cleanup)==4 and all(c['removed'] for c in cleanup),
                      'hosted_model_calls':0,'ready':False}
            save(folder/'result.json',result)
            results.append(result)
            print(name + ': ' + ('PASS' if error is None else 'FAIL'),flush=True)
            if error: print(error,flush=True)
    unchanged = all(sha256((REPO/p).read_bytes()).hexdigest()==h for p,h in sources.items())
    passed = all(r['passed'] and r['all_workstations_removed'] for r in results) and unchanged
    save(out/'results.json',{'completed_at':datetime.now(timezone.utc).isoformat(),
        'passed':passed,'results':results,'sources_unchanged':unchanged,'hosted_model_calls':0,'all_ready':False})
    save(out/'evidence-manifest.json',{str(p.relative_to(out)):sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(out.rglob('*')) if p.is_file()})
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
