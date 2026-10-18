import argparse
import json
from pathlib import Path

from recording import retrieve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    settings = json.loads((args.directory / 'recording-settings.json').read_text())
    exported = json.loads((args.directory / 'recording-gateway.json').read_text())
    report = retrieve(args.directory, settings, [exported])
    print(json.dumps({key: report[key] for key in ('requests', 'objects', 'bytes', 's3_get_requests', 's3_list_requests')}))


if __name__ == '__main__':
    main()
