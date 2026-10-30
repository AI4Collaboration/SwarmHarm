"""JSON-RPC connection to a pinned Codex app-server process."""

import json
from pathlib import Path
import queue
import subprocess
import threading


class CodexRpc:
    """Keep the native stream separate from controller projections."""

    def __init__(self, command, *, env, cwd, folder, notification=None, server_request=None):
        self.folder = Path(folder)
        (self.folder / 'native').mkdir(parents=True, exist_ok=True)
        self.notification = notification or (lambda message, source: None)
        self.server_request = server_request
        self.pending = {}
        self.lock = threading.Lock()
        self.native_lock = threading.Lock()
        self.sequence = 0
        self.request_id = 0
        self.closed = False
        self.disconnected = threading.Event()
        self.stderr = (self.folder / 'stderr.log').open('xb')
        self.process = subprocess.Popen(command, env=env, cwd=cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            text=True, bufsize=1, start_new_session=True)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def record(self, direction, message):
        # account/read can contain account identity. Persist only its auth type.
        with self.native_lock:
            self.sequence += 1
            source = f'native/{self.sequence:06d}.json'
            value = {'direction': direction, 'message': message}
            (self.folder / source).write_text(json.dumps(value, ensure_ascii=False) + '\n')
        return source

    def send(self, message, *, persist=True):
        with self.lock:
            if self.disconnected.is_set():
                raise RuntimeError('Codex app-server connection closed')
            if persist:
                self.record('client', message)
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            self.process.stdin.flush()

    def request(self, method, params=None, *, timeout=60, private=False):
        with self.lock:
            self.request_id += 1
            identity = self.request_id
            result = queue.Queue()
            self.pending[identity] = (result, private)
        try:
            self.send({'id': identity, 'method': method, 'params': params}, persist=not private)
            value = result.get(timeout=timeout)
            if isinstance(value, Exception):
                raise value
            if 'error' in value:
                raise RuntimeError(f'Codex {method} failed: {value["error"]}')
            return value['result']
        finally:
            with self.lock:
                self.pending.pop(identity, None)

    def _read(self):
        try:
            for line in self.process.stdout:
                message = json.loads(line)
                waiting = self.pending.get(message.get('id')) if 'method' not in message else None
                if waiting:
                    target, private = waiting
                    if not private:
                        self.record('server', message)
                    target.put(message)
                    continue
                source = self.record('server', message)
                if 'id' in message and 'method' in message:
                    if self.server_request is None:
                        self.send({'id': message['id'], 'error': {
                            'code': -32601, 'message': 'Client request is unsupported.'}})
                    else:
                        self.server_request(message, source)
                else:
                    self.notification(message, source)
        except Exception as error:
            for target, _ in list(self.pending.values()):
                target.put(error)
            if not self.closed:
                self.notification({'method': 'transport/error', 'params': {
                    'message': str(error)}}, None)
        finally:
            self.disconnected.set()
            if not self.closed:
                self.notification({'method': 'transport/error', 'params': {
                    'message': 'Codex app-server connection closed'}}, None)
            for target, _ in list(self.pending.values()):
                target.put(RuntimeError('Codex app-server connection closed'))

    def close(self, timeout=10):
        import os
        import signal
        self.closed = True
        try:
            self.process.stdin.close()
            self.process.wait(timeout=timeout)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                if self.process.poll() is None:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait()
        finally:
            self.reader.join(timeout=5)
            self.process.stdout.close()
            self.stderr.close()
        return self.process.returncode
