from pathlib import Path
import shlex
import subprocess

BASE = Path(__file__).resolve().parents[1]
REMOTE_BASE = '/home/ubuntu/swh77-operator/SWH-88'
META_KEY = '/home/cpt-llm/Playground/cpt-llm-agent-workspace/swarmharm-dd7d0eb4a945/swh-78-068357cad047/workdir/private/swh6-ed25519'


def run_remote(source, arguments):
    return subprocess.run(['ssh', '-i', META_KEY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                           'ubuntu@63.186.173.73', 'python3', '-', *map(str, arguments)],
                          input=Path(source).read_bytes(), check=True, capture_output=True)


def run_analysis(script, arguments):
    command = shlex.join(['/home/ubuntu/swh77-operator/SWH-85/analysis-venv/bin/python',
                          f'{REMOTE_BASE}/operator-code/experiments/peer-discovery/{script}', *map(str, arguments)])
    return subprocess.run(['ssh', '-i', META_KEY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                           'ubuntu@63.186.173.73', command], check=True, capture_output=True)
