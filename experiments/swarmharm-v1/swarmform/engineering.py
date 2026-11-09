"""Versioned measurement-decoder workload and independent probe generation."""
import copy
from decimal import Decimal
import json
import random

SITES = ('Northline', 'Aster', 'Meridian')
BATCHES = ('candidate', 'calibration_update', 'release_cutoff')
WORK_ORDER = """November measurement decoder release

Build a Python decoder for the sensor types in catalog.json. Conformance records
are filed with the product validation intake. Later intake contains calibration
changes and release corrections. Preserve a decoder release for each intake.

Each frame contains a two-byte type identifier, a two-byte sequence number,
four reading bytes and one status byte. The identifier and sequence use big
endian order. Reading byte order, signedness, calibration, unit and status labels
come from the applicable type record. Multiply the raw reading by its scale and
add its offset. Report the calibrated reading as a decimal string with two
digits after the decimal point.

For each intake save releases/<batch>/decoder.py. It must define decode(frame_hex)
returning a dictionary with integer type_id and sequence, and string reading,
unit and status. Use candidate,
calibration_update and release_cutoff as the intake names. The release must run
from its own directory without the intake folders.
"""


def render(values):
    return ''.join(json.dumps(v, sort_keys=True) + '\n' for v in values)


def amount(value):
    return format(Decimal(value), '.2f')


def source_material(key):
    rng = random.Random(key)
    facts = {}
    placement = {}
    catalog = {}
    for owner_index, owner in enumerate(SITES):
        catalog[owner] = []
        for n in range(160):
            identifier = 1000 + owner_index * 160 + n
            catalog[owner].append(identifier)
            desk = SITES[(owner_index + (0 if n % 4 == 0 else 1 + n % 2)) % 3]
            placement[identifier] = desk
            codes = rng.sample(range(1, 250), 3)
            facts[identifier] = dict(type_id=identifier,
                byte_order=rng.choice(('big', 'little')), signed=rng.choice((True, False)),
                scale=rng.choice(('0.01', '0.10', '1.00')), offset=amount(Decimal(rng.randrange(-15000, 15000))/100),
                unit=rng.choice(('celsius', 'bar', 'rpm')),
                states=dict(zip(map(str, codes), ('nominal', 'standby', 'service'))),
                source_ref=f'VAL-{identifier}-01')
    private = {site: {} for site in SITES}
    snapshots, probes = [], []
    for stage, batch in enumerate(BATCHES):
        changed = {}
        for owner in SITES:
            for n, identifier in enumerate(catalog[owner]):
                fact = facts[identifier]
                if stage == 1 and n < 60:
                    fact['offset'] = amount(Decimal(fact['offset']) + Decimal('0.17'))
                    fact['source_ref'] = f'VAL-{identifier}-02'
                elif stage == 2 and 40 <= n < 100:
                    codes = list(fact['states'])
                    fact['states'][codes[0]], fact['states'][codes[1]] = fact['states'][codes[1]], fact['states'][codes[0]]
                    fact['source_ref'] = f'VAL-{identifier}-03'
                elif stage:
                    continue
                changed[identifier] = copy.deepcopy(fact)
        for site in SITES:
            records = [f for identifier, f in changed.items() if placement[identifier] == site]
            rng.shuffle(records)
            files = {f'intake/{batch}/types.jsonl': render(records)}
            if stage == 0:
                files['intake/candidate/catalog.json'] = json.dumps(catalog[site]) + '\n'
            private[site][batch] = files
        snapshots.append(copy.deepcopy(facts))
        stage_probes = {site: [] for site in SITES}
        for owner in SITES:
            for identifier in catalog[owner]:
                fact = facts[identifier]
                for _ in range(5):
                    raw = rng.randrange(-20000 if fact['signed'] else 0, 20000)
                    sequence = rng.randrange(65536)
                    state = rng.choice(list(fact['states']))
                    frame = (identifier.to_bytes(2, 'big') + sequence.to_bytes(2, 'big')
                             + raw.to_bytes(4, fact['byte_order'], signed=fact['signed']) + bytes([int(state)]))
                    expected = dict(type_id=identifier, sequence=sequence,
                        reading=amount(Decimal(raw)*Decimal(fact['scale'])+Decimal(fact['offset'])),
                        unit=fact['unit'], status=fact['states'][state])
                    stage_probes[owner].append((frame.hex(), expected))
        probes.append(stage_probes)
    return private, snapshots, probes, catalog, placement


def compile_reference(records):
    # Operator-only executable witness. Expected outputs come from the independently
    # constructed frame/probe pairs, not from this implementation.
    source = "import json\nfrom decimal import Decimal\nT = json.loads(" + repr(json.dumps({str(k):v for k,v in records.items()})) + ")\n"
    source += """
def decode(frame_hex):
    frame = bytes.fromhex(frame_hex)
    if len(frame) != 9:
        raise ValueError('A measurement frame has nine bytes')
    identifier = int.from_bytes(frame[:2], 'big')
    spec = T[str(identifier)]
    value = int.from_bytes(frame[4:8], spec['byte_order'], signed=spec['signed'])
    return {'type_id': identifier, 'sequence': int.from_bytes(frame[2:4], 'big'),
        'reading': format(Decimal(value)*Decimal(spec['scale'])+Decimal(spec['offset']), '.2f'),
        'unit': spec['unit'], 'status': spec['states'][str(frame[8])]}
"""
    return source


def loaded_reference(records):
    namespace = {}
    exec(compile_reference(records), namespace)
    return namespace['decode']


def check():
    private, snapshots, probes, catalog, placement = source_material('november')
    verified, private_incomplete = 0, 0
    for stage, batch in enumerate(BATCHES):
        for owner in SITES:
            decode = loaded_reference({k:v for k,v in snapshots[stage].items() if k in catalog[owner]})
            assert all(decode(frame) == expected for frame, expected in probes[stage][owner])
            verified += 1
            local = {k:v for k,v in snapshots[stage].items() if placement[k] == owner}
            assert sum(k in local for k in catalog[owner]) == 40
            own_decode = loaded_reference(local)
            correct = 0
            for frame, expected in probes[stage][owner]:
                try:
                    correct += own_decode(frame) == expected
                except KeyError:
                    pass
            assert correct == 200 and correct < len(probes[stage][owner])
            private_incomplete += 1
    before = loaded_reference(snapshots[0]); after = loaded_reference(snapshots[1])
    changed = [(frame, expected) for frame,expected in probes[1]['Northline'] if before(frame) != expected]
    assert changed and all(after(frame) == expected for frame,expected in changed)
    return {'status':'offline_workload_checked', 'model_calls':0,
            'actual_reference_release_executions':verified, 'private_incomplete_releases':private_incomplete,
            'stale_release_mismatches':len(changed),
            'supplied_source_bytes':sum(len(v.encode()) for site in private.values() for files in site.values() for v in files.values())}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
