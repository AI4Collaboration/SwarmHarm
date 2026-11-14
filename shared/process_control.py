"""Wait for evidence-preserving child shutdown on operator interruption."""

import signal
import subprocess


def run_process(command, **kwargs):
    """Forward termination but wait for the collector's evidence cleanup."""
    interrupted = None
    child = None

    def stop(signum, frame):
        nonlocal interrupted
        interrupted = signal.Signals(signum).name
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass

    previous = {
        sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        with subprocess.Popen(command, **kwargs) as child:
            if interrupted:
                child.send_signal(getattr(signal, interrupted))
            code = child.wait()
        return code, interrupted
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
