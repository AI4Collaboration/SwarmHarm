"""Identify the embedded figure in an offline survey report using the drawing office originals."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from field_reader import Images, selected_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('booking', choices=('north', 'crossing', 'harbor'))
    parser.add_argument('--report-version', type=int)
    args = parser.parse_args()
    name = f'reports/{args.booking}.html'
    pins = {} if args.report_version is None else {name: args.report_version}
    with selected_inputs((name,), pins) as root:
        html = (root / name).read_bytes()
    images = Images()
    images.feed(html.decode())
    prefix = 'data:image/svg+xml;base64,'
    if len(images.sources) != 1 or not images.sources[0].startswith(prefix):
        raise ValueError('Expected one embedded calibration diagram')
    embedded = base64.b64decode(images.sources[0][len(prefix):], validate=True)
    originals = Path('/workspace/bookings') / args.booking
    matches = [edition for edition in ('A', 'B')
               if (originals / edition / 'calibration.svg').is_file()
               and (originals / edition / 'calibration.svg').read_bytes() == embedded]
    print(json.dumps({'booking': args.booking, 'report_sha256': hashlib.sha256(html).hexdigest(),
                      'matching_local_editions': matches}))
    return 0 if matches else 1



if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except ValueError as error:
        raise SystemExit(str(error))
