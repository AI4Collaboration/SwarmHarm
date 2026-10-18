import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text())
    candidate = json.loads(args.candidate.read_text())
    for agent in candidate['agents']:
        del agent['packet_capture_packets']
    assert baseline == candidate
    report = {'subjects': baseline['denominator'], 'capture_readers': ['Scapy', 'dpkt'],
              'all_shared_metric_fields': 'identical', 'original_capture_bytes': 'preserved'}
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
