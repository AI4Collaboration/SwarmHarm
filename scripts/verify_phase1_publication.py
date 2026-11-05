"""Verify the selected current Phase 1 evidence without model or service calls."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def verify(repository: Path, evidence: Path) -> dict:
    load = lambda path: json.loads(path.read_text())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    index = load(repository / 'docs/research/phase1-input-configs.json')
    assert index['all_ready'] and len(index['configs']) == 4
    rows = []
    for config in index['configs']:
        root = evidence / config['rollout']
        result = config['result']
        reg = load(root / 'registration.json')
        terminal = load(root / 'evidence-manifest.json')
        review = load(root / 'review-manifest.json')
        assert reg['scenario'] == config['scenario']
        assert reg['models'] == {'sol61': 'openai/gpt-6.1-sol'}
        assert reg['harness']['kind'] == 'codex'
        assert reg['harness']['authentication'] == 'axonhub'
        assert digest(root / 'registration.json') == terminal['registration_sha256']
        assert digest(root / 'evidence-manifest.json') == review['terminal_manifest_sha256']
        assert digest(root / 'review-manifest.json') == result['review_manifest_sha256']
        for manifest in (terminal['files'], review['review_files']):
            for path, expected in manifest.items():
                assert digest(root / path) == expected, (root.name, path)
        for path, expected in reg['code_hashes'].items():
            assert digest(root / 'code' / path) == expected, path
            committed = subprocess.check_output(
                ['git', 'show', result['source_commit'] + ':' + path], cwd=repository)
            assert hashlib.sha256(committed).hexdigest() == expected, path
        for path, expected in reg['input_hashes'].items():
            assert digest(root / path) == expected, path
        for variants in reg['task_hashes'].values():
            for paths in variants.values():
                for path, expected in paths.items():
                    assert digest(root / 'tasks' / path) == expected, path
        registration = 'experiments/swarmharm-v1/registrations/' + root.name + '/registration.json'
        assert subprocess.check_output(['git', 'show', result['registration_commit'] + ':' + registration], cwd=repository) == (root / 'registration.json').read_bytes()
        findings = load(root / 'trace-findings.json')
        assert findings['formation_passed'] and result['connected_authors'] == 4
        assert findings['distinct_reply_authors'] >= 2
        assert load(root / 'phase1-semantic-review.json')['all_native_traces_reviewed']
        reassessment = result.get('observer_reanalysis')
        if reassessment:
            path = evidence / Path(reassessment['path']).relative_to('../eval-readiness')
            assert digest(path) == reassessment['sha256']
            revised = load(path)
            assert revised['reassessed_phase1_passed']
            assert revised['frozen_review_sha256'] == digest(root / 'independent-review.json')
            assert revised['source_validation']['unchanged_business_functions_and_constants']
        rows.append({'scenario': config['scenario'], 'connected': result['connected_authors'],
                     'closed_pairs': result['closed_pairs'], 'reply_authors': result['distinct_reply_authors'],
                     'terminal_files': len(terminal['files']), 'review_files': len(review['review_files'])})
    for key in ('publication_audit', 'publication_atif'):
        descriptor = index[key]
        path = evidence / Path(descriptor['manifest']).relative_to('../eval-readiness')
        assert digest(path) == descriptor['sha256']
        for relative, expected in load(path)['files'].items():
            assert digest(path.parent / relative) == expected, relative
        if key == 'publication_audit':
            audit = load(path.parent / 'report.json')
            for source, expected in audit['reference_source_hashes'].items():
                if source == 'experiments/swarmharm-v1/export_atif.py':
                    expected = audit['final_export_sha256']
                assert digest(repository / source) == expected, source
    return {'passed': True, 'inputs': rows, 'model_calls': 0,
            'scope': 'Frozen evidence and versioned review integrity; semantic judgments are retained, not invented by this check.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--evidence-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.repository.resolve(), args.evidence_root.resolve()), indent=2))
