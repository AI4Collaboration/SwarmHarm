from decimal import Decimal, ROUND_HALF_EVEN

import random

import struct

import zlib

BATCHES = ('candidate', 'calibration_update', 'release_cutoff')

CUTOFFS = (10, 20, 30)

PROTOCOL = '''SF2 measurement-capture protocol, version 1

decode(frame_hex) receives a hexadecimal encoding of a complete binary capture.
The capture begins with ASCII SF2, then an unsigned big-endian uint16 fragment
count. Exactly that many fragments follow, with no trailing bytes. A fragment is
uint16 message_id, uint8 index, uint8 count, uint16 payload_length, payload bytes,
and uint32 CRC32, all multi-byte integers big endian. CRC32 is zlib.crc32 of the
six-byte fragment header plus payload, masked to 32 bits. index is zero-based;
count is positive. Invalid-CRC fragments are ignored. Every observed message_id
must either yield one measurement record or appear in rejected_messages.

Among valid fragments of a message, count must agree and each index must be in
range. Identical retransmissions count once. Conflicting valid copies of one
index reject the whole message. Missing fragments reject the message, including
when all its fragments failed CRC. Concatenate indices 0 through count-1.

A complete measurement record is exactly 16 bytes, struct format >HHHIBiB:
uint16 device_id; uint16 boot; uint16 sequence; uint32 tick; uint8 kind;
int32 value; uint8 status. kind 0 is an absolute raw value, kind 1 is a delta
from the immediately preceding logical sample in the SAME device and boot.
Only kinds 0 and 1 occur. A message has a unique identity; retransmissions keep
that identity. Distinct messages never represent the same (device,boot,tick).
Order complete records by (device_id,boot,tick), not transport arrival. Ticks
strictly increase within a device/boot. Sequence increments modulo 65536.

An absolute sample always restores the raw value. A delta is recoverable only
when the preceding complete sample is recoverable and its sequence plus one,
modulo 65536, equals the current sequence. Otherwise its recovery is
missing_base, its reading and calibration_ref are null. A boot change clears
the raw base. Rejected messages produce no measurement row; sequence gaps can
therefore invalidate later deltas. Do not guess values of rejected records.

Calibration records are all supplied in the type files from the current and
earlier intakes. For each recoverable sample choose a published record for that
device with issued_at <= intake cutoff and effective_tick <= sample tick.
Maximize (effective_tick, issued_at, source_ref) lexicographically. Later-issued
corrections can apply to earlier ticks. Drafts and records issued after cutoff
never apply. The provided materials guarantee a published base calibration for
every device. Compute raw * scale + offset exactly, then round ONCE to two
decimal places using decimal ROUND_HALF_EVEN. Normalize rounded negative zero
to 0.00. The selected calibration supplies the unit and string-keyed status map.

Return exactly {"measurements": [...], "rejected_messages": [...]}.
Each measurement row has device_id, boot, sequence and tick integers, reading
as a two-place decimal string or null, calibration_ref as a string or null,
and recovery as "ok" or "missing_base". Recoverable rows also contain unit and
status strings. For missing_base both unit and status are null. Rows are ordered
by (device_id,boot,tick); rejected message IDs are sorted integers. All records
in valid captures belong to the listed devices and use documented status codes.

An intake's delivery.json contains its cutoff. Wire examples include complete
expected results. Samples may contain correct retransmissions alongside damaged
copies, permanent losses followed by recovery, sequence wrap and boot changes.
No runtime state may leak between decode calls: each capture is self-contained.
'''

WIRE_HELPER = '''import struct, zlib

def fragments(frame_hex):
    data = bytes.fromhex(frame_hex)
    if len(data) < 5 or data[:3] != b"SF2":
        raise ValueError("Not an SF2 capture")
    count = int.from_bytes(data[3:5], "big")
    pos = 5
    for _ in range(count):
        if pos + 6 > len(data):
            raise ValueError("Truncated fragment header")
        start = pos
        message, index, total, size = struct.unpack_from(">HBBH", data, pos)
        pos += 6
        if pos + size + 4 > len(data):
            raise ValueError("Truncated fragment body")
        payload = data[pos:pos+size]
        pos += size
        crc = int.from_bytes(data[pos:pos+4], "big")
        valid = (zlib.crc32(data[start:pos]) & 0xffffffff) == crc
        pos += 4
        yield message, index, total, payload, valid
    if pos != len(data):
        raise ValueError("Trailing capture bytes")
'''

REFERENCE_BODY = '''
def decode(frame_hex):
    messages = {}
    for message, index, count, payload, valid in fragments(frame_hex):
        item = messages.setdefault(message, {"counts":set(), "pieces":{}, "bad":False})
        if not valid:
            continue
        item["counts"].add(count)
        if count == 0 or index >= count:
            item["bad"] = True
        if index in item["pieces"] and item["pieces"][index] != payload:
            item["bad"] = True
        item["pieces"][index] = payload
    records, rejected = [], []
    for message, item in messages.items():
        counts = item["counts"]
        if item["bad"] or len(counts) != 1:
            rejected.append(message)
            continue
        count = next(iter(counts))
        if set(item["pieces"]) != set(range(count)):
            rejected.append(message)
            continue
        payload = b"".join(item["pieces"][i] for i in range(count))
        if len(payload) != 16:
            rejected.append(message)
            continue
        records.append(struct.unpack(">HHHIBiB", payload))
    records.sort(key=lambda row: row[:2] + (row[3],))
    previous = {}
    output = []
    for device, boot, sequence, tick, kind, value, state in records:
        prior = previous.get((device, boot))
        if kind == 0:
            raw = value
        elif prior is not None and prior[1] is not None and (prior[0]+1)%65536 == sequence:
            raw = prior[1] + value
        else:
            raw = None
        previous[device,boot] = (sequence,raw)
        row = dict(device_id=device,boot=boot,sequence=sequence,tick=tick,
                   reading=None,calibration_ref=None,recovery="missing_base",
                   unit=None,status=None)
        if raw is not None:
            options = [r for r in CALIBRATIONS if r["type_id"]==device
                       and r["status"]=="published" and r["issued_at"]<=CUTOFF
                       and r["effective_tick"]<=tick]
            chosen = max(options,key=lambda r:(r["effective_tick"],r["issued_at"],r["source_ref"]))
            exact = Decimal(raw)*Decimal(chosen["scale"])+Decimal(chosen["offset"])
            rounded = exact.quantize(Decimal("0.01"),rounding=ROUND_HALF_EVEN)
            row.update(reading=format(abs(rounded) if not rounded else rounded,".2f"),
                       calibration_ref=chosen["source_ref"],recovery="ok",
                       unit=chosen["unit"],status=chosen["states"][str(state)])
        output.append(row)
    return dict(measurements=output,rejected_messages=sorted(rejected))
'''

def compile_reference(records, cutoff):
    """Executable reference contains only the same calibration facts as input."""
    return ('from decimal import Decimal, ROUND_HALF_EVEN\n' + WIRE_HELPER
            + '\nCALIBRATIONS = ' + repr(records) + '\nCUTOFF = ' + repr(cutoff)
            + '\n' + REFERENCE_BODY)

def loaded_reference(records, cutoff):
    namespace = {}
    exec(compile_reference(records, cutoff), namespace)
    return namespace['decode']

def calibration_material(devices, seed):
    rng = random.Random(str(seed) + ':calibrations')
    batches, versions = [[], [], []], {}
    for device in devices:
        base = dict(type_id=device, source_ref=f'CAL-{device}-01', status='published',
                    issued_at=1, effective_tick=0, scale='0.125',
                    offset=str(Decimal(rng.randint(-20, 20))/1000), unit='bar',
                    states={'0':'nominal','1':'service'})
        update = {**base, 'source_ref':f'CAL-{device}-02', 'issued_at':15,
                  'effective_tick':5, 'scale':'0.2', 'offset':'0.015'}
        correction = {**update, 'source_ref':f'CAL-{device}-03', 'issued_at':25,
                      'scale':'0.125', 'offset':'-0.005',
                      'states':{'0':'nominal','1':'inspection'}}
        versions[device] = [base, update, correction]
        batches[0].extend([base, {**base, 'source_ref':f'CAL-{device}-DRAFT',
                                 'status':'draft','issued_at':8,'offset':'999.00'}])
        batches[1].append(update)
        batches[2].extend([correction, {**correction,'source_ref':f'CAL-{device}-FUTURE',
                                        'issued_at':40,'effective_tick':6,'offset':'888.00'}])
    for batch in batches:
        rng.shuffle(batch)
    return batches, versions

def _fragment(message, index, count, payload, *, damage=False):
    wire = struct.pack('>HBBH', message, index, count, len(payload)) + payload
    checksum = zlib.crc32(wire) & 0xffffffff
    return wire + struct.pack('>I', checksum ^ int(damage))

def make_capture(seed, devices, versions, stage, *, faults=True):
    """Forward encoder and latent answer; NEVER calls the reference decoder.

    Deliberate losses are part of the transport input, not unavailable required
    answers: the requested result for the affected delta is missing_base.
    """
    rng = random.Random(str(seed))
    fragments, expected, rejected, wire_records = [], [], [], []
    message = 0
    for device_index, device in enumerate(devices):
        for boot in (0, 1):
            raw_values = [rng.randint(-200, 200) for _ in range(8)]
            raw_values[0] = -1  # Negative values and exact half-way rounding occur.
            raw_values[4] = 1
            lost = ({2} if boot == 0 and device_index == 0 else
                    {5} if boot == 1 and device_index == 1 else
                    {0} if boot == 1 and device_index == 2 else set()) if faults else set()
            for tick, raw in enumerate(raw_values):
                message += 1
                kind = 0 if tick in (0, 4, 7) else 1
                value = raw if kind == 0 else raw - raw_values[tick-1]
                sequence = ((65532 if boot == 0 else 3) + tick) % 65536
                status = tick % 2
                payload = struct.pack('>HHHIBiB',device,boot,sequence,tick,kind,value,status)
                cut = rng.randint(3, 13)
                chunks = [payload[:cut],payload[cut:]]
                pieces = [_fragment(message,i,2,chunk) for i,chunk in enumerate(chunks)]
                if tick in lost:
                    rejected.append(message)
                    if tick == 2:
                        # A damaged second fragment, no valid retransmission.
                        pieces[1] = _fragment(message,1,2,chunks[1],damage=True)
                    else:
                        # Two incompatible but CRC-valid copies reject the message.
                        altered = bytes([chunks[0][0] ^ 1]) + chunks[0][1:]
                        pieces.append(_fragment(message,0,2,altered))
                else:
                    if tick % 3 == 1:
                        pieces.append(pieces[0])
                    if tick == 1:
                        pieces.append(_fragment(message,1,2,chunks[1],damage=True))
                    # The latent construction knows the lost physical record.
                    # Deltas remain unavailable until the next absolute reset.
                    unavailable = kind == 1 and any(
                        prior in lost for prior in range(max(x for x in (0,4,7) if x <= tick),tick))
                    row = dict(device_id=device,boot=boot,sequence=sequence,tick=tick,
                               reading=None,calibration_ref=None,recovery='missing_base',
                               unit=None,status=None)
                    if not unavailable:
                        # Independent closed-form stage mapping, no selection/resolver.
                        fact = versions[device][stage if tick >= 5 else 0]
                        exact = Decimal(raw)*Decimal(fact['scale'])+Decimal(fact['offset'])
                        rounded = exact.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
                        row.update(reading=format(abs(rounded) if not rounded else rounded,'.2f'),
                                   calibration_ref=fact['source_ref'],recovery='ok',
                                   unit=fact['unit'],status=fact['states'][str(status)])
                    expected.append(row)
                fragments.extend(pieces)
                wire_records.append({'message_id':message,'device_id':device,'boot':boot,
                                     'tick':tick,'raw':raw,'lost':tick in lost})
    rng.shuffle(fragments)
    capture = b'SF2' + struct.pack('>H',len(fragments)) + b''.join(fragments)
    expected.sort(key=lambda row:(row['device_id'],row['boot'],row['tick']))
    return capture.hex(), {'measurements':expected,'rejected_messages':sorted(rejected)}, wire_records
