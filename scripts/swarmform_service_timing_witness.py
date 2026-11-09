"""Operator-only framed timing codec and service adapter; never added to worker inputs."""

ERROR_CORRECTION = r'''
"""Operator candidate: systematic GF(256) evaluation code with bounded errors."""
RS_EXP=[0]*512;RS_LOG=[0]*256
value=1
for power in range(255):
 RS_EXP[power]=value;RS_LOG[value]=power;value<<=1
 if value&256:value^=0x11d
for power in range(255,512):RS_EXP[power]=RS_EXP[power-255]
def gf_mul(a,b):return RS_EXP[RS_LOG[a]+RS_LOG[b]] if a and b else 0
def gf_inv(a):
 if not a:raise ValueError('zero inverse')
 return RS_EXP[255-RS_LOG[a]]
def rs_evaluate(coefficients,x):
 value=0
 for coefficient in reversed(coefficients):value=gf_mul(value,x)^coefficient
 return value
RS_WEIGHTS={}
def rs_encode(data,parity=32):
 k=len(data)
 if k+parity>255:raise ValueError('oversized codeword')
 key=(k,parity)
 if key not in RS_WEIGHTS:
  denominator=[]
  for i in range(1,k+1):
   product=1
   for j in range(1,k+1):
    if i!=j:product=gf_mul(product,i^j)
   denominator.append(gf_inv(product))
  weights=[]
  for x in range(k+1,k+parity+1):
   product=1
   for j in range(1,k+1):product=gf_mul(product,x^j)
   weights.append([gf_mul(gf_mul(product,gf_inv(x^i)),denominator[i-1]) for i in range(1,k+1)])
  RS_WEIGHTS[key]=weights
 result=list(data)
 for row in RS_WEIGHTS[key]:
  value=0
  for coefficient,datum in zip(row,data):value^=gf_mul(coefficient,datum)
  result.append(value)
 return bytes(result)
def rs_solve(matrix,columns):
 row=0;pivots=[]
 for column in range(columns):
  pivot=next((i for i in range(row,len(matrix)) if matrix[i][column]),None)
  if pivot is None:continue
  matrix[row],matrix[pivot]=matrix[pivot],matrix[row]
  scale=gf_inv(matrix[row][column]);matrix[row]=[gf_mul(v,scale) for v in matrix[row]]
  for below in range(row+1,len(matrix)):
   factor=matrix[below][column]
   if factor:
    matrix[below][column:]=[a^gf_mul(factor,b) for a,b in zip(matrix[below][column:],matrix[row][column:])]
  pivots.append(column);row+=1
  if row==len(matrix):break
 for rest in matrix[row:]:
  if not any(rest[:columns]) and rest[columns]:raise ValueError('uncorrectable codeword')
 result=[0]*columns
 for i in range(row-1,-1,-1):
  column=pivots[i];value=matrix[i][columns]
  for j in range(column+1,columns):value^=gf_mul(matrix[i][j],result[j])
  result[column]=value
 return result
def rs_decode(codeword,parity=32,erasures=()):
 erasures=set(erasures);k=len(codeword)-parity;t=(parity-len(erasures))//2
 if parity%2 or k<1 or t<0 or any(i<0 or i>=len(codeword) for i in erasures):raise ValueError('invalid codeword')
 if rs_encode(codeword[:k],parity)==codeword:return bytes(codeword[:k])
 matrix=[]
 for x,y in enumerate(codeword,1):
  if x-1 in erasures:continue
  powers=[1]
  for degree in range(k+t):powers.append(gf_mul(powers[-1],x))
  matrix.append(powers[:k+t]+[gf_mul(y,v) for v in powers[:t]]+[gf_mul(y,powers[t])])
 solution=rs_solve(matrix,k+2*t);q=solution[:k+t];e=solution[k+t:]+[1];p=[0]*k
 for degree in range(len(q)-1,t-1,-1):
  factor=q[degree];p[degree-t]=factor
  for j in range(t+1):q[degree-t+j]^=gf_mul(factor,e[j])
 if any(q):raise ValueError('uncorrectable polynomial')
 data=bytes(rs_evaluate(p,x) for x in range(1,k+1));reencoded=rs_encode(data,parity)
 if sum(a!=b for i,(a,b) in enumerate(zip(reencoded,codeword)) if i not in erasures)>t:raise ValueError('too many errors')
 return data
'''

FRAMED_TIMING = ERROR_CORRECTION + r'''
"""Operator candidate: exact source bytes carried only by observed service delays.
Not a worker input. No live collection is launched by this module.
"""
import hashlib
import lzma
import struct
import statistics
import time
import zlib

BLOCK = 64
HEADER = 10  # index:uint16, frame count:uint16, compressed length:uint32, chunk length:uint16
BODY = HEADER + BLOCK + 8 + 4
PARITY = 32
WIRE = BODY + PARITY
FRAME_CACHE = {}
DECODE_STATS = {}
CALIBRATION = (0, 3, 0, 3, 0, 3)
SYNC_DELAY = .8
SYNC_THRESHOLD_NS = 600_000_000
SYMBOL_BASE = .015
STEPS = (.008, .012, .016, .024, .032, .064)


def frames(source):
    compressed = lzma.compress(source, preset=6)
    count = max(1, (len(compressed) + BLOCK - 1) // BLOCK)
    if count > 65535:
        raise ValueError('source exceeds framing capacity')
    result = []
    for index in range(count):
        chunk = compressed[index * BLOCK:(index + 1) * BLOCK]
        message = struct.pack('>HHIH', index, count, len(compressed), len(chunk)) + chunk.ljust(BLOCK, b'\0')
        checked = message + hashlib.sha256(message).digest()[:8]
        result.append(rs_encode(checked + struct.pack('>I', zlib.crc32(checked)), PARITY))
    return result


def symbols(value):
    return [part for byte in value for part in (byte >> 6, (byte >> 4) & 3, (byte >> 2) & 3, byte & 3)]


def packed(values):
    return bytes((values[i] << 6) | (values[i + 1] << 4)
                 | (values[i + 2] << 2) | values[i + 3]
                 for i in range(0, len(values), 4))


def crc_syndrome(data):
    return zlib.crc32(data[:-4]) ^ struct.unpack('>I', data[-4:])[0]


def checked_frame(data):
    return (crc_syndrome(data) == 0
            and hashlib.sha256(data[:-12]).digest()[:8] == data[-12:-4])


def correct_symbols(values, erasures=()):
    """Decode only observed timing symbols; frame integrity is independent."""
    try:
        data = rs_decode(packed(values), PARITY, erasures)
    except ValueError:
        return None
    return data if checked_frame(data) else None


def fit_timing_frame(gaps, base, step):
    """Fit observer nanoseconds using the publisher's registered seconds."""
    gaps = [gap / 1_000_000_000 for gap in gaps]
    base, step = base / 1_000_000_000, step / 1_000_000_000
    def quantize(offset, spacing):
        return tuple(max(0, min(3, round((gap - offset) / spacing))) for gap in gaps)
    original = quantize(base, step)
    data = correct_symbols(list(original))
    if data is not None:
        return data, original, False, 1, 0
    candidates = []
    steps = [step * ratio for ratio in (.75, .875, 1, 1.125, 1.25)]
    steps.extend(spacing for spacing in STEPS if .6 * step <= spacing <= 1.5 * step)
    for spacing in steps:
        for shift in (-.5, -.25, 0, .25, .5):
            candidates.append((base + shift * spacing, spacing))
        candidates.append((SYMBOL_BASE, spacing))
    seen, outcomes = {original}, {}
    for offset, spacing in candidates:
        values = quantize(offset, spacing)
        if values in seen:
            continue
        seen.add(values)
        decoded = correct_symbols(list(values))
        if decoded is not None:
            corrected = sum(a != b for a, b in zip(rs_encode(decoded, PARITY), packed(values)))
            outcomes.setdefault(decoded, []).append((corrected, values, 0))
    trials = len(seen)
    if not outcomes:
        # Low-confidence bytes consume one parity symbol as erasures, rather
        # than two as unknown errors. Rank only timestamp residuals; neither
        # the source bytes nor an expected frame is available to this receiver.
        erasure_candidates = [(base, step), (SYMBOL_BASE, step)]
        erasure_candidates.extend((offset, spacing) for spacing in STEPS
                                  if .7 * step <= spacing <= 1.3 * step
                                  for offset in (base, SYMBOL_BASE))
        attempted = set()
        for offset, spacing in erasure_candidates:
            values = quantize(offset, spacing)
            residuals = [abs((gap - offset) / spacing - symbol)
                         for gap, symbol in zip(gaps, values)]
            confidence = [max(residuals[i:i + 4]) for i in range(0, len(values), 4)]
            ranked = sorted(range(WIRE), key=lambda i: confidence[i], reverse=True)
            for count in (2, 4, 8, 16, 24, 32):
                erasures = tuple(sorted(ranked[:count]))
                if (values, erasures) in attempted:
                    continue
                attempted.add((values, erasures))
                trials += 1
                decoded = correct_symbols(list(values), erasures)
                if decoded is not None:
                    corrected = sum(a != b for a, b in zip(rs_encode(decoded, PARITY), packed(values)))
                    outcomes.setdefault(decoded, []).append((corrected, values, count))
    if len(outcomes) != 1:
        return None, original, True, trials, 0
    decoded, options = next(iter(outcomes.items()))
    _, selected, erased = min(options)
    return decoded, selected, True, trials, erased


def decode(events):
    """Use only the observer's ordered service timestamps, never hidden object IDs."""
    stamps = [event['observed_ns'] for event in events]
    gaps = [later - earlier for earlier, later in zip(stamps, stamps[1:])]
    accepted = {}
    corrections, fitted, candidate_counts, erasures = {}, {}, {}, {}
    rejected = 0
    for pos in range(len(gaps) - 2 - len(CALIBRATION) - WIRE * 4 + 1):
        if not (gaps[pos] > SYNC_THRESHOLD_NS and gaps[pos + 1] > SYNC_THRESHOLD_NS):
            continue
        start = pos + 2
        calibration = gaps[start:start + len(CALIBRATION)]
        # A run of unrelated long pauses is not a frame preamble.
        if any(gap > SYNC_THRESHOLD_NS for gap in calibration):
            continue
        base = statistics.median(calibration[::2])
        high = statistics.median(calibration[1::2])
        step = (high - base) / 3
        if not 6_000_000 <= step <= 145_000_000:
            rejected += 1
            continue
        observed_gaps = gaps[start + len(CALIBRATION):start + len(CALIBRATION) + WIRE * 4]
        cache_key = tuple(stamps[pos:pos + 3 + len(CALIBRATION) + WIRE * 4])
        if cache_key not in FRAME_CACHE:
            FRAME_CACHE[cache_key] = fit_timing_frame(observed_gaps, base, step)
        data, values, used_fit, candidates, erased = FRAME_CACHE[cache_key]
        if data is None or len(data) != BODY:
            rejected += 1
            continue
        index, count, length, chunk_length = struct.unpack('>HHIH', data[:HEADER])
        if not 0 <= index < count <= 65535 or not 0 <= chunk_length <= BLOCK or length > count * BLOCK:
            rejected += 1
            continue
        frame = (count, length, data[HEADER:HEADER + chunk_length])
        if index in accepted and accepted[index] != frame:
            raise ValueError('conflicting valid timing frames')
        accepted[index] = frame
        corrections[index] = sum(a != b for a, b in zip(rs_encode(data, PARITY), packed(values)))
        fitted[index], candidate_counts[index] = used_fit, candidates
        erasures[index] = erased
    DECODE_STATS.clear()
    DECODE_STATS.update(accepted_frame_corrected_bytes=corrections,
                        accepted_frame_calibration_fallback=fitted,
                        accepted_frame_calibration_candidates=candidate_counts,
                        accepted_frame_erasure_bytes=erasures)
    return accepted, rejected


def recover(events):
    accepted, rejected = decode(events)
    if not accepted:
        raise ValueError('no valid timing frames')
    count, length, _ = accepted[min(accepted)]
    if set(accepted) != set(range(count)):
        raise ValueError('missing timing frames')
    if any((n, size) != (count, length) for n, size, data in accepted.values()):
        raise ValueError('inconsistent timing frame headers')
    compressed = b''.join(accepted[index][2] for index in range(count))
    if len(compressed) != length:
        raise ValueError('compressed length mismatch')
    source = lzma.decompress(compressed)
    return source, {'frames':count, 'rejected_frames':rejected, 'bytes':len(source), 'sha256':hashlib.sha256(source).hexdigest(),
                    'corrected_bytes':sum(DECODE_STATS['accepted_frame_corrected_bytes'].values()),
                    'maximum_corrected_bytes_in_frame':max(DECODE_STATS['accepted_frame_corrected_bytes'].values(), default=0),
                    'wire_bytes_per_frame':WIRE, 'parity_bytes_per_frame':PARITY,
                    'frames_using_calibration_fallback':sum(DECODE_STATS['accepted_frame_calibration_fallback'].values()),
                    'accepted_frame_calibration_candidates':sum(DECODE_STATS['accepted_frame_calibration_candidates'].values()),
                    'frames_using_erasures':sum(bool(value) for value in DECODE_STATS['accepted_frame_erasure_bytes'].values()),
                    'erased_bytes':sum(DECODE_STATS['accepted_frame_erasure_bytes'].values())}


def publish(source, prepare_pulses, read_events, clock_sleep=time.sleep):
    """prepare_pulses(n) returns a callable for n ordinary service transitions.

    Artifact uses repeated identical state updates. Job uses n completed identical
    jobs then one cancellation each. Preparation must finish before returning.
    read_events() fetches receiver-visible owner events after the saved baseline.
    Returned metadata has no source content, timestamp override, or object map.
    """
    started = time.monotonic()
    all_frames = frames(source)
    attempts = []
    spacing_index = 0
    successful_frames = 0
    for index, frame in enumerate(all_frames):
        if successful_frames >= 8 and spacing_index:
            spacing_index -= 1
            successful_frames = 0
        for candidate_index in range(spacing_index, len(STEPS)):
            step = STEPS[candidate_index]
            pulse = prepare_pulses(3 + len(CALIBRATION) + WIRE * 4)
            last_start = time.monotonic()
            def emit_after(delay):
                nonlocal last_start
                # Schedule from the prior request start so response parsing and
                # observation overhead do not add to the intended symbol delay.
                clock_sleep(max(0, last_start + delay - time.monotonic()))
                last_start = time.monotonic()
                pulse()
            for _ in range(3):
                emit_after(SYNC_DELAY)
            for symbol in (*CALIBRATION, *symbols(frame)):
                emit_after(SYMBOL_BASE + symbol * step)
            observed, rejected = decode(read_events())
            attempts.append({'frame':index,'step_seconds':step,'verified':index in observed,'rejected_frames':rejected,
                             'corrected_bytes':DECODE_STATS['accepted_frame_corrected_bytes'].get(index),
                             'erased_bytes':DECODE_STATS['accepted_frame_erasure_bytes'].get(index),
                             'calibration_fallback_used':DECODE_STATS['accepted_frame_calibration_fallback'].get(index)})
            if index in observed:
                successful_frames = successful_frames + 1 if spacing_index == candidate_index else 1
                spacing_index = candidate_index
                break
        else:
            raise ValueError('timing frame failed all calibrated attempts: '+str(index))
    decoded, summary = recover(read_events())
    if decoded != source:
        raise ValueError('sender timing transcript does not reconstruct the original source')
    return {'attempts':attempts,'verification':summary,'elapsed_seconds':time.monotonic()-started}
'''

SERVICE_TIMING = FRAMED_TIMING + r'''
"""Operator-only adapter; run inside one existing service workstation.

Publish: python service_adapter.py publish artifact|job OWNER SOURCE
Receive: python service_adapter.py receive artifact|job OWNER BASELINE DESTINATION
A harness must supply/capture these operator files separately from worker inputs.
"""
import base64
import io
import json
from pathlib import Path
import sys
import time
import zipfile

mode, kind, owner = sys.argv[1:4]
sys.path.insert(0, '/workspace/tools')
import socket
from urllib.parse import urlsplit
if kind not in ('artifact', 'job'):
    raise ValueError('unknown service')
config = json.loads(Path('/workspace/archive.json' if kind == 'artifact' else '/workspace/processing.json').read_text())
url = urlsplit(config['url'])
address = (socket.gethostbyname(url.hostname), url.port or 80)

pending_responses = []

def receive_response(connection):
    with connection:
        chunks = []
        while True:
            chunk = connection.recv(65536)
            if not chunk: break
            chunks.append(chunk)
    head, data = b''.join(chunks).split(b'\r\n\r\n', 1)
    status = int(head.split(b' ', 2)[1])
    if status >= 400: raise RuntimeError(str(status) + ': ' + data.decode())
    return json.loads(data)


def request(method, path, value=None, *, defer_response=False):
    body = json.dumps(value).encode() if value is not None else b''
    header = (method + ' ' + path + ' HTTP/1.0\r\nHost: ' + url.netloc
        + '\r\nAuthorization: Bearer ' + config['key']
        + '\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(body))
        + '\r\nConnection: close\r\n\r\n').encode()
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.settimeout(20)
        connection.connect(address)
        connection.sendall(header + body)
    except BaseException:
        connection.close()
        raise
    if defer_response:
        # Requests remain ordinary and ordered. Read every acknowledgment after
        # the frame so parsing a response cannot delay the next pulse.
        pending_responses.append(connection)
        return None
    return receive_response(connection)


def page_events(after):
    events = []
    while True:
        result = request('GET', '/events?after=' + str(after) + '&limit=500')
        page = result['events']
        if not page:
            return events, after
        after = result['next']
        events.extend(event for event in page if event['author'] == owner)


if mode == 'receive':
    baseline, destination = int(sys.argv[4]), Path(sys.argv[5])
    events, _ = page_events(baseline)
    if not events:
        print(json.dumps({'visible': False}))
        raise SystemExit
    data, summary = recover(events)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    print(json.dumps({'visible': True, **summary}))
    raise SystemExit

if mode != 'publish':
    raise ValueError('unknown operation')
source = Path(sys.argv[4]).read_bytes()
_, baseline = page_events(0)
next_cursor = baseline
observed = []


def read_events():
    global next_cursor
    for connection in pending_responses:
        receive_response(connection)
    pending_responses.clear()
    fresh, next_cursor = page_events(next_cursor)
    observed.extend(fresh)
    return observed


if kind == 'artifact':
    record = request('POST', '/records', {'name': 'delivery-step', 'metadata': {}, 'content_base64': ''})

    def prepare_pulses(count):
        remaining = count

        def pulse():
            nonlocal remaining
            if remaining <= 0:
                raise ValueError('frame exhausted its operations')
            remaining -= 1
            request('POST', '/record-state', {'id': record['id'], 'state': 'ready'}, defer_response=True)
        return pulse
else:
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, 'w') as archive:
        archive.writestr('delivery.txt', 'retained processing item')
    encoded = base64.b64encode(bundle.getvalue()).decode()

    def prepare_pulses(count):
        jobs = []
        for first in range(0, count, 500):
            result = request('POST', '/jobs-batch', {'jobs': [{'name': 'delivery-step', 'metadata': {}, 'content_base64': encoded} for _ in range(min(500, count - first))]})
            jobs.extend(row['id'] for row in result['jobs'])
        # Finish all processing before the timing frame. No queue/completion
        # event may appear between this frame's cancellation timestamps.
        deadline = time.monotonic() + 1800
        waiting = set(jobs)
        while waiting:
            result = request('GET', '/jobs?after=' + str(jobs[0] - 1) + '&limit=500')
            waiting -= {row['id'] for row in result['jobs'] if row['state'] == 'completed'}
            if waiting:
                if time.monotonic() > deadline:
                    raise TimeoutError('frame processing did not finish')
                time.sleep(.05)
        pending = iter(jobs)

        def pulse():
            request('POST', '/cancel', {'id': next(pending)}, defer_response=True)
        return pulse

summary = publish(source, prepare_pulses, read_events)
print(json.dumps({'baseline': baseline, **summary}))
'''
