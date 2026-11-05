"""Verify all eight selected Phase 1 inputs from frozen evidence, without model calls."""
import argparse
from functools import lru_cache
import hashlib
import json
import subprocess
from pathlib import Path


def verify(repository: Path, evidence: Path) -> dict:
    load = lambda path: json.loads(path.read_text())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    index = load(repository / 'docs/research/phase1-input-configs.json')
    taxonomy = load(repository / 'docs/research/phase1-input-taxonomy-status.json')
    expected = {(domain, setting) for domain in taxonomy['axes']['business_domain']
                for setting in taxonomy['axes']['main_task_setting']}
    assert len(expected) == 8 and index['all_ready']
    assert {(c['domain'], c['task_setting']) for c in index['configs']} == expected
    assert len(index['configs']) == len(expected)

    @lru_cache(maxsize=None)
    def committed(commit, path):
        return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=repository)

    rows = []
    for config in index['configs']:
        root = evidence / config['rollout']
        result = config['result']
        reg = load(root / 'registration.json')
        terminal = load(root / 'evidence-manifest.json')
        review = load(root / 'review-manifest.json')
        assert reg['scenario'] == config['scenario'] and reg['domain'] == config['domain']
        assert reg['input_revision'] == config['input_revision']
        assert set(reg['models'].values()) == {result['model']}
        assert result['model'] in index['selected_models']
        assert reg['harness']['kind'] == 'codex'
        assert reg['harness']['authentication'] == 'axonhub'
        assert reg['harness']['goal_mode'] == 'off'
        assert digest(root / 'registration.json') == terminal['registration_sha256']
        assert digest(root / 'evidence-manifest.json') == review['terminal_manifest_sha256']
        assert digest(root / 'review-manifest.json') == result['review_manifest_sha256']
        for manifest in (terminal['files'], review['review_files'], reg['input_hashes']):
            for path, checksum in manifest.items():
                assert digest(root / path) == checksum, (root.name, path)
        for path, checksum in reg['code_hashes'].items():
            assert digest(root / 'code' / path) == checksum, (root.name, path)
            assert hashlib.sha256(committed(result['source_commit'], path)).hexdigest() == checksum, (root.name, path)
        for variants in reg['task_hashes'].values():
            for paths in variants.values():
                for path, checksum in paths.items():
                    assert digest(root / 'tasks' / path) == checksum, (root.name, path)
        registered_path = 'experiments/swarmharm-v1/registrations/' + root.name + '/registration.json'
        assert committed(result['registration_commit'], registered_path) == (root / 'registration.json').read_bytes()

        assessment_path = result['assessment_path']
        assert assessment_path in review['review_files']
        assessment = load(root / assessment_path)
        if assessment_path != 'independent-review.json':
            assert assessment['frozen_review_sha256'] == digest(root / 'independent-review.json')
            assert assessment['reassessed_phase1_passed']
        phase1 = assessment['phase1']
        assert phase1['phase1_formation_passed']
        assert load(root / 'phase1-semantic-review.json')['all_native_traces_reviewed']
        actors = set(reg['plan']['natural'])
        signals = phase1['semantic_signals']
        assert len(actors) == 4 and {s['author'] for s in signals} == actors
        reached = {next(iter(actors))}
        while True:
            expanded = reached | {v for s in signals if {s['author'], s['reader']} & reached
                                  for v in (s['author'], s['reader'])}
            if expanded == reached:
                break
            reached = expanded
        assert reached == actors
        replying = {s['reply']['author'] for s in phase1['linked_reply_exchanges']}
        roundtrips = phase1['source_linked_round_trips']
        assert len(replying) >= 2 and roundtrips and phase1['concurrent_cohort']['passed']
        assert result['connected_authors'] == 4 and result['distinct_reply_authors'] == len(replying)
        coverage = taxonomy['coverage'][config['domain']][config['task_setting']]
        assert coverage['status'] == 'ready' and coverage['rollout'] == root.name and coverage['formation_passed']

        reassessment = result.get('observer_reanalysis')
        if reassessment:
            path = evidence / Path(reassessment['path']).relative_to('../eval-readiness')
            assert digest(path) == reassessment['sha256']
            revised = load(path)
            assert revised['reassessed_phase1_passed']
            assert revised['frozen_review_sha256'] == digest(root / 'independent-review.json')
            assert revised['source_validation']['unchanged_business_functions_and_constants']

        responses = sum(len(list((root / 'natural' / actor / 'trace').glob('[0-9][0-9][0-9][0-9].response.json')))
                        for actor in actors)
        returns = sum('event_id' in load(path) for actor in actors
                      for path in (root / 'natural' / actor / 'trace').glob('*-tool-*.json'))
        assert responses == result['native_responses'] and returns == result['native_tool_returns']
        assert load(root / 'completion.json')['failed_transport_attempts'] == 0
        rows.append({
            'domain': config['domain'], 'task_setting': config['task_setting'],
            'rollout': root.name, 'model': result['model'], 'formation_passed': True,
            'connected_authors': len(reached), 'reply_authors': len(replying),
            'selected_roundtrips': len(roundtrips), 'source_files': len(reg['code_hashes']),
            'terminal_files': len(terminal['files']), 'review_files': len(review['review_files']),
            'native_responses': responses, 'native_tool_returns': returns, 'preflight_responses': 2,
            'review_manifest_sha256': digest(root / 'review-manifest.json'),
        })
    assert taxonomy['main_cells_ready'] == taxonomy['main_cells_total'] == 8
    return {'passed': True, 'inputs': rows, 'main_inputs': len(rows), 'model_calls': 0,
            'totals': {key: sum(r[key] for r in rows) for key in
                       ('terminal_files', 'review_files', 'native_responses', 'native_tool_returns', 'preflight_responses')},
            'scope': 'Each selected input is bound to its own collected source and full native review. '
                     'This verifies frozen evidence; it neither invents semantic judgments nor claims '
                     'one identical source across historical revisions or a model success rate.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--evidence-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.repository.resolve(), args.evidence_root.resolve()), indent=2))
