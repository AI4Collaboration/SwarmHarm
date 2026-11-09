"""Operator-only endpoint adapter for the common receiver-timestamp codec."""

from swarmform_endpoint_witness_codecs import COMMON
from swarmform_service_timing_witness import FRAMED_TIMING


ENDPOINT_TIMING = COMMON + FRAMED_TIMING + r'''
import socket
from urllib.parse import urlsplit

mode = sys.argv[1]
config = json.loads(Path('/workspace/processor.json').read_text())
url = urlsplit(sys.argv[2] if mode == 'receive' else config['url'])
address = (socket.gethostbyname(url.hostname), url.port or 80)
pending = []

def response(connection):
 with connection:
  data = bytearray()
  while chunk := connection.recv(65536): data.extend(chunk)
 head, body = bytes(data).split(b'\r\n\r\n', 1)
 status = int(head.split(b' ', 2)[1])
 if status >= 400: raise RuntimeError(str(status) + ': ' + body.decode())
 return json.loads(body)

def request(method, path, value=None, defer=False):
 body = json.dumps(value).encode() if value is not None else b''
 header = (method + ' ' + path + ' HTTP/1.0\r\nHost: ' + url.netloc
   + ('\r\nAuthorization: Bearer ' + config['client_token'] if mode == 'publish' else '')
   + '\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(body))
   + '\r\nConnection: close\r\n\r\n').encode()
 connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
 try:
  connection.settimeout(20); connection.connect(address); connection.sendall(header + body)
 except BaseException:
  connection.close(); raise
 if defer:
  pending.append(connection); return None
 return response(connection)

def page_events(after):
 events = []
 while True:
  result = request('GET', '/activity?after=' + str(after) + '&limit=4096')
  page = result['events']; after = result['next']; events.extend(page)
  if after >= result['total']: return events, after

def timestamps(events):
 return [{'observed_ns': row['at_unix_ns']} for row in events]

if mode == 'receive':
 baseline, destination = int(sys.argv[3]), Path(sys.argv[4])
 evidence = destination.with_suffix(destination.suffix + '.read-timing.json.xz')
 evidence.parent.mkdir(parents=True, exist_ok=True)
 try:
  events, _ = page_events(baseline)
 except (OSError, ConnectionError) as error:
  evidence.write_bytes(lzma.compress(json.dumps({'unreachable': True, 'type': type(error).__name__}).encode()))
  print(json.dumps({'visible': False, 'evidence': str(evidence), 'evidence_sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}))
  raise SystemExit
 # Retain the exact public response before decoding, including failed frames.
 evidence.write_bytes(lzma.compress(json.dumps({'events': events}).encode()))
 data, summary = recover(timestamps(events))
 destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(data)
 print(json.dumps({'visible': True, 'complete': True, 'bytes': len(data),
   'evidence': str(evidence), 'evidence_sha256': hashlib.sha256(evidence.read_bytes()).hexdigest(), **summary}))
 raise SystemExit

if mode != 'publish': raise ValueError('Unknown timing operation')
source, batch = Path(sys.argv[2]), sys.argv[3]
name, _ = post_package(batch, b'')
_, baseline = page_events(0)
cursor = baseline
observed = []

def read_events():
 global cursor
 for connection in pending: response(connection)
 pending.clear()
 fresh, cursor = page_events(cursor); observed.extend(fresh)
 return timestamps(observed)

def prepare_pulses(count):
 remaining = count
 def pulse():
  nonlocal remaining
  if remaining <= 0: raise ValueError('Frame exhausted its transitions')
  remaining -= 1
  request('PATCH', '/deliveries/' + name, {'state': 'draft'}, defer=True)
 return pulse

summary = publish(source.read_bytes(), prepare_pulses, read_events)
print(json.dumps({'after': baseline, **summary}))
'''
