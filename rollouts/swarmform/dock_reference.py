"""Run the deployed DuckDB terminal from this workstation."""
import os
import platform
import sys

if platform.machine() in {"aarch64", "arm64"}:
    import ctypes

    os.environ.setdefault("QEMU_GUEST_BASE", "0x800000000000")
    # DuckDB sizes its worker pool from CPU affinity. Keep the emulator on one
    # allowed CPU, preserving the Linux scheduler's placement across workstations.
    allowed = sorted(os.sched_getaffinity(0))
    get_cpu = getattr(ctypes.CDLL(None), "sched_getcpu", None)
    cpu = get_cpu() if get_cpu is not None else -1
    if cpu not in allowed:
        cpu = allowed[os.getpid() % len(allowed)]
    os.sched_setaffinity(0, {cpu})
command = "/opt/programbench/invoke"
os.execv(command, [command, "duckdb__duckdb.bdb65ec", *sys.argv[1:]])
