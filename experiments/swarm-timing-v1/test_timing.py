import json, random, tempfile, unittest
from pathlib import Path
from timing import (audit, cross_reads, influence, kaplan_meier, km_median,
                    load, milestones, stop_rule)


def event(i, t, actor, changes=(), matches=()):
    return {'id': i, 't': t, 'actor': actor, 'operation': 'bash',
            'result': {'status': 200}, 'shared_changes': list(changes),
            'full_body_output_matches': list(matches)}


def note(path, sha, author):
    return {'path': path, 'sha256': sha, 'author': author, 'origin': 'bash'}


def coupled(seed=1, n=40):
    """A writes; B exactly reads it 3-12 s later and writes; A reads back."""
    rng, events, i, t = random.Random(seed), [], 0, 0.0
    for k in range(n):
        t += rng.expovariate(1 / 40)
        a = note(f'/registry/cache/a{k}', f'a{k}', 'A')
        events.append(event(i := i + 1, t, 'A', [a]))
        tb = t + rng.uniform(3, 12)
        b = note(f'/registry/cache/b{k}', f'b{k}', 'B')
        events.append(event(i := i + 1, tb, 'B', [b], [a]))
        events.append(event(i := i + 1, tb + rng.uniform(3, 12), 'A', [], [b]))
    return sorted(events, key=lambda e: e['t'])


def independent(seed=2, n=40):
    rng, events = random.Random(seed), []
    for actor in ('A', 'B'):
        t = 0.0
        for k in range(n):
            t += rng.expovariate(1 / 40)
            events.append(event(0, t, actor,
                                [note(f'/registry/cache/{actor}{k}', f'{actor}{k}', actor)]))
    events.sort(key=lambda e: e['t'])
    for j, e in enumerate(events, 1):
        e['id'] = j
    return events


def edge(edges, a, b):
    return next(e for e in edges if e['from'] == a and e['to'] == b)


class Checks(unittest.TestCase):
    def test_lead_detects_known_coupling(self):
        row = edge(influence(coupled(), ['A', 'B']), 'A', 'B')
        self.assertLess(row['lead_p'], 0.01); self.assertEqual(row['exact_reads'], 40)

    def test_lead_false_alarms_near_nominal(self):
        ps = [edge(influence(independent(s), ['A', 'B']), 'A', 'B')['lead_p'] for s in range(20)]
        self.assertLessEqual(sum(p < 0.05 for p in ps), 3)

    def test_no_reads_without_exact_matches(self):
        self.assertEqual(edge(influence(independent(), ['A', 'B']), 'A', 'B')['exact_reads'], 0)

    def test_read_back_loop_needs_peer_to_read_the_new_version(self):
        m = milestones(coupled(n=3), ['A', 'B'])
        self.assertIsNotNone(m['B']['first_read_back_loop'])
        self.assertGreater(m['A']['first_peer_read'], m['B']['first_peer_read'])
        self.assertIsNone(milestones(independent(n=3), ['A', 'B'])['A']['first_read_back_loop'])

    def test_relay_ring_has_no_read_back_loop(self):
        actors, events = ['A', 'B', 'C'], []
        files = {a: note(f'/registry/cache/{a}', a, a) for a in actors}
        for i, a in enumerate(actors):
            prev = actors[i - 1]
            events.append(event(2 * i + 1, 10.0 * i, a, [files[a]],
                                [files[prev]] if i else []))
        events.append(event(7, 40.0, 'A', [], [files['C']]))
        m = milestones(events, actors)
        self.assertTrue(all(m[a]['first_peer_read'] is not None for a in actors))
        self.assertTrue(all(m[a]['first_read_back_loop'] is None for a in actors))

    def test_message_body_read_counts_once(self):
        a = note('/registry/cache/a', 'a', 'A')
        body = dict(a, exposure_kind='complete_message_body')
        later = event(3, 20.0, 'B', [], [a]); later['message_body_output_matches'] = [body]
        first = event(2, 10.0, 'B', []); first['message_body_output_matches'] = [body]
        reads = cross_reads([event(1, 0.0, 'A', [a]), first, later], ['A', 'B'])
        self.assertEqual([(r['t'], r['kind']) for r in reads], [(10.0, 'message_body')])

    def test_self_read_and_failed_write_ignored(self):
        mine = note('/registry/cache/x', 'x', 'A')
        failed = event(1, 0.0, 'A', [mine]); failed['result']['status'] = 500
        m = milestones([failed, event(2, 5.0, 'A', [], [mine])], ['A'])
        self.assertIsNone(m['A']['first_write']); self.assertIsNone(m['A']['first_peer_read'])

    def test_kaplan_meier_censoring(self):
        curve = kaplan_meier([(10, True), (20, False), (30, True), (40, False)])
        self.assertEqual(curve, [(0.0, 1.0), (10, 0.75), (30, 0.375)])
        self.assertEqual(km_median(curve), 30)

    def test_stop_rule_counts_runs_that_would_be_cut(self):
        runs = [{'span_s': 900, 'cross_reads': 3,
                 'milestones': {'A': {'first_peer_read': 400}}},
                {'span_s': 900, 'cross_reads': 0,
                 'milestones': {'A': {'first_peer_read': None}}}]
        row = {r['cutoff_s']: r for r in stop_rule(runs, (300, 480))}
        self.assertEqual(row[300]['stopped'], 2); self.assertEqual(row[300]['stopped_but_later_read'], 1)
        self.assertEqual(row[480]['stopped'], 1); self.assertEqual(row[480]['stopped_but_later_read'], 0)

    def test_both_layouts_and_untimed_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            v1 = Path(tmp, 'v1'); (v1 / 'natural').mkdir(parents=True)
            (v1 / 'natural/world.json').write_text(json.dumps({'events': [
                {'id': 1, 'actor': 'A', 'at': '2026-10-26T00:00:10Z'},
                {'id': 2, 'actor': 'A', 'at': '2026-10-26T00:00:40Z'}]}))
            (v1 / 'natural/continuation.json').write_text(json.dumps({'state': {'activation_event': 2}}))
            events, activation = load(v1)
            self.assertEqual([e['t'] for e in events], [0.0, 30.0]); self.assertEqual(activation, 2)
            v3 = Path(tmp, 'v3'); (v3 / 'trial/world').mkdir(parents=True)
            (v3 / 'trial/world/state.json').write_text(json.dumps({'events': [
                {'id': 1, 'actor': 'A', 'at': 100.0}, {'id': 2, 'actor': 'A'},
                {'id': 3, 'actor': 'A', 'at': 105.0}]}))
            events, activation = load(v3)
            self.assertEqual([e['t'] for e in events], [0.0, 0.0, 5.0]); self.assertIsNone(activation)

    def test_audit_preserves_natives_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            native = Path(tmp, 'run'); (native / 'natural').mkdir(parents=True)
            world = {'events': [dict(e, at=e['t']) for e in coupled(n=3)]}
            (native / 'natural/world.json').write_text(json.dumps(world))
            before = (native / 'natural/world.json').read_bytes()
            receipt = audit([native], Path(tmp, 'out'))
            self.assertEqual((native / 'natural/world.json').read_bytes(), before)
            self.assertEqual(receipt['runs'][0]['run'], 'run')
            self.assertNotIn(tmp, json.dumps(receipt['runs']))
            self.assertTrue(Path(tmp, 'out/preservation.json').exists())
            self.assertTrue(Path(tmp, 'out-backup').exists())
            with self.assertRaises(FileExistsError):
                audit([native], Path(tmp, 'out'))


if __name__ == '__main__':
    unittest.main()
