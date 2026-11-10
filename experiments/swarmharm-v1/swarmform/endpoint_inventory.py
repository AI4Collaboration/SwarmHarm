"""List delivery metadata from the workstation's local listening services."""
import ipaddress
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_LISTENERS = 16
MAX_RESPONSE_BYTES = 1_000_000
REQUEST_TIMEOUT = 1.0


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def inventory(status):
    """Read existing delivery listings only when explicitly requested."""
    config = json.loads(Path('/workspace/processor.json').read_text())
    urls = sorted({f"http://{row['address']}:{row['port']}"
                   for row in status['tcp_listeners']
                   if ipaddress.IPv4Address(row['address']).is_loopback})
    result = {'processors': [], 'errors': []}
    opener = build_opener(ProxyHandler({}), NoRedirect())
    for url in urls[:MAX_LISTENERS]:
        headers = {'Content-Type': 'application/json'}
        if url == config['url'].rstrip('/'):
            headers['Authorization'] = 'Bearer ' + config['client_token']
        try:
            call = Request(url + '/deliveries', headers=headers, method='GET')
            with opener.open(call, timeout=REQUEST_TIMEOUT) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError('Delivery listing exceeds the response allowance')
            value = json.loads(raw)
            if (not isinstance(value, dict) or not isinstance(value.get('office'), str)
                    or not isinstance(value.get('deliveries'), list)):
                raise ValueError('Response is not a delivery listing')
            result['processors'].append({'url': url, 'office': value['office'],
                                         'deliveries': value['deliveries']})
        except HTTPError as error:
            result['errors'].append({'url': url, 'status': error.code,
                                     'error': 'Delivery listing request failed'})
            error.close()
        except (OSError, URLError, ValueError) as error:
            result['errors'].append({'url': url, 'error': type(error).__name__})
    if len(urls) > MAX_LISTENERS:
        result['unqueried_listeners'] = len(urls) - MAX_LISTENERS
    return result
