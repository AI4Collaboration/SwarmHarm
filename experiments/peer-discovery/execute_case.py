import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from cloud import ROOT, save


def run(directory, label, script, arguments):
    print(json.dumps({'stage': label, 'state': 'running'}), flush=True)
    with (directory / f'{label}.log').open('wb') as output:
        subprocess.run([sys.executable, str(ROOT / script), *map(str, arguments)],
                       stdout=output, stderr=subprocess.STDOUT, check=True)
    print(json.dumps({'stage': label, 'state': 'verified'}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--issue', required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    publications = directory / 'deliverables'
    publications.mkdir(exist_ok=True)
    for repeat in (1, 2, 3):
        graph = directory / f'graph-{repeat}.json'
        target = directory / f'repeat-{repeat}'
        assert shutil.disk_usage(directory).free > 12 * 2**30
        probe = directory / f'provider-admission-{repeat}'
        if not (probe / 'recording-verification.json').exists():
            run(directory, f'provider-{repeat}', 'provider_admission.py',
                [probe, '--meta-key', args.meta_key, '--label', f'repeat-{repeat}', '--issue', args.issue])
            run(directory, f'provider-recording-{repeat}', 'verify_provider_recording.py',
                [probe, '--meta-key', args.meta_key])
        assert not (target / 'cloud.json').exists()
        run(directory, f'execution-{repeat}', 'repeat.py',
            [target, graph, '--meta-key', args.meta_key, '--issue', args.issue])
        publication = publications / f'{args.issue}-repeat-{repeat}.tar.gz'
        run(directory, f'finalization-{repeat}', 'finalize_repeat.py',
            [target, graph, '--meta-key', args.meta_key, '--output', publication])
        run(directory, f'contacts-{repeat}', 'contact_audit.py',
            [target, '--output', directory / f'contacts-repeat-{repeat}.json'])
        save(directory, f'completed-repeat-{repeat}.json',
             {'repeat': repeat, 'publication': str(publication.relative_to(directory)),
              'state': 'verified'})
    save(directory, 'execution-complete.json', {'issue': args.issue, 'repeats': [1, 2, 3]})


if __name__ == '__main__':
    main()
