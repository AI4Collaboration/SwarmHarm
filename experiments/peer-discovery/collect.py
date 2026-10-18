import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

import psutil


directory = Path('/var/lib/peer-operator')
paths = [Path('/home/agent/discovered_peers.json'), Path('/home/agent/peers.txt'),
    Path('/home/agent/.codex/config.toml'), Path('/opt/peer-discovery/driver.py'), directory / 'objective.txt', directory / 'frozen-output.json']
files = {}
for path in paths:
    if path.exists():
        stat = path.stat()
        files[str(path)] = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'ctime_ns': stat.st_ctime_ns,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
shutil.copyfile('/opt/peer-discovery/driver.py', directory / 'executed-driver.py')
shutil.copyfile('/opt/peer-discovery/dist/registry.json', directory / 'codex-distribution.json')
record = {'time_ns': time.time_ns(), 'files': files, 'launch_markers': sorted(path.name for path in (directory / 'launches').iterdir()),
    'memory': psutil.virtual_memory()._asdict(), 'disk': psutil.disk_usage('/')._asdict(),
    'network': psutil.net_io_counters()._asdict()}
(directory / 'collection-receipt.json').write_text(json.dumps(record, indent=2))
(directory / 'traffic-journal.txt').write_bytes(subprocess.run(
    ['journalctl', '-u', 'peer-traffic.service', '--no-pager'], check=True, capture_output=True).stdout)
(directory / 'packages.txt').write_bytes(subprocess.run(
    ['dpkg-query', '-W', 'python3', 'python3-pexpect', 'python3-requests', 'python3-psutil',
     'chrony', 'curl', 'openssh-server', 'tcpdump', 'iproute2', 'iputils-ping', 'dnsutils', 'netcat-openbsd', 'jq'],
    check=True, capture_output=True).stdout)
print(json.dumps({'files': len(files), 'launch_markers': record['launch_markers']}))
