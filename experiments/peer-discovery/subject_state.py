import json
import sqlite3


def subject_state(directory, instance_id):
    root = directory / instance_id / 'var/lib/peer-operator'
    stop = json.loads((root / 'process-stop.json').read_text())
    submitted = json.loads((root / 'goal-submitted.json').read_text())
    objective = (root / 'objective.txt').read_text().strip()
    assert submitted['objective'] == objective and stop['submitted']
    paths = list((directory / instance_id / 'home/agent/.codex/sessions').rglob('*.jsonl'))
    goal_path = root / 'native-goals.json'
    if goal_path.exists():
        goals = json.loads(goal_path.read_text())['goals']
        assert len(goals) == len(paths) == 1 and goals[0]['objective'] == objective
        metadata = [json.loads(line)['payload'] for line in paths[0].read_bytes().splitlines()
                    if json.loads(line)['type'] == 'session_meta']
        assert len(metadata) == 1 and metadata[0]['id'] == goals[0]['thread_id']
        return {'state': 'goal_accepted', 'goal': goals[0], 'sessions': paths}
    transcript = (root / 'pty.txt').read_bytes()
    assert paths == [] and stop['goal_complete'] is False
    if b'Error: app server did not become ready on ' in transcript:
        assert b'Unsent draft:' in transcript and stop['exitstatus'] == 1
        diagnostic = 'app_server_readiness'
    else:
        assert b'Cannot use the background server' in transcript and b'Waiting for startup' in transcript
        assert stop['signalstatus'] == 1
        diagnostic = 'feature_discovery'
    assert b'/goal ' + objective.splitlines()[0].encode() in transcript
    database = directory / instance_id / 'home/agent/.codex/goals_1.sqlite'
    if database.exists():
        with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'thread_goals' in tables:
                assert connection.execute('SELECT COUNT(*) FROM thread_goals').fetchone()[0] == 0
    return {'state': 'startup_timeout', 'startup_diagnostic': diagnostic, 'goal': None, 'sessions': paths}
