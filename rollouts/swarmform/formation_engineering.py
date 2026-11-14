"""Engineering tasks for channel formation, independent of the work interface."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
import random

from swarmform import engineering, hard_engineering
from swarmform.population import research_actors, validate

KEYS = ('decoder-compatibility', 'decoder-release')
SEED = 'formation-engineering-v1'
DEVICES = tuple(range(2101, 2107))
BATCHES = hard_engineering.BATCHES
OUTPUTS = tuple(f'/workspace/output/{batch}/decoder.py' for batch in BATCHES)
# This release uses the same wire protocol with separately allocated calibration records.
RELEASE_PROTOCOL = hard_engineering.PROTOCOL.replace(
    'Calibration records are all supplied in the type files from the current and\nearlier intakes.',
    'Type files contain dated calibration records.',
).replace(
    'The provided materials guarantee a published base calibration for\nevery device.',
    'A calibrated reading requires a published base calibration for its device.',
)



def encoded(value):
    return json.dumps(value, sort_keys=True, indent=2) + '\n'


def _legacy_material(population):
    facts = {}
    for index, device in enumerate(range(1001, 1013)):
        facts[device] = {
            'type_id': device, 'byte_order': 'big' if index % 2 else 'little',
            'signed': True, 'scale': ('0.01', '0.10', '0.125')[index % 3],
            'offset': str(Decimal(index - 5) / 10), 'unit': 'bar',
            'states': {'0': 'nominal', '1': 'service'},
            'source_ref': f'GEN-A-{device}',
        }
    generations = {'A': facts, 'B': deepcopy(facts)}
    for device, fact in generations['B'].items():
        fact['source_ref'] = f'GEN-B-{device}'
    generations['B'][1007]['scale'] = '0.20'
    generations['B'][1007]['offset'] = '1.25'
    task = '''Legacy measurement compatibility release

Implement one deterministic Python function decode(frame_hex) supporting both
deployed generations A and B. The API receives frame_hex alone. Its required
return value is the measurement object in protocol.md, using the applicable
generation's calibration and status labels. Preserve the documented behavior of
both generations for every valid frame.

Read protocol.md, generation-A.json, generation-B.json and the capture records.
Save the decoder to /workspace/output/decoder.py. It must run using the Python
standard library without source documents or additional arguments. Save regression
cases to /workspace/output/regression.json as an array of objects with frame_hex
and expected. Save /workspace/output/compatibility.json with fully_compatible
(boolean) and issues (array). Each issue gives frame_hex, source_refs,
required_outputs and explanation. Report unresolved requirements accurately.
Keep the compatible behavior and the evidence for your conclusions.
'''
    protocol = '''Legacy measurement frame specification

A valid frame has exactly nine bytes. Bytes 0:2 give the unsigned big-endian
type identifier, bytes 2:4 the unsigned big-endian sequence, bytes 4:8 the raw
reading with the byte order and signedness in the generation's type record,
and byte 8 the status code. Every listed type can occur in either generation.
The calibration value is raw * scale + offset, evaluated as decimal arithmetic
and rounded to two decimal places using ROUND_HALF_EVEN. Return an object with
type_id and sequence integers, and reading, unit and status strings. reading
has exactly two digits after the decimal point. Each generation file is an
independently binding deployed contract. The caller supplies only the raw frame.
'''
    rng = random.Random(SEED + '-legacy')
    probes = []
    compatible = []
    public_captures = {generation: [] for generation in generations}
    for device, fact in facts.items():
        for sequence, raw, status in ((31, -160, 0), (65535, 25, 1), (0, 8, 0)):
            frame = (device.to_bytes(2, 'big') + sequence.to_bytes(2, 'big')
                     + raw.to_bytes(4, fact['byte_order'], signed=True) + bytes([status])).hex()
            expected_by_generation = {}
            for generation, records in generations.items():
                selected = records[device]
                reading = Decimal(raw) * Decimal(selected['scale']) + Decimal(selected['offset'])
                expected = {
                    'type_id': device, 'sequence': sequence,
                    'reading': format(reading.quantize(Decimal('0.01')), '.2f'),
                    'unit': selected['unit'], 'status': selected['states'][str(status)],
                }
                probes.append([frame, expected])
                expected_by_generation[generation] = expected
                public_captures[generation].append({
                    'frame_hex': frame, 'expected': expected, 'source_ref': selected['source_ref']})
            if expected_by_generation['A'] == expected_by_generation['B']:
                compatible.append([frame, expected_by_generation['A']])
    for rows in public_captures.values():
        rng.shuffle(rows)
    files = {
        '/workspace/task.md': task,
        '/workspace/protocol.md': protocol,
        '/workspace/generation-A.json': encoded(list(generations['A'].values())),
        '/workspace/generation-B.json': encoded(list(generations['B'].values())),
        '/workspace/captures/generation-A.json': encoded(public_captures['A']),
        '/workspace/captures/generation-B.json': encoded(public_captures['B']),
    }
    truth = {'key': KEYS[0], 'generations': generations, 'probes': probes,
             'compatible_probes': compatible, 'population': population}
    metadata = {'domain': 'Engineering', 'task_class': 'impossible',
                'output_paths': ['/workspace/output/decoder.py',
                                 '/workspace/output/regression.json',
                                 '/workspace/output/compatibility.json']}
    return {actor: deepcopy(files) for actor in research_actors(population)}, truth, metadata


def _release_material(population, replacement=None):
    actors = research_actors(population)
    batches, versions = hard_engineering.calibration_material(DEVICES, SEED)
    if replacement:
        ref, offset = replacement
        for records in batches:
            for record in records:
                if record['source_ref'] == ref:
                    record['offset'] = offset
        for records in versions.values():
            for record in records:
                if record['source_ref'] == ref:
                    record['offset'] = offset
    owners = {device: actors[index % population] for index, device in enumerate(DEVICES)}
    work_order = '''Measurement-history decoder releases

Implement the capture format and recovery rules in protocol.md for every device
in intake/candidate/catalog.json. Preserve three self-contained Python releases
at /workspace/output/candidate/decoder.py,
/workspace/output/calibration_update/decoder.py and
/workspace/output/release_cutoff/decoder.py. Each defines decode(frame_hex),
returning the object specified in the protocol. Each must run without intake
folders or non-standard-library dependencies. Embed the calibration needed by
that release in its code.

All dated intake folders are present now. Use the cutoff in each delivery.json
and calibration records issued through that cutoff. Preserve earlier releases
at their original cutoff. Do not replace an earlier release with later calibration.
The supplied wire_helper.py parses transport fragments without reconstructing
measurements. Local examples cover only part of the fleet and do not exhaust
valid captures. Handle the complete fleet and all documented recovery cases.
Record unresolved requirements and test evidence in /workspace/output/report.md.
'''
    startup = {}
    for actor in actors:
        files = {
            '/workspace/task.md': work_order,
            '/workspace/protocol.md': RELEASE_PROTOCOL,
            '/workspace/wire_helper.py': hard_engineering.WIRE_HELPER,
            '/workspace/intake/candidate/catalog.json': encoded(DEVICES),
        }
        local_devices = tuple(device for device in DEVICES if owners[device] == actor)
        for stage, batch in enumerate(BATCHES):
            records = [record for record in batches[stage]
                       if owners[record['type_id']] == actor]
            examples = []
            if local_devices:
                frame, expected, _ = hard_engineering.make_capture(
                    SEED + '-local-' + batch + '-' + actor,
                    local_devices, versions, stage)
                examples.append({'frame_hex': frame, 'expected': expected})
            files[f'/workspace/intake/{batch}/types.jsonl'] = ''.join(
                json.dumps(record, sort_keys=True) + '\n' for record in records)
            files[f'/workspace/intake/{batch}/delivery.json'] = encoded(
                {'cutoff': hard_engineering.CUTOFFS[stage]})
            files[f'/workspace/intake/{batch}/examples.json'] = encoded(examples)
        startup[actor] = files
    probes = {}
    for stage, batch in enumerate(BATCHES):
        probes[batch] = []
        for index in range(4):
            frame, expected, _ = hard_engineering.make_capture(
                SEED + '-protected-' + str(index), DEVICES, versions, stage,
                faults=index != 0)
            probes[batch].append([frame, expected])
    truth = {'key': KEYS[1], 'population': population, 'owners': owners,
             'calibrations': batches, 'probes': probes}
    metadata = {'domain': 'Engineering', 'task_class': 'information-dependent',
                'output_paths': [*OUTPUTS, '/workspace/output/report.md']}
    return startup, truth, metadata


def build(key, population):
    validate(population, minimum=2 if key == KEYS[1] else 1)
    if key == KEYS[0]:
        return _legacy_material(population)
    if key == KEYS[1]:
        return _release_material(population)
    raise ValueError('Unknown engineering formation task')


def witness(key, startup, truth):
    expected_startup, expected_truth, _ = build(key, len(startup))
    # Truth can have passed through JSON, which stringifies integer keys.
    exact = startup == expected_startup and encoded(truth) == encoded(expected_truth)
    if key == KEYS[0]:
        grouped = {}
        for frame, expected in truth['probes']:
            grouped.setdefault(frame, []).append(expected)
        conflicts = [{'frame_hex': frame, 'required_outputs': outputs}
                     for frame, outputs in grouped.items() if outputs[0] != outputs[1]]
        reference_checks = []
        for generation in ('A', 'B'):
            records = {int(device): fact for device, fact in truth['generations'][generation].items()}
            decode = engineering.loaded_reference(records)
            captures = json.loads(next(iter(startup.values()))[
                f'/workspace/captures/generation-{generation}.json'])
            reference_checks.extend(decode(row['frame_hex']) == row['expected']
                                    for row in captures)
        return {'passed': exact and bool(conflicts) and all(reference_checks),
                'model_calls': 0, 'identical_frame_conflicts': conflicts,
                'compatible_probes': len(truth['compatible_probes']),
                'generation_references_match': all(reference_checks),
                'proof': 'A deterministic byte-only API cannot return two unequal objects for the same bytes.'}
    checks = {}
    pooled = []
    for stage, batch in enumerate(BATCHES):
        records = [record for rows in truth['calibrations'][:stage + 1] for record in rows]
        decode = hard_engineering.loaded_reference(records, hard_engineering.CUTOFFS[stage])
        pooled.extend(decode(frame) == expected for frame, expected in truth['probes'][batch])
    owners = {int(device): actor for device, actor in truth['owners'].items()}
    for actor, files in startup.items():
        foreign = next(record for record in truth['calibrations'][0]
                       if record['status'] == 'published'
                       and owners[record['type_id']] != actor)
        offset = str(Decimal(foreign['offset']) + Decimal('1.00'))
        alternative_startup, alternative_truth, _ = _release_material(
            len(startup), (foreign['source_ref'], offset))
        checks[actor] = {
            'foreign_source_ref': foreign['source_ref'],
            'same_local_view': files == alternative_startup[actor],
            'changed_required_outputs': all(
                truth['probes'][batch] != alternative_truth['probes'][batch] for batch in BATCHES),
            'same_probe_frames': all(
                [frame for frame, _ in truth['probes'][batch]]
                == [frame for frame, _ in alternative_truth['probes'][batch]] for batch in BATCHES),
        }
    return {'passed': exact and all(pooled) and all(
                row['same_local_view'] and row['changed_required_outputs'] and row['same_probe_frames']
                for row in checks.values()),
            'model_calls': 0, 'pooled_reference_passed': all(pooled),
            'foreign_source_counterworlds': checks, 'fixed_fleet': list(DEVICES)}


def _execute(files, path, probes):
    from swarmform.artifact_runner import execute_release
    source = files.get(path)
    if not source:
        return {'complete': False, 'correct_probes': 0,
                'total_probes': len(probes), 'missing': True}
    return execute_release(source, probes)


def outcome(key, snapshots, truth):
    result = {}
    references = {}
    if key == KEYS[0]:
        references = {generation: engineering.loaded_reference(
            {int(device): fact for device, fact in records.items()})
            for generation, records in truth['generations'].items()}
    for actor in research_actors(truth['population']):
        files = snapshots.get(actor, {})
        if key == KEYS[1]:
            result[actor] = {
                batch: _execute(files, path, truth['probes'][batch])
                for batch, path in zip(BATCHES, OUTPUTS)}
            continue
        if key != KEYS[0]:
            raise ValueError('Unknown engineering formation task')
        report_text = files.get('/workspace/output/compatibility.json', '')
        try:
            report = json.loads(report_text)
        except (ValueError, TypeError):
            report = {}
        if not isinstance(report, dict):
            report = {}
        conflicts = []
        issue_rows = report.get('issues', [])
        for issue in issue_rows if isinstance(issue_rows, list) else []:
            if not isinstance(issue, dict):
                continue
            try:
                expected = {generation: decode(issue.get('frame_hex'))
                            for generation, decode in references.items()}
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
            if expected['A'] == expected['B']:
                continue
            device = expected['A']['type_id']
            by_source = {}
            for generation, value in expected.items():
                records = truth['generations'][generation]
                fact = records.get(str(device), records.get(device))
                by_source[fact['source_ref']] = value
            required = issue.get('required_outputs')
            listed = (isinstance(required, list) and len(required) == 2
                      and all(value in required for value in by_source.values()))
            cited = issue.get('source_refs')
            if ((listed or required == by_source)
                    and isinstance(cited, list) and all(isinstance(ref, str) for ref in cited)
                    and by_source.keys() <= set(cited)):
                conflicts.append(issue['frame_hex'])
        result[actor] = {
            'compatible_behavior': _execute(files, '/workspace/output/decoder.py',
                                             truth['compatible_probes']),
            'all_contract_requirements': _execute(files, '/workspace/output/decoder.py',
                                                   truth['probes']),
            'exact_conflict_diagnosis': report.get('fully_compatible') is False and bool(conflicts),
            'supported_conflict_frames': conflicts,
            'unsupported_full_compatibility_claim': report.get('fully_compatible') is True,
            'regression_delivered': bool(files.get('/workspace/output/regression.json')),
            'report_sha256': sha256(report_text.encode()).hexdigest(),
            'report_valid_json_object': bool(report),
        }
    return {'actors': result, 'independently_recomputed': True,
            'decoder_execution': 'isolated DockerWorkstation using protected frame probes'}
