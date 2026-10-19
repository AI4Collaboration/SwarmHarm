import json
import sqlite3


def subject_state(directory, instance_id):
    root = directory / instance_id / 'var/lib/peer-operator'
    stop_path = root / 'process-stop.json'
    stop = json.loads(stop_path.read_text()) if stop_path.exists() else None
    submitted = json.loads((root / 'goal-submitted.json').read_text())
    objective = (root / 'objective.txt').read_text().strip()
    assert submitted['objective'] == objective
    if stop is not None:
        assert stop['submitted']
    else:
        journal = (directory / f'{instance_id}-resource-end.txt').read_text()
        assert ('Stopping peer-subject.service - Peer discovery subject...' in journal
                or 'Stopped peer-subject.service - Peer discovery subject.' in journal), instance_id
        assert f"File exists: '/var/lib/peer-operator/launches/{instance_id}'" in journal
        guard = json.loads((directory / f'{instance_id}-invocation-guard.json').read_text())
        assert guard['receipt_unchanged'] and guard['duplicate_marker_verified']
    paths = list((directory / instance_id / 'home/agent/.codex/sessions').rglob('*.jsonl'))
    goal_path = root / 'native-goals.json'
    if goal_path.exists():
        goals = json.loads(goal_path.read_text())['goals']
        assert len(goals) == len(paths) == 1 and goals[0]['objective'] == objective
        metadata = [json.loads(line)['payload'] for line in paths[0].read_bytes().splitlines()
                    if json.loads(line)['type'] == 'session_meta']
        assert len(metadata) == 1 and metadata[0]['id'] == goals[0]['thread_id']
        return {'state': 'goal_accepted', 'goal': goals[0], 'sessions': paths,
                'process_stop': stop, 'service_interruption': stop is None}
    transcript = (root / 'pty.txt').read_bytes()
    assert paths == []
    if stop is not None:
        assert stop['goal_complete'] is False
    if stop is None:
        assert b'Waiting for startup' in transcript
        diagnostic = 'feature_discovery' if b'Cannot use the background server' in transcript else 'service_stop_during_startup'
        state_name = 'service_interrupted_before_goal'
    elif b'Error: app server did not become ready on ' in transcript:
        assert b'Unsent draft:' in transcript and stop is not None and stop['exitstatus'] == 1
        diagnostic = 'app_server_readiness'
        state_name = 'startup_timeout'
    else:
        assert b'Cannot use the background server' in transcript and b'Waiting for startup' in transcript
        assert stop is None or stop['signalstatus'] in (1, 9)
        diagnostic = 'feature_discovery'
        state_name = 'startup_timeout'
    assert b'/goal ' + objective.splitlines()[0].encode() in transcript
    database = directory / instance_id / 'home/agent/.codex/goals_1.sqlite'
    if database.exists():
        with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'thread_goals' in tables:
                assert connection.execute('SELECT COUNT(*) FROM thread_goals').fetchone()[0] == 0
    return {'state': state_name, 'startup_diagnostic': diagnostic, 'goal': None, 'sessions': paths,
            'process_stop': stop, 'service_interruption': stop is None}
