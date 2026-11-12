#!/usr/bin/env python3
"""Prepare a separate observer-scope repair without replacing registered scores."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'swarmharm'))
sys.path.insert(0, str(REPO/'shared'))
from phase2 import claim_evidence, mechanism_inputs
from review import verify_evidence_manifest
import guardrails
import run


def scoped_inputs(packet, mechanical, contract):
    mechanism = contract['mechanism']
    criterion = contract['criterion']
    if (criterion != mechanism_inputs.MECHANISMS[mechanism]['criterion']
            or mechanical['criterion'] != criterion
            or packet['registered_claim'] != mechanism
            or packet['registered_semantic_criterion'] != criterion):
        raise ValueError('Only the original overbroad observer scope can be repaired')
    packet, mechanical = deepcopy(packet), deepcopy(mechanical)
    packet['full_mechanism_criterion'] = criterion
    packet['registered_semantic_criterion'] = mechanism_inputs.semantic_criterion(mechanism)
    mechanical['semantic_criterion'] = packet['registered_semantic_criterion']
    return packet, mechanical


def prepare(root, destination):
    root = guardrails.outside_repository(root, REPO, 'Rollout output')
    destination = guardrails.outside_repository(destination, REPO, 'Observer scope review')
    if destination.exists():
        raise FileExistsError(destination)
    manifest_sha = verify_evidence_manifest(root)
    names = ('registration.json', 'mechanism-review.json', 'transcript-judge-input.json',
             'action-monitor.json', 'independent-review.json')
    values = {name: json.loads((root/name).read_text()) for name in names}
    if values['independent-review.json']['evidence_manifest_sha256'] != manifest_sha:
        raise ValueError('Independent review is not bound to the original evidence')
    packet, mechanical = scoped_inputs(values['transcript-judge-input.json'],
        values['mechanism-review.json'], values['registration.json']['mechanism_contract'])
    destination.mkdir(parents=True)
    code_hashes = {}
    for source in run.code_paths():
        relative = source.relative_to(REPO)
        target = destination/'code'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        code_hashes[str(relative)] = claim_evidence.digest_file(target)
    for name, value in [('transcript-judge-input.json', packet),
                        ('mechanism-review.json', mechanical),
                        ('action-monitor.json', values['action-monitor.json'])]:
        (destination/name).write_text(json.dumps(value, indent=2)+'\n')
    (destination/'observer-scope-repair.json').write_text(json.dumps({
        'schema': 'mechanism-observer-scope-repair-v1', 'original_root': str(root),
        'reason': 'The blinded transcript reader was asked to verify terminal effects and '
                  'counterfactual replays absent from its packet. These remain required by '
                  'the unchanged full criterion and the independent action monitor.',
        'changed_fields': ['packet.registered_semantic_criterion',
                           'packet.full_mechanism_criterion', 'mechanical.semantic_criterion'],
        'original_sha256': {name: claim_evidence.digest_file(root/name) for name in names},
        'evidence_manifest_sha256': manifest_sha,
        'observer_code_sha256': {str(p.relative_to(REPO)): claim_evidence.digest_file(p) for p in (
            Path(__file__), REPO/'swarmharm/phase2/mechanism_inputs.py',
            REPO/'swarmharm/phase2/mechanism_review.py', REPO/'swarmharm/phase2/claim_evidence.py')},
        'sealed_code_sha256': code_hashes,
        'judge_entrypoint': 'code/swarmharm/scripts/judge_unified_transcript.py',
        'original_scores_preserved': True, 'subject_inputs_changed': False,
        'mechanical_checks_changed': False,
    }, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--review-dir', required=True, type=Path)
    args = parser.parse_args()
    prepare(args.output, args.review_dir)
