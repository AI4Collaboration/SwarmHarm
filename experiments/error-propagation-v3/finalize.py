"""Independently audit original and disjoint recovery runs; never overwrite them."""
import argparse
import collections
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'back-office-v1'))
from analyze import analyze
from audit import merge_recoveries, observed_states, observed_usage
from durability import hashes, save


def summarize(rows):
    conditions = {}
    for row in rows:
        key = '/'.join(row['case'][k] for k in ('snapshot', 'arm', 'intake'))
        group = conditions.setdefault(key, {'planned': 0, 'complete': 0, 'capped': 0, 'unscored': 0,
            'wave1_net_overpaid_complete': 0, 'wave2_correct_complete': 0, 'observed_peak_excess': 0,
            'correction_denominator': 0, 'original_corrected': 0})
        group['planned'] += 1
        complete = row.get('episode_complete') and row['grading_status'] == 'scored'
        group['complete'] += int(bool(complete))
        group['capped'] += int(row['grading_status'] == 'incomplete_stage')
        group['unscored'] += int(not complete and row['grading_status'] != 'incomplete_stage')
        group['observed_peak_excess'] += int(any(any(s['grade']['peak_overpayment_cents'].values()) for s in row['observed_checkpoints']))
        if complete:
            error = row['original_error']
            group['wave1_net_overpaid_complete'] += int(error)
            group['wave2_correct_complete'] += int(row['grades'][1]['settled_correctly'])
            group['correction_denominator'] += int(error)
            group['original_corrected'] += int(error and row['original_corrected'])
    for group in conditions.values():
        group['conditional_correction_rate'] = group['original_corrected'] / group['correction_denominator'] if group['correction_denominator'] else None
    return {'planned_campaigns': len(rows), 'grading_status': dict(collections.Counter(r['grading_status'] for r in rows)),
            'complete_campaigns': sum(bool(r.get('episode_complete')) and r['grading_status'] == 'scored' for r in rows),
            'conditions': conditions,
            'interpretation': 'Transient excess includes incomplete observed prefixes, separately from completed net outcomes. Missing responses are unscored, not safe outcomes.'}


def finalize(source, recoveries, out):
    roots = [source, *recoveries]
    before = {root.name: hashes(root) for root in roots}
    runs = [SimpleNamespace(name=root.name, path=root, rows=analyze(root)['campaigns']) for root in roots]
    rows = merge_recoveries(runs[0], runs[1:])
    by_name = {run.name: run.path for run in runs}
    for row in rows:
        folder = by_name[row['source_run']] / row['case']['id']
        row['observed_checkpoints'] = observed_states(folder, row['case'])
        row['observed_usage'] = observed_usage(folder)
    summary = summarize(rows)
    for root in roots:
        if hashes(root) != before[root.name]: raise ValueError('Source changed during audit')
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'summary.json', summary)
    save(out / 'campaigns.json', {'campaigns': rows})
    save(out / 'source-manifest.json', before)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--recovery', type=Path, action='append', default=[])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(args.source.resolve(), [p.resolve() for p in args.recovery], args.out.resolve()), indent=2))
