import argparse
import concurrent.futures
import json
import threading
import time
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('key_file', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    key = json.loads(args.key_file.read_text())['key']
    barrier = threading.Barrier(2)

    def call(index, synchronize):
        if synchronize:
            barrier.wait(timeout=10)
        start = time.time_ns()
        response = requests.post('https://lmportal.iefbr14.xyz/v1/responses',
            headers={'Authorization': 'Bearer ' + key}, json={'model': 'gpt-6.1-sol',
                'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'Reply with OK.'}]}],
                'instructions': 'Reply with OK.', 'reasoning': {'effort': 'xhigh'}, 'store': False, 'stream': True}, timeout=120)
        return {'index': index, 'start_ns': start, 'end_ns': time.time_ns(), 'status': response.status_code, 'body': response.text}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda index: call(index, True), range(2)))
    records.append(call(2, False))
    args.output.write_text(json.dumps(records, indent=2))
    print(json.dumps([{key: value for key, value in record.items() if key != 'body'} for record in records]))


if __name__ == '__main__':
    main()
