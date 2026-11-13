"""Check only clearly historical fields in the selected initial input."""
import base64
import csv
from datetime import date
from io import StringIO
import json


def validate_files(files_by_actor, observed_on):
    """Reject recorded facts in the future; scheduled dates have different semantics."""
    count = 0
    for actor, files in files_by_actor.items():
        for path, encoded in files.items():
            if not any(path.endswith(s) for s in ('observations.csv', 'customer-corrections.csv',
                                                   'bank.csv', '-receipt.json', 'source-index.json')):
                continue
            content = base64.b64decode(encoded, validate=True).decode()
            if path.endswith('source-index.json'):
                entries = ((row.get('published_on'), 'published_on') for row in json.loads(content))
            elif path.endswith('-receipt.json'):
                entries = [(json.loads(content).get('accepted_on'), 'accepted_on')]
            else:
                entries = ((row.get(key), key) for row in csv.DictReader(StringIO(content))
                           for key in ('observed_on', 'received_on', 'posted_on'))
            for value, key in entries:
                if value:
                    count += 1
                    if date.fromisoformat(value) > observed_on:
                        raise ValueError(f'Future recorded fact: {actor} {path} {key}={value} (as of {observed_on})')
    return count
