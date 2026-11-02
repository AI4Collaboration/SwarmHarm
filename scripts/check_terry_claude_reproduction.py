#!/usr/bin/env python3
"""Verify the seven historical sources and this branch's declared adaptation."""
import ast
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/research/terry-claude-code-reproduction.json'


def git_bytes(commit, path):
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)


def check():
    campaign = json.loads(MANIFEST.read_text())
    for row in campaign['conditions']:
        data = git_bytes(row['registration_commit'], row['original_registration'])
        assert sha256(data).hexdigest() == row['original_registration_sha256']
        for path, digest in row['original_source_hashes'].items():
            assert sha256(git_bytes(row['registration_commit'], path)).hexdigest() == digest, path
    # This first adaptation is based on r190. Later condition branches must
    # explicitly select their own original registration before using this audit.
    selected = next(row for row in campaign['conditions'] if row['condition'] == campaign.get('current_condition', 'r190'))
    relative = 'experiments/swarmharm-v1/phase2/trace_release.py'
    original = git_bytes(selected['registration_commit'], relative).decode()
    adapted = (ROOT / relative).read_text()
    adapted = adapted.replace('from phase2.native_messages import conversation_row\n', '')
    adapted = adapted.replace('conversation_row(json.loads(line))', 'json.loads(line)')
    adapted = adapted.replace('/tmp/agent/.claude/sessions', '/tmp/agent/.pi/sessions')
    adapted = adapted.replace("'conversation_entry_type':'user or assistant'", "'conversation_entry_type':'message'")
    assert ast.dump(ast.parse(original)) == ast.dump(ast.parse(adapted)), 'Undeclared business/scorer source change'
    print(json.dumps({'verified_conditions': len(campaign['conditions']),
        'current_condition': selected['condition'], 'business_source_equivalent': True,
        'allowed_source_changes': ['native message decoding', 'supplied method path/schema'],
        'inference_calls': 0}))


if __name__ == '__main__':
    check()
