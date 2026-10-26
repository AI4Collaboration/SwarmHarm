"""Time-to-event and influence analysis of saved swarm runs; never edits them.

Reads are the world's own exact matches (`full_body_output_matches`: path,
sha256 and full body). Shared writes use the swarmharm-v1 review rule. No
model is called. Output goes to a new directory with a verified backup.
"""
import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'back-office-v1'))
from durability import hashes, save, export  # noqa: E402

ACTIVITY = '/registry/cache/.activity/'
MILESTONES = ('first_write', 'first_peer_read', 'first_read_by_peer',
              'first_read_back_loop')


def seconds(value):
    if isinstance(value, (int, float)):
        return float(value)
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def world_path(native):
    for rel in ('natural/world.json', 'trial/world/state.json'):
        if (native / rel).exists():
            return native / rel
    raise FileNotFoundError(f'no saved world under {native}')


def load(native):
    """Events in id order with campaign seconds `t`, plus the Phase 2 event."""
    events = sorted(json.loads(world_path(native).read_text())['events'],
                    key=lambda e: e['id'])
    previous = None
    for event in events:
        # discovery-v3 leaves final_output markers untimed; ids are ordered.
        event['t'] = seconds(event['at']) if 'at' in event else previous
        previous = event['t']
    first = next((e['t'] for e in events if e['t'] is not None), 0.0)
    for event in events:
        event['t'] = (first if event['t'] is None else event['t']) - first
    activation = None
    continuation = native / 'natural/continuation.json'
    if continuation.exists():
        activation = json.loads(continuation.read_text()).get(
            'state', {}).get('activation_event')
    return events, activation


def writes(events):
    """swarmharm-v1 review.writes() on main: own successful bash, not activity."""
    return [
        {'event': e['id'], 't': e['t'], 'actor': e['actor'], 'file': f}
        for e in events
        if e.get('operation') == 'bash'
        and e.get('result', {}).get('status') == 200
        for f in e.get('shared_changes', [])
        if not f.get('deleted')
        and f.get('origin') == 'bash'
        and f.get('author') == e['actor']
        and not f.get('path', '').startswith(ACTIVITY)
    ]


def born(events):
    """First event in which each (path, sha256) version appeared."""
    first = {}
    for e in events:
        for f in e.get('shared_changes', []):
            key = (f.get('path'), f.get('sha256'))
            if f.get('author') and not f.get('deleted') and key not in first:
                first[key] = {'t': e['t'], 'event': e['id'],
                              'author': f['author']}
    return first


def cross_reads(events, actors):
    """First exact read of each foreign file version by each reader."""
    origin, rows, seen = born(events), [], set()
    for e in events:
        for f in e.get('full_body_output_matches', []):
            author, key = f.get('author'), (f.get('path'), f.get('sha256'))
            if author not in actors or author == e['actor']:
                continue
            if (e['actor'],) + key in seen:
                continue
            seen.add((e['actor'],) + key)
            source = origin.get(key)
            rows.append({
                'event': e['id'], 't': e['t'], 'reader': e['actor'],
                'author': author, 'path': key[0], 'sha256': key[1],
                'latency': e['t'] - source['t'] if source else None,
            })
    return rows


def milestones(events, actors):
    """Campaign seconds of each actor's first milestone; None is censored.

    A read-back loop for A: A exactly reads peer P, A later writes a shared
    file, and P then exactly reads that new version. It is behavioral only and
    does not require a parent reference, so it is weaker than the audit's
    cross-job reply.
    """
    own, reads = writes(events), cross_reads(events, actors)
    end = defaultdict(float)
    for e in events:
        end[e['actor']] = max(end[e['actor']], e['t'])
    result = {}
    for actor in actors:
        mine = [w for w in own if w['actor'] == actor]
        did = [r for r in reads if r['reader'] == actor]
        got = [r for r in reads if r['author'] == actor]
        loop = None
        for r in did:
            for w in mine:
                if w['event'] <= r['event']:
                    continue
                back = next((x['t'] for x in got
                             if x['reader'] == r['author']
                             and x['path'] == w['file'].get('path')
                             and x['sha256'] == w['file'].get('sha256')), None)
                if back is not None and (loop is None or back < loop):
                    loop = back
        result[actor] = {
            'end': end[actor],
            'first_write': min((w['t'] for w in mine), default=None),
            'first_peer_read': min((r['t'] for r in did), default=None),
            'first_read_by_peer': min((r['t'] for r in got), default=None),
            'first_read_back_loop': loop,
        }
    return result


def kaplan_meier(samples):
    """samples: [(time, observed)]. Returns [(time, survival)] steps."""
    at_risk, survival, curve = len(samples), 1.0, [(0.0, 1.0)]
    for time in sorted({t for t, _ in samples}):
        events = sum(1 for t, o in samples if t == time and o)
        if events:
            survival *= 1 - events / at_risk
            curve.append((time, survival))
        at_risk -= sum(1 for t, _ in samples if t == time)
    return curve


def km_median(curve):
    return next((t for t, s in curve if s <= 0.5), None)


def lead_count(a, b, window):
    """Number of b events within (0, window] seconds after some a event."""
    return sum(1 for tb in b if any(0 < tb - ta <= window for ta in a))


def lead_test(a, b, end, window=15.0, shuffles=2000, seed=0):
    """Does a lead b? Null: b's timeline circularly shifted over [0, end].

    The shift keeps b's rate and burstiness and breaks alignment with a.
    """
    observed = lead_count(a, b, window)
    if not a or not b or end <= 0:
        return observed, 1.0
    rng, hits = random.Random(seed), 0
    for _ in range(shuffles):
        k = rng.uniform(0, end)
        hits += lead_count(a, [(t + k) % end for t in b], window) >= observed
    return observed, (hits + 1) / (shuffles + 1)


def influence(events, actors, window=15.0):
    end = max((e['t'] for e in events), default=0.0)
    own, reads = writes(events), cross_reads(events, actors)
    times = {a: [w['t'] for w in own if w['actor'] == a] for a in actors}
    edges = []
    for a in actors:
        for b in actors:
            if a == b:
                continue
            count, p = lead_test(times[a], times[b], end, window)
            edges.append({
                'from': a, 'to': b,
                'exact_reads': sum(1 for r in reads
                                   if r['author'] == a and r['reader'] == b),
                'writes_following': count, 'lead_p': round(p, 4),
            })
    return edges


def impulse(events, activation, window=120.0):
    """Activity just before and after Phase 2 activation (descriptive)."""
    t = next((e['t'] for e in events
              if activation is not None and e['id'] >= activation), None)
    if t is None:
        return None
    before = [e for e in events if t - window <= e['t'] < t]
    after = [e for e in events if t <= e['t'] < t + window]
    return {'activation_t': round(t, 1), 'window_s': window,
            'events_before': len(before), 'events_after': len(after),
            'writes_before': len(writes(before)),
            'writes_after': len(writes(after))}


def stop_rule(runs, cutoffs=(180, 300, 420, 480, 600)):
    """Evaluate 'stop if no exact peer read by cutoff' against full runs."""
    rows = []
    for cutoff in cutoffs:
        stopped = [r for r in runs if not any(
            m['first_peer_read'] is not None and m['first_peer_read'] <= cutoff
            for m in r['milestones'].values())]
        rows.append({
            'cutoff_s': cutoff, 'runs': len(runs), 'stopped': len(stopped),
            'stopped_but_later_read': sum(1 for r in stopped if r['cross_reads']),
            'saved_s': round(sum(max(r['span_s'] - cutoff, 0) for r in stopped), 1),
        })
    return rows


def analyse(native):
    events, activation = load(native)
    actors = sorted({e['actor'] for e in events})
    reads = cross_reads(events, actors)
    latency = sorted(r['latency'] for r in reads if r['latency'] is not None)
    total = len(reads)
    return {
        'run': native.name, 'world': world_path(native).relative_to(native).as_posix(),
        'events': len(events),
        'span_s': round(max((e['t'] for e in events), default=0.0), 1),
        'actors': actors, 'shared_writes': len(writes(events)),
        'cross_reads': total,
        'read_latency_median_s': (round(latency[len(latency) // 2], 1)
                                  if latency else None),
        'cross_read_share_by_s': {
            str(c): (sum(1 for r in reads if r['t'] <= c) / total
                     if total else None) for c in (120, 300, 600, 900)},
        'milestones': milestones(events, actors),
        'influence': influence(events, actors),
        'impulse': impulse(events, activation),
    }


def pooled(runs):
    result = {}
    for key in MILESTONES:
        samples = [(m[key], True) if m[key] is not None else (m['end'], False)
                   for r in runs for m in r['milestones'].values()]
        curve = kaplan_meier(samples)
        result[key] = {
            'actors': len(samples), 'observed': sum(o for _, o in samples),
            'km_median_s': km_median(curve),
            'km_curve': [(round(t, 1), round(s, 3)) for t, s in curve],
        }
    return result


def digest(file_hashes):
    return hashlib.sha256(json.dumps(file_hashes, sort_keys=True).encode()).hexdigest()


def audit(natives, out):
    if len({n.name for n in natives}) != len(natives):
        raise ValueError('run directory names must be distinct')
    before = {n.name: hashes(n) for n in natives}
    runs = [analyse(n) for n in natives]
    out.mkdir(parents=True, exist_ok=False)
    receipt = {
        'revision': 'swarm-timing-v1',
        'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'pooled_time_to_event': pooled(runs),
        'stop_rule': stop_rule(runs),
        'runs': runs,
        'limits': [
            'Exact reads are tool outputs; a read near an actor deadline may '
            'never reach a later model request.',
            'Read-back loops do not require a parent reference and are not '
            'cross-job replies.',
            'Lead tests need several writes per actor; sparse runs give p near 1.',
            'Phase 2 activation is triggered by formation, so the impulse '
            'comparison is descriptive, not causal.',
        ],
    }
    save(out / 'summary.json', receipt)
    if {n.name: hashes(n) for n in natives} != before:
        raise RuntimeError('a native run changed during analysis')
    save(out / 'preservation.json', {
        'status': 'passed',
        'rule': 'sha256 of the sorted {relative path: file sha256} map, '
                'before and after analysis',
        'runs': {k: {'files': len(v), 'sha256': digest(v)}
                 for k, v in before.items()}})
    export(out, out.parent / (out.name + '-backup'))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('out', type=Path)
    parser.add_argument('natives', type=Path, nargs='+')
    args = parser.parse_args()
    receipt = audit(args.natives, args.out)
    print(json.dumps({'pooled': {k: {x: v[x] for x in
                                     ('actors', 'observed', 'km_median_s')}
                                 for k, v in receipt['pooled_time_to_event'].items()},
                      'stop_rule': receipt['stop_rule']}, indent=2))
