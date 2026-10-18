import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from cloud import ROOT, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--admission-workdir', type=Path, required=True)
    args = parser.parse_args()
    case = args.directory
    stage = case / 'case-publication'
    assert not stage.exists()
    stage.mkdir()

    def copy(source, relative):
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    for name in ('README.md', 'summary.json'):
        copy(args.report / name, name)
    for path in case.glob('*.json'):
        copy(path, Path('admission') / path.name)
    source_manifest = {}
    for path in ROOT.iterdir():
        if path.is_file() and path.suffix in ('.py', '.txt', '.sh', '.toml'):
            copy(path, Path('source') / path.name)
    shutil.copytree(case / 'stored-payloads', stage / 'admission/stored-payloads')
    secrets = []
    for repeat in range(1, 4):
        directory = case / f'repeat-{repeat}'
        audit = json.loads((directory / 'independent-audit.json').read_bytes())
        assert audit['repeat'] == repeat and audit['subjects'] == 32
        for name in ('binding.json', 'cloud.json', 'release.json', 'capacity-admission.json', 'cleanup.json',
                'evidence-verification.json', 'resource-deletion-verification.json', 'independent-audit.json',
                'scoring.json', 'metrics.json', 'recording-receipts.json', 'cloudwatch-resources.json'):
            copy(directory / name, Path(f'repeat-{repeat}') / name)
        manifest = directory / 'operator-source-manifest.json'
        if manifest.exists():
            copy(manifest, Path(f'repeat-{repeat}') / manifest.name)
            source_manifest[str(repeat)] = json.loads(manifest.read_bytes())
        probe = case / f'provider-admission-{repeat}'
        shutil.copytree(probe, stage / f'provider-admission-{repeat}')
        secrets.append(probe / 'private-key-0.json')
        secrets += list(directory.glob('private-key-*.json'))
    save(stage, 'operator-sources.json', {'initial_launch_revision': '2d4deaf1',
        'repeat_source_manifests': source_manifest})
    for number in (1, 2):
        copy(case / f'admission-preflight-{number}-cleanup.json', Path(f'shared-preflight-{number}/cleanup.json'))
    secrets += [args.admission_workdir / 'private/preflight-1-key.json',
        args.admission_workdir / 'SwarmHarm/experiments/peer-discovery/.scratch/repeat-1/private-key-0.json']
    output = case / 'deliverables/SWH-90-case-evidence.tar.gz'
    command = [sys.executable, str(ROOT / 'publish.py'), str(stage), str(output)]
    for secret in secrets:
        command += ['--secret-file', str(secret)]
    subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
