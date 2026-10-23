"""One-shot launchd-owned collection and audit. No automatic restart or API retry."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(HERE.parent / 'back-office-v1'))
from durability import export, hashes, save, verify

os.chdir(ROOT)
os.environ['PATH'] = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'
out = ROOT / 'work/error-propagation-v3-runs-20261024'
backup = ROOT / 'work/backups/error-propagation-v3-runs-20261024'
receipt_path = ROOT / 'outputs/ERROR_PROPAGATION_V3_LAUNCH.json'
receipt = {'status': 'supervisor_started', 'supervisor_pid': os.getpid(), 'supervisor_parent_pid': os.getppid(),
           'supervisor_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'epoch': time.time(), 'launchd_label': 'org.ayush.swarmharm.repair.20261024',
           'automatic_restart': False, 'automatic_api_retry': False, 'planned_campaigns': 72,
           'out': str(out), 'backup': str(backup), 'legacy_results': 'preserved and reported separately'}
assert os.getppid() == 1, 'collector must be independent of the chat process'
lock = ROOT / 'work/propagation-v3-supervisor-dispatch.lock'
with lock.open('x') as file:
    file.write(json.dumps(receipt) + '\n'); file.flush(); os.fsync(file.fileno())
assert not out.exists() and not backup.exists(), 'Never restart or overwrite an existing dispatch'
save(receipt_path, receipt)
try:
    command = [sys.executable, '-u', str(HERE / 'run.py'), '--registration',
               str(ROOT / 'outputs/ERROR_PROPAGATION_V3_REGISTRATION.json'),
               '--out', str(out), '--backup', str(backup), '--jobs', '4']
    child = subprocess.Popen(command, env=os.environ.copy())
    receipt.update(status='collecting', collector_pid=child.pid)
    save(receipt_path, receipt)
    exit_code = child.wait()
    receipt.update(status='auditing', collector_exit_code=exit_code, collection_finished_epoch=time.time())
    save(receipt_path, receipt)
    environment = {k: v for k, v in os.environ.items() if k not in ('OPENROUTER_API_KEY', 'OPENAI_API_KEY')}
    checks = []
    atif = ROOT / 'work/error-propagation-v3-atif-20261024'
    results = ROOT / 'outputs/ERROR_PROPAGATION_V3_RESULTS.json'
    temporary = results.with_suffix('.pending.json')
    commands = [[sys.executable, str(HERE / 'analyze.py'), str(out), str(temporary)],
                [str(ROOT / 'work/harbor-0.24.0/bin/python'), str(HERE / 'export_atif.py'), str(out), str(atif)]]
    for command in commands:
        result = subprocess.run(command, env=environment)
        checks.append({'command': command, 'exit_code': result.returncode})
        if result.returncode != 0: raise RuntimeError('offline audit/export failed; originals preserved')
    json.loads(temporary.read_text()); os.replace(temporary, results)
    report = subprocess.run([sys.executable, str(HERE / 'report.py'), str(ROOT)], env=environment)
    assert report.returncode == 0, 'readable report failed'
    export(atif, ROOT / 'work/backups/error-propagation-v3-atif-20261024')
    backup_check = verify(out, backup)
    save(ROOT / 'outputs/ERROR_PROPAGATION_V3_EXPORT_CHECK.json', backup_check)
    metrics = json.loads(results.read_text())
    complete = sum(r.get('episode_complete', False) and r['grading_status'] == 'scored' for r in metrics['campaigns'])
    receipt.update(status='completed' if exit_code == 0 and complete == 72 and not backup_check['issues'] else 'requires_review',
                   postprocessing=checks, complete_campaigns=complete, expected_campaigns=72,
                   export_verified=not backup_check['issues'], finished_epoch=time.time())
    save(receipt_path, receipt)
except BaseException as error:
    receipt.update(status='requires_review', error_type=type(error).__name__, finished_epoch=time.time())
    save(receipt_path, receipt)
    raise
