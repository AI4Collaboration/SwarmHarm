from contextlib import contextmanager

from contextvars import ContextVar

import os

import re

import secrets

import time

RELATIVE = re.compile(r'^(\d+)\s+(\d+\.\d+)\s+\(\+\s*(\d+)\.(\d{9})\) (.+)$')

FORMAT = 'strace-6.13-ttt-relative-ns-single-output-v1'

HOST_CLOCK = {'domain': 'host-process-'+str(os.getpid())+'-'+secrets.token_hex(16),
              'implementation': time.get_clock_info('monotonic').implementation,
              'resolution_seconds': repr(time.get_clock_info('monotonic').resolution)}

_COMMAND = ContextVar('strace_command_binding', default=None)

@contextmanager
def command_binding(**values):
    """Thread-local original native identity; later background captures keep it."""
    token = _COMMAND.set(dict(values))
    try:
        yield
    finally:
        _COMMAND.reset(token)

def current_command():
    return dict(_COMMAND.get() or {})

def legacy_line(line):
    """Return a parser view only; do not write this view into evidence archives."""
    match = RELATIVE.fullmatch(line)
    if match is None:
        return line
    pid, wall, _, _, body = match.groups()
    return f'{pid} {wall} {body}'
