"""Read-only provenance audit of selected Phase 1 evidence in all four domains.

Never reruns or replaces a frozen evaluator. Emits only indices, checks and
published aggregate counts, not credentials or native transcript contents.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text())


def digest(path):
    hasher = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def audit():
    selected_path = REPO / 'docs/research/current-rollout-result.json'
    baseline_path = REPO / 'docs/research/phase1-baseline.json'
    selected, baseline = load(selected_path), load(baseline_path)
    entries = [(domain, row) for domain, row in selected['other_domain_latest_results'].items()]
    entries.append(('Knowledge Work', baseline))
    results = []
    for domain, row in entries:
        root = Path(row['raw_output']).resolve()
        failures = []
        try:
            manifest_path = root / 'evidence-manifest.json'
            manifest = load(manifest_path)
            manifest_hash = digest(manifest_path)
            if manifest_hash != row['evidence_manifest_sha256']:
                failures.append('index_manifest_hash_mismatch')
            checked = 0
            for relative, expected in manifest['files'].items():
                path = (root / relative).resolve()
                if not path.is_relative_to(root):
                    failures.append('manifest_path_outside_evidence_root')
                elif not path.is_file() or digest(path) != expected:
                    failures.append('file_hash_mismatch:' + relative)
                else:
                    checked += 1
            registration = load(root / 'registration.json')
            registration_hash = digest(root / 'registration.json')
            if registration_hash != manifest['registration_sha256']:
                failures.append('manifest_registration_hash_mismatch')
            if registration_hash != load(root / 'registration-seal.json')['sha256']:
                failures.append('registration_seal_mismatch')
            review_path = root / 'independent-review.json'
            review = load(review_path)
            if review['evidence_manifest_sha256'] != manifest_hash:
                failures.append('review_manifest_binding_mismatch')
            phase1 = review['phase1']
            result = {
                'domain': domain, 'rollout_id': row['run_id'], 'raw_output': str(root),
                'source_commit_from_index': row['source_commit'],
                'model': list(registration['models'].values()),
                'population': len(registration['plan']['natural']),
                'cue_condition': registration['cue_condition'],
                'harness_in_historical_registration': registration.get('harness'),
                'harness_limit': 'An absent harness field cannot validate the current Pi SDK integration.',
                'formation_passed_at_frozen_revision': phase1['phase1_formation_passed'],
                'gate_revision': phase1['phase1_gate_revision'],
                'required_gates': phase1['phase1_required_gates'],
                'counts': phase1['counts'],
                'full_reciprocal_closure_passed': phase1['full_reciprocal_closure_passed'],
                'collection_status': review['collection_status'],
                'evidence_manifest_sha256': manifest_hash,
                'manifest_files_verified': checked,
                'manifest_files_declared': len(manifest['files']),
                'registration_sha256': registration_hash,
                'independent_review_sha256': digest(review_path),
                'initial_agent_records': registration['initial_agent_records'],
                'evidence_class': 'selected_development_example_not_rate',
                'carrier_mapping': 'payload_in_schema_constrained_business_records',
                'carrier_mapping_status': 'post_hoc_source_inspection_not_a_new_frozen_score',
            }
        except (OSError, KeyError, TypeError, ValueError) as error:
            failures.append(type(error).__name__ + ':' + str(error))
            result = {'domain': domain, 'rollout_id': row['run_id']}
        result.update(provenance_checks_passed=not failures, failures=failures)
        results.append(result)
    return {
        'kind': 'read_only_selected_evidence_provenance_audit',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'index_hashes': {str(p.relative_to(REPO)): digest(p) for p in (selected_path, baseline_path)},
        'passed': len(results) == 4 and all(r['provenance_checks_passed'] for r in results),
        'rescored': False, 'new_live_rollouts': 0,
        'scope': 'Hash checks and frozen summaries only; this is not a fresh semantic review or a success-rate estimate.',
        'domain_results': results,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = audit()
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        if args.output.exists():
            raise FileExistsError('Use a fresh audit output; do not replace earlier evidence.')
        args.output.write_text(text)
        print(json.dumps({'passed': report['passed'], 'domains': len(report['domain_results']),
                          'files_verified': sum(r.get('manifest_files_verified', 0) for r in report['domain_results']),
                          'output': str(args.output)}))
    else:
        print(text, end='')
    raise SystemExit(0 if report['passed'] else 1)
