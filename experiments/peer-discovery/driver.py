import argparse
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

import pexpect
import psutil


def receipt(directory, name, data):
    (directory / f'{name}.json').write_text(json.dumps({'time_ns': time.time_ns(), **data}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('instance_id')
    parser.add_argument('objective', type=Path)
    parser.add_argument('--deadline', type=int, required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0
    directory = Path('/var/lib/peer-operator')
    with (directory / 'launches' / args.instance_id).open('x') as marker:
        marker.write(str(time.time_ns()))
        marker.flush()
        os.fsync(marker.fileno())
    objective = args.objective.read_text().strip()
    assert 0 < len(objective) <= 4000
    environment = {'HOME': '/home/agent', 'USER': 'agent', 'LOGNAME': 'agent', 'PATH': '/usr/local/bin:/usr/bin:/bin',
        'TERM': 'xterm-256color', 'LANG': 'C.UTF-8', 'AXONHUB_API_KEY': (directory / 'inference-key').read_text().strip(),
        'CODEX_HOME': '/home/agent/.codex'}
    child = pexpect.spawn('/usr/sbin/runuser', ['-u', 'agent', '--preserve-environment', '--',
        '/usr/local/bin/codex', '--no-alt-screen', '--dangerously-bypass-approvals-and-sandbox', '-C', '/home/agent'],
        env=environment, encoding='utf-8', dimensions=(50, 160), timeout=1)
    receipt(directory, 'process-start', {'pid': child.pid, 'instance_id': args.instance_id,
        'objective_sha256': hashlib.sha256(objective.encode()).hexdigest()})
    sent = False
    completed = False
    process_recorded = False
    with (directory / 'pty.txt').open('w') as transcript:
        child.logfile_read = transcript
        try:
            while time.time() < args.deadline:
                if not process_recorded:
                    processes = [process for process in psutil.Process(child.pid).children() if process.name() == 'codex']
                    if processes:
                        process = processes[0]
                        receipt(directory, 'codex-process-start', {'pid': process.pid, 'create_time': process.create_time(), 'instance_id': args.instance_id})
                        process_recorded = True
                matched = child.expect(['\x1b\\[6n', 'trust this', 'Press enter', '›', pexpect.TIMEOUT, pexpect.EOF], timeout=1)
                if matched == 0:
                    child.send('\x1b[1;1R')
                elif matched in (1, 2) and not sent:
                    child.send('\r')
                elif matched == 3 and not sent:
                    child.send('/goal ')
                    child.send('\x1b[200~' + objective + '\x1b[201~')
                    time.sleep(0.3)
                    child.send('\r')
                    sent = True
                    receipt(directory, 'goal-submitted', {'objective': objective})
                elif matched == 5:
                    break
                databases = list(Path('/home/agent/.codex').glob('goals*.sqlite'))
                for database in databases:
                    with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
                        connection.row_factory = sqlite3.Row
                        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='thread_goals'")]
                        for table in tables:
                            assert table.replace('_', '').isalnum()
                            goals = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
                            if goals:
                                receipt(directory, 'native-goals', {'database': str(database), 'table': table, 'goals': goals})
                            for goal in goals:
                                if goal.get('status') == 'complete':
                                    completed = True
                if completed:
                    output = Path('/home/agent/discovered_peers.json')
                    if output.exists():
                        (directory / 'frozen-output.json').write_bytes(output.read_bytes())
                    receipt(directory, 'goal-complete', {})
                    break
        finally:
            child.close(force=True)
            receipt(directory, 'process-stop', {'submitted': sent, 'goal_complete': completed, 'exitstatus': child.exitstatus,
                'signalstatus': child.signalstatus})
            output = Path('/home/agent/discovered_peers.json')
            if output.exists() and not (directory / 'frozen-output.json').exists():
                (directory / 'frozen-output.json').write_bytes(output.read_bytes())


if __name__ == '__main__':
    main()
