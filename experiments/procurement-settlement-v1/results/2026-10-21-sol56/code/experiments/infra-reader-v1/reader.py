"""Contained public-byte reader with explicit lifecycle evidence and durable receipts."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import base64
import json
import os
import secrets
import subprocess
import tempfile
import time


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(json.dumps(value,ensure_ascii=False,indent=2).encode() + b'\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class ReaderFailure(RuntimeError):
    def __init__(self, kind, phase, message, evidence=None):
        super().__init__(message)
        self.kind, self.phase, self.evidence = kind, phase, evidence or {}


class PublicReader:
    """One fresh isolated consumer per distinct public-byte state, never model retries.

    Successful receipts are content addressed. Cache keys include image, decoder,
    wrapper and every public path/body. Invalid receipts and failed executions are
    never cached. Each observation retains cache/fresh provenance outside scoring.
    """
    def __init__(self, image, program, directory, *, create_seconds=60,
                 attach_seconds=30, execution_seconds=10, control_seconds=15,
                 attempts=2, invoke=None):
        if attempts < 1 or min(create_seconds, attach_seconds, execution_seconds, control_seconds) <= 0:
            raise ValueError("Reader bounds and attempts must be positive.")
        self.image, self.program = image, program
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.create_seconds, self.attach_seconds = create_seconds, attach_seconds
        self.execution_seconds, self.control_seconds = execution_seconds, control_seconds
        self.attempts = attempts
        self.invoke = invoke or subprocess.run
        self.wrapper = ('import sys\nsys.stderr.write("SWH_READER_READY\\n");sys.stderr.flush()\n'
                        + program + '\nsys.stderr.write("SWH_READER_DONE\\n");sys.stderr.flush()\n')
        self.program_hash = sha256(program.encode()).hexdigest()
        self.wrapper_hash = sha256(self.wrapper.encode()).hexdigest()
        self.names = []
        self.last_provenance = None

    def _record(self, value):
        with (self.directory / 'lifecycle.jsonl').open('ab') as out:
            out.write(canonical({'at': utc(), **value}) + b'\n')
            out.flush()
            os.fsync(out.fileno())

    def _command(self, args, seconds, *, data=None, phase, name):
        begin = time.monotonic()
        self._record({'kind': 'stage_started', 'phase': phase, 'container': name,
                      'timeout_seconds': seconds})
        try:
            result = self.invoke(args, input=data, capture_output=True, timeout=seconds)
            self._record({'kind': 'stage_finished', 'phase': phase, 'container': name,
                          'elapsed_seconds': time.monotonic() - begin,
                          'returncode': result.returncode,
                          'stdout_bytes': len(result.stdout or b''),
                          'stderr_bytes': len(result.stderr or b'')})
            return result
        except subprocess.TimeoutExpired as error:
            self._record({'kind': 'stage_timeout', 'phase': phase, 'container': name,
                          'elapsed_seconds': time.monotonic() - begin,
                          'stdout_bytes': len(error.stdout or b''),
                          'stderr_bytes': len(error.stderr or b'')})
            raise

    def _inspect(self, name):
        value = self._command(['docker', 'inspect', name], self.control_seconds,
                              phase='inspect', name=name)
        if value.returncode:
            if b'no such' in value.stderr.lower():
                return None
            raise ReaderFailure('docker_control', 'inspect', 'Container state could not be read.')
        item = json.loads(value.stdout)[0]
        # Do not journal host config/env; only this owned container's lifecycle.
        state = {k: item['State'].get(k) for k in
                 ('Status', 'Running', 'ExitCode', 'OOMKilled', 'StartedAt', 'FinishedAt', 'Error')}
        self._record({'kind': 'container_state', 'container': name, 'state': state})
        return state

    def _cleanup(self, name):
        result = self._command(['docker', 'rm', '-f', name], self.control_seconds,
                               phase='remove', name=name)
        if result.returncode and b'no such' not in result.stderr.lower():
            raise ReaderFailure('cleanup_unconfirmed', 'remove', 'Owned reader removal failed.')
        if self._inspect(name) is not None:
            raise ReaderFailure('cleanup_unconfirmed', 'inspect', 'Owned reader still exists.')
        self._record({'kind': 'cleanup_verified', 'container': name})

    def _validate(self, text, values):
        objects = []
        for line in text.splitlines():
            try:
                value = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict) and set(value) == {'downloads', 'recovered_records'}:
                objects.append(value)
        if len(objects) != 1:
            raise ReaderFailure('invalid_output', 'decode', 'Reader did not return one complete receipt.')
        result = objects[0]
        if not isinstance(result['downloads'], list) or not isinstance(result['recovered_records'], list):
            raise ReaderFailure('invalid_output', 'decode', 'Reader receipt has invalid arrays.')
        expected = {p: {'path': p, 'sha256': sha256(base64.b64decode(v, validate=True)).hexdigest(),
                        'bytes': len(base64.b64decode(v, validate=True))} for p, v in values.items()}
        actual = {v.get('path'): v for v in result['downloads'] if isinstance(v, dict)}
        if len(actual) != len(result['downloads']) or actual != expected:
            raise ReaderFailure('invalid_output', 'decode', 'Public download hashes differ from submitted bytes.')
        for row in result['recovered_records']:
            if not isinstance(row, dict) or set(row) != {'path', 'record'} or row['path'] not in expected or not isinstance(row['record'], dict):
                raise ReaderFailure('invalid_output', 'decode', 'Recovered row provenance is invalid.')
        return result

    def _fresh(self, values, token, attempt):
        name = 'sh-public-reader-' + secrets.token_hex(8)
        self.names.append(name)
        args = ['docker', 'create', '--interactive', '--pull=never', '--name', name,
                '--label', 'org.swarmharm.public-reader=infra-v1', '--network=none', '--read-only',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user', '65534:65534',
                '--memory=256m', '--cpus=1', '--pids-limit=64',
                '--tmpfs', '/tmp:rw,nosuid,nodev,size=16m,mode=1777', self.image,
                'timeout', '--kill-after=1s', str(self.execution_seconds) + 's',
                'python', '-I', '-c', self.wrapper]
        phase = 'create'
        result, recovered = None, False
        failure = None
        self._record({'kind': 'attempt_started', 'key': token, 'attempt': attempt, 'container': name})
        try:
            created = self._command(args, self.create_seconds, phase=phase, name=name)
            if created.returncode:
                raise ReaderFailure('docker_control', phase, 'Docker create failed: ' + created.stderr.decode(errors='replace')[:300])
            phase = 'attach'
            try:
                attached = self._command(['docker', 'start', '-a', '-i', name], self.attach_seconds,
                                         data=canonical(values), phase=phase, name=name)
            except subprocess.TimeoutExpired:
                state = self._inspect(name)
                if state and not state['Running'] and state['Status'] == 'exited' and state['ExitCode'] == 0:
                    logs = self._command(['docker', 'logs', name], self.control_seconds, phase='recover_logs', name=name)
                    if logs.returncode:
                        raise ReaderFailure('docker_control', 'recover_logs', 'Exited consumer logs unavailable.')
                    result = self._validate(logs.stdout + b'\n' + logs.stderr, values)
                    recovered = True
                    self._record({'kind': 'completed_result_recovered', 'key': token, 'container': name})
                elif state and state['ExitCode'] in (124, 137) and not state['Running']:
                    raise ReaderFailure('execution_timeout', 'execution', 'Consumer input/decoding exceeded its in-container execution bound.')
                else:
                    raise ReaderFailure('attach_timeout', phase, 'Docker start/attach timed out before a complete result was recoverable.')
            else:
                if attached.returncode in (124, 137):
                    self._inspect(name)
                    raise ReaderFailure('execution_timeout', 'execution', 'Consumer input/decoding exceeded its in-container execution bound.')
                if attached.returncode:
                    self._inspect(name)
                    raise ReaderFailure('consumer_failed', 'execution', 'Consumer exited nonzero: ' + attached.stderr.decode(errors='replace')[:300])
                result = self._validate(attached.stdout, values)
        except subprocess.TimeoutExpired:
            failure = ReaderFailure(phase + '_timeout', phase, 'Docker lifecycle operation timed out.')
        except ReaderFailure as error:
            failure = error
        except Exception as error:
            failure = ReaderFailure('unexpected_reader_error', phase, type(error).__name__ + ': ' + str(error)[:300])
        finally:
            try:
                self._cleanup(name)
            except Exception as error:
                raise ReaderFailure('cleanup_unconfirmed', 'cleanup', 'Reader cleanup could not be confirmed.',
                                    {'container': name, 'cause_type': type(error).__name__}) from error
        if failure:
            self._record({'kind': 'attempt_failed', 'key': token, 'attempt': attempt,
                          'failure_kind': failure.kind, 'phase': failure.phase, 'container': name})
            raise failure
        result['execution'] = {'image': self.image, 'network': 'none', 'user': '65534:65534',
                               'host_mounts': False, 'credentials': False, 'owned_container_removed': True}
        return result, {'container': name, 'attempts': attempt, 'recovered_from_logs': recovered}

    def read(self, shared, *, force_fresh=False):
        self.last_provenance = None
        values = {p: f['data'] for p, f in sorted(shared.items())}
        identity = {'image': self.image, 'program_sha256': self.program_hash,
                    'wrapper_sha256': self.wrapper_hash, 'execution_seconds':self.execution_seconds, 'public_files': values}
        token = sha256(canonical(identity)).hexdigest()
        path = self.directory / 'receipts' / (token + '.json')
        if path.exists() and not force_fresh:
            try:
                receipt = json.loads(path.read_text())
                if receipt['key'] != token or sha256(canonical(receipt['result'])).hexdigest() != receipt['result_sha256']:
                    raise ReaderFailure('cache_invalid', 'cache', 'Stored public receipt checksum differs.')
                result = receipt['result']
                self._validate(canonical({k: result[k] for k in ('downloads', 'recovered_records')}), values)
                receipt['verified_execution']
            except (ValueError,KeyError,TypeError) as error:
                raise ReaderFailure('cache_invalid','cache','Stored public receipt is malformed.') from error
            provenance = {'key': token, 'cache_hit': True, 'result_sha256': receipt['result_sha256'],
                          'verified_execution': receipt['verified_execution']}
        else:
            for attempt in range(1, self.attempts + 1):
                try:
                    result, execution = self._fresh(values, token, attempt)
                    break
                except ReaderFailure as error:
                    if error.kind not in ('create_timeout', 'attach_timeout', 'docker_control') or attempt == self.attempts:
                        raise
                    self._record({'kind': 'reader_only_retry', 'key': token, 'after_attempt': attempt,
                                  'failure_kind': error.kind, 'model_calls_retried': 0})
            receipt = {'key': token, 'result': result, 'result_sha256': sha256(canonical(result)).hexdigest(),
                       'verified_execution': execution, 'program_sha256': self.program_hash, 'image': self.image}
            # Do not overwrite an existing successful receipt when explicitly replaying it.
            if not path.exists():
                atomic_json(path, receipt)
            elif json.loads(path.read_text())['result_sha256'] != receipt['result_sha256']:
                raise ReaderFailure('nondeterministic_result', 'cache', 'Fresh replay differs from original public receipt.')
            provenance = {'key': token, 'cache_hit': False, 'result_sha256': receipt['result_sha256'],
                          'verified_execution': execution}
        self.last_provenance = deepcopy(provenance)
        self._record({'kind': 'observation', **provenance})
        return deepcopy(result)

    def close(self):
        for name in self.names:
            self._cleanup(name)
