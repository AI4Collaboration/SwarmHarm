import argparse
import concurrent.futures
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--issue', required=True)
    parser.add_argument('--n', type=int, required=True)
    parser.add_argument('--k', type=int, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--probe-key-id', required=True)
    args = parser.parse_args()
    root = Path(__file__).parent.resolve()
    directory = args.directory.resolve()
    assert directory.is_mount()
    assert shutil.disk_usage(directory).free >= 10 * 1024**3

    def run(name, arguments, log):
        with (directory / log).open('w') as stream:
            subprocess.run([sys.executable, str(root / name), *map(str, arguments)],
                           stdout=stream, stderr=subprocess.STDOUT, check=True)

    run('storage_costs.py', [directory], 's3-prices-console.txt')
    for repeat in range(1, 4):
        target = directory / f'repeat-{repeat}'
        assert not target.exists()
        assert shutil.disk_usage(directory).free >= 3 * 1024**3
        graph = directory / f'graphs/graph-{repeat}.json'
        definition = json.loads(graph.read_text())
        assert definition['n'] == args.n and definition['k'] == args.k
        run('storage_probe.py', [directory / f'storage-admission-{repeat}', '--meta-key', args.meta_key,
                                '--key-id', args.probe_key_id], f'repeat-{repeat}-storage-console.txt')
        shared = [target, graph, '--meta-key', args.meta_key]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            operator = pool.submit(run, 'repeat.py', shared + ['--issue', args.issue, '--state-dir', args.state_dir],
                                   f'repeat-{repeat}-console.txt')
            observer = pool.submit(run, 'observe.py', shared, f'repeat-{repeat}-observations-console.txt')
            operator.result()
            observer.result()
        run('finish_repeat.py', [target, graph, '--prices', directory / 's3-prices.json'],
            f'repeat-{repeat}-verification-console.txt')
        archive = directory / f'deliverables/{args.issue}-repeat-{repeat}.tar.gz'
        run('publish.py', [target, archive], f'repeat-{repeat}-publication-console.txt')
        run('verify_publication.py', [target, archive], f'repeat-{repeat}-publication-verification-console.txt')
        print(json.dumps({'repeat': repeat, 'collection_scoring_publication_cleanup': 'verified'}), flush=True)
    run('verify_case.py', [directory, '--n', args.n, '--k', args.k], 'case-verification-console.txt')


if __name__ == '__main__':
    main()
