import argparse
import hashlib
import json
from pathlib import Path

from cloud import save, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    for host in binding['hosts']:
        original = ssh(args.directory, host['public_ip'], 'sudo cat /var/lib/peer-operator/process-start.json').stdout
        result = ssh(args.directory, host['public_ip'], f'sudo python3 /opt/peer-discovery/driver.py {host["id"]} /var/lib/peer-operator/objective.txt --deadline 0', check=False)
        assert result.returncode != 0 and b'FileExistsError' in result.stderr
        assert ssh(args.directory, host['public_ip'], 'sudo cat /var/lib/peer-operator/process-start.json').stdout == original
        save(args.directory, f'{host["id"]}-invocation-guard.json', {'instance_id': host['id'],
            'duplicate_returncode': result.returncode, 'original_process_receipt_sha256': hashlib.sha256(original).hexdigest(), 'receipt_unchanged': True})
    print(json.dumps({'verified_invocation_guards': len(binding['hosts'])}))


if __name__ == '__main__':
    main()
