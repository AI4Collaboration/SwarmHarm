import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

from remote import BASE


def main():
    source = BASE / 'operator-code/experiments/peer-discovery'
    native = BASE / 'native-admission/i-0bc670d5401eb31fa'
    assert (source / 'driver.py').read_bytes() == (native / 'var/lib/peer-operator/executed-driver.py').read_bytes()
    configuration = tomllib.loads((source / 'provider.toml').read_text())
    accepted = tomllib.loads((native / 'home/agent/.codex/config.toml').read_text())
    assert accepted.pop('tui') == {'screen_reader_detection_done': True}
    assert configuration == accepted
    hashes = {str(path.relative_to(BASE)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in source.iterdir() if path.is_file()}
    revision = subprocess.run(['git', '-C', str(BASE / 'repository'), 'rev-parse', 'HEAD'],
                              check=True, capture_output=True, text=True).stdout.strip()
    receipt = {'source_revision': revision, 'shared_harness': '100470a2',
               'native_admission_driver': 'byte-identical', 'native_admission_provider': 'verified', 'sha256': hashes}
    (BASE / 'source-manifest.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps({'source_revision': revision, 'native_admission_pairing': 'verified',
                      'source_files': len(hashes)}))


if __name__ == '__main__':
    main()
