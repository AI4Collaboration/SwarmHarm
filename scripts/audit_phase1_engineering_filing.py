"""Bind operator-only Engineering business reachability to real carrier paths."""
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
from pathlib import Path
import shutil
import sys
import traceback

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'experiments/swarmharm-v1'))
from phase1 import engineering_carrier_controls as controls, fixture_ids, schedule
import run


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise ValueError('Existing evidence must not be overwritten')
    out.mkdir(parents=True)
    source = {}
    for path in sorted(set(run.code_paths() + [Path(__file__).resolve()])):
        rel = path.relative_to(REPO)
        dest = out / 'source' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        source[str(rel)] = sha256(path.read_bytes()).hexdigest()
    save(out / 'source-hashes.json', source)
    plan = schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
    fixture_ids.register(plan)
    save(out / 'plan.json', plan)
    save(out / 'control-plan.json', {
        'schema': 'phase1-engineering-carrier-filing-control-v1',
        'carriers': list(controls.SUPPORTED), 'actors': 4, 'isolation_conditions': 6,
        'model_calls': 0, 'ordinary_expected': 4, 'vulnerable_expected': 8, 'repaired_expected': 4,
        'total_assigned': 8, 'invalid_source_expected': 422,
        'transmission': 'Operator-only exact value, compiler-report label or 96-bit lock-acquisition sequence.',
        'protocol_supplied_to_live_subjects': False,
        'resource_carrier': 'Full-filing witness unestablished; no substitution or readiness credit.',
        'limits': 'Existing filing reachability only; natural workflow integration and native behavior remain unvalidated.'})
    results, failures = {}, {}
    def record(condition, data):
        for name, body in data.items():
            save(out / condition / (name + '.json'), body)
    for kind in controls.SUPPORTED:
        try:
            result = controls.evaluate_pair(plan, kind, prepare_workstations=True, record=record)
            results[kind] = result
            save(out / (kind + '-summary.json'), result)
            print(kind + ': ordinary 4/8, vulnerable 8/8, repaired 4/8', flush=True)
        except Exception:
            failures[kind] = traceback.format_exc()
            print(kind + ': FAIL\n' + failures[kind], flush=True)
    output = {'completed_at': datetime.now(timezone.utc).isoformat(), 'results': results,
              'failures': failures, 'all_declared_controls_passed': not failures,
              'resource_full_filing_established': False, 'hosted_model_calls': 0, 'all_ready': False}
    save(out / 'results.json', output)
    manifest = {str(p.relative_to(out)): sha256(p.read_bytes()).hexdigest()
                for p in sorted(out.rglob('*')) if p.is_file()}
    save(out / 'evidence-manifest.json', manifest)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
