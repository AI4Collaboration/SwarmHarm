"""HTTP connections to named local delivery processes."""
from contextlib import contextmanager
from http.client import HTTPConnection
import io
from pathlib import Path
import re
import socket
from socketserver import ThreadingUnixStreamServer
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen as tcp_urlopen


def socket_address(url):
    address = urlsplit(url)
    if (address.scheme != 'http+unix' or address.path not in ('', '/')
            or address.query or address.fragment
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', address.netloc)):
        raise ValueError('Invalid local processor address')
    return b'\0' + address.netloc.encode('ascii')


class LocalConnection(HTTPConnection):
    def __init__(self, address, timeout):
        super().__init__('localhost', timeout=timeout)
        self.address = address

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        try:
            self.sock.connect(self.address)
        except BaseException:
            self.sock.close()
            self.sock = None
            raise


@contextmanager
def urlopen(request, timeout=20):
    address = urlsplit(request.full_url)
    if address.scheme != 'http+unix':
        with tcp_urlopen(request, timeout=timeout) as response:
            yield response
        return
    connection = LocalConnection(socket_address('http+unix://' + address.netloc), timeout)
    try:
        path = address.path or '/'
        if address.query:
            path += '?' + address.query
        connection.request(request.get_method(), path, body=request.data,
                           headers=dict(request.header_items()))
        with connection.getresponse() as response:
            if not 200 <= response.status < 300:
                raise HTTPError(request.full_url, response.status, response.reason,
                                response.headers, io.BytesIO(response.read()))
            yield response
    finally:
        connection.close()


class LocalServer(ThreadingUnixStreamServer):
    daemon_threads = True


def server(url, handler):
    return LocalServer(socket_address(url), handler)


def unix_listeners():
    listeners = []
    for line in Path('/proc/net/unix').read_text().splitlines()[1:]:
        fields = line.split(maxsplit=7)
        if len(fields) == 8 and fields[3:6] == ['00010000', '0001', '01']:
            listeners.append({'name': fields[7]})
    return sorted(listeners, key=lambda row: row['name'])
