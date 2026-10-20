"""Host-only Responses transport for an explicitly configured DeepSeek route."""
import json
import os
from pathlib import Path
import signal
import time
from urllib.parse import urlsplit
import urllib.error
import urllib.request

MODEL = None
ENDPOINT = None
API_KEY_ENV = 'DEEPSEEK_API_KEY'
API_KEY_FILE = None


def configure(model, base_url, key_env='DEEPSEEK_API_KEY', key_file=None):
    global MODEL, ENDPOINT, API_KEY_ENV, API_KEY_FILE
    url = urlsplit(base_url)
    if (url.scheme != 'https' or not url.netloc or url.username or url.password
            or url.query or url.fragment):
        raise ValueError('Use an HTTPS API base URL without credentials or query parameters')
    if 'deepseek' not in model.lower():
        raise ValueError('Select an explicit DeepSeek model ID from the configured provider')
    MODEL, ENDPOINT = model, base_url.rstrip('/') + '/responses'
    API_KEY_ENV, API_KEY_FILE = key_env, Path(key_file).expanduser() if key_file else None


def key():
    value = API_KEY_FILE.read_text().strip() if API_KEY_FILE else os.environ.get(API_KEY_ENV, '').strip()
    if not value:
        raise ValueError('No API credential configured; no request was sent')
    if any(c.isspace() for c in value):
        raise ValueError('The API key file must contain only the key')
    return value


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def payload(body):
    if MODEL is None or ENDPOINT is None:
        raise ValueError('DeepSeek route is not configured')
    return {'model': MODEL, 'store': False, 'stream': True,
            'parallel_tool_calls': False, 'include': ['reasoning.encrypted_content'], **body}


def call(body, directory, label, timeout=150):
    credential = key()
    request_body = payload(body)
    directory = Path(directory)
    save(directory / (label + '.request.json'), request_body)
    request = urllib.request.Request(ENDPOINT, data=json.dumps(request_body).encode(), headers={
        'Authorization': 'Bearer ' + credential, 'Content-Type': 'application/json',
        'Accept': 'text/event-stream', 'User-Agent': 'SwarmHarm-business-pilot/1.0'})
    started = time.monotonic()
    response = None
    def timed_out(signum, frame):
        raise TimeoutError('Inference request exceeded wall time')
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.setitimer(signal.ITIMER_REAL, 0)
    signal.signal(signal.SIGALRM, timed_out)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as stream:
            for line in stream:
                if time.monotonic() - started > timeout:
                    raise TimeoutError('Inference request exceeded wall time')
                if not line.startswith(b'data:'):
                    continue
                try:
                    event = json.loads(line[5:])
                except (ValueError, UnicodeDecodeError):
                    continue
                if event.get('type') == 'error':
                    error = event.get('error') if isinstance(event.get('error'), dict) else event
                    diagnostic = {k: str(error[k]).replace(credential, '[REDACTED]')
                                  for k in ('type', 'code', 'message', 'status', 'param') if k in error}
                    save(directory / (label + '.error.json'), {'provider_error': diagnostic})
                    raise RuntimeError('Inference stream returned an error')
                if event.get('type') in ('response.completed', 'response.failed', 'response.incomplete'):
                    response = event.get('response', {})
                    break
    except urllib.error.HTTPError as error:
        save(directory / (label + '.error.json'), {'http_status': error.code})
        raise RuntimeError('Inference HTTP ' + str(error.code)) from None
    except TimeoutError:
        save(directory / (label + '.error.json'), {'timeout_seconds': timeout})
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, *old_timer)
        signal.signal(signal.SIGALRM, old_handler)
    if response is None:
        save(directory / (label + '.error.json'), {'provider_error': 'No terminal response'})
        raise RuntimeError('Inference stream ended without a terminal response')
    # The raw provider model ID and status are preserved, never relabelled.
    save(directory / (label + '.response.json'), response)
    if response.get('status') != 'completed' or response.get('model') != MODEL:
        raise RuntimeError('Inference status/model mismatch; native response preserved')
    return response


def output_text(response):
    return '\n'.join(c.get('text', '') for item in response.get('output', [])
        if item.get('type') == 'message' for c in item.get('content', [])
        if c.get('type') == 'output_text')
