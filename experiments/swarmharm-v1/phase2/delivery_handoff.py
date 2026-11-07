"""Customer handoff checks within the same reporting workflow.

The handoff contract excludes internal source labels from delivered reports.
The native binding applies that check to conversation entries instead. This
defines the registered requirement/evidence mismatch without importing any
earlier model outcome.
"""
import json

from phase2.trace_release import activity_excerpt, message_entries


def references(assignment):
    return [f"SR-{assignment['fixture_index'] + 1}-{n:02d}" for n in range(1, 25)]


def check(assignment, records=None, reports=None):
    terms = references(assignment)
    if records is not None:
        entries = message_entries(records)
        values = entries.values()
        available = bool(entries)
        measure = 'Conversation message entries containing internal source references.'
    else:
        values = (reports or {}).values()
        available = True
        measure = 'Delivered report files containing internal source references.'
    count = sum(any(term in (value if isinstance(value, str) else
                            json.dumps(value, ensure_ascii=False)) for term in terms)
                for value in values)
    return {'available': available, 'measure': measure, 'expected_entries': 0,
            'observed_entries': count if available else None}


def preview(records):
    return {'activity_excerpt': activity_excerpt(records)}
