#!/usr/bin/env python3
"""Offline regrade into a NEW directory; retains the original verifier verbatim."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import hashlib
from durability import save, hashes

HERE = Path(__file__).resolve().parent


def regrade(episode, truth_path, destination):
    episode, truth_path, destination = Path(episode).resolve(), Path(truth_path).resolve(), Path(destination).resolve()
    if destination == episode or episode in destination.parents or destination in episode.parents:
        raise ValueError('regrade must be separate from the original episode')
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    original_hashes = hashes(episode)
    meta = json.loads((episode/'meta.json').read_text())
    shutil.copytree(episode/'verifier', destination/'original-verifier')
    shutil.copy2(episode/'meta.json', destination/'original-meta.json')
    scorer_path = HERE/'shared/compute_reward.py'
    spec = importlib.util.spec_from_file_location('regrade_scorer', scorer_path)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    result = {'status': 'scored', 'episode_complete': meta['stop'] == 'final_answer',
              'original_episode': str(episode), 'original_hashes': original_hashes,
              'scorer_sha256': hashlib.sha256(scorer_path.read_bytes()).hexdigest(),
              'truth_sha256': hashlib.sha256(truth_path.read_bytes()).hexdigest()}
    try:
        if meta['stop'] == 'api_error':
            result.update(status='api_error', scores=None)
        else:
            snapshot = json.loads((episode/'backoffice/state.json').read_text())
            audit = [json.loads(x) for x in (episode/'backoffice/audit.jsonl').read_text().splitlines() if x]
            truth = json.loads(truth_path.read_text())['steps']['wave-'+str(meta['wave'])]
            scores, details = scorer.score(truth, snapshot['state'], audit, snapshot['arm'])
            result.update(scores=scores, details=details)
    except Exception as e:
        result.update(status='grading_error', scores=None, error=f'{type(e).__name__}: {e}')
    if hashes(episode) != original_hashes:
        raise RuntimeError('original changed during regrade')
    save(destination/'regrade.json', result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('episode', type=Path)
    ap.add_argument('truth', type=Path)
    ap.add_argument('destination', type=Path)
    a = ap.parse_args()
    result = regrade(a.episode, a.truth, a.destination)
    print(json.dumps({k: result[k] for k in ('status', 'episode_complete')}))
    if result['status'] == 'grading_error':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
