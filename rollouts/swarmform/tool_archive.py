"""Join durable mapped-memory tool results to their original command archives after shutdown."""

from contextvars import ContextVar
import gzip
from io import BytesIO
import zlib
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

on_result = ContextVar("mapped_result_available", default=None)
PENDING = "tool_result_pending"


def _receipt(path, origins, verify):
    from .read_observer import trace_blocks

    raw = path.read_bytes()
    receipt = json.loads(raw)
    for origin in origins:
        key = origin["trace_file"]
        record = receipt["files"].get(key)
        if not record or record["timing"]["origin"] != origin or key in receipt["incomplete_closed_logs"]:
            raise ValueError(f"Unresolved observed command {origin['trace_id']} in {path}")
        if verify:
            for _ in trace_blocks(path.parent, record):
                pass
    return {"path": str(path), "sha256": sha256(raw).hexdigest(), "started_traces": origins}


def _durable_rows(path, notes):
    # emit() fsyncs a separate gzip member per event. A killed process can leave
    # an incomplete final member, even one containing a newline but no checksum.
    decoder = zlib.decompressobj(31)
    buffer = BytesIO()
    partial = False
    with path.open("rb") as stream:
        while data := stream.read(131072):
            while data:
                partial = True
                buffer.write(decoder.decompress(data))
                data = decoder.unused_data
                if decoder.eof:
                    buffer.seek(0)
                    yield from buffer
                    decoder, buffer, partial = zlib.decompressobj(31), BytesIO(), False
    if partial:
        notes["discarded_uncommitted_final_member"] = True


def finish(actor_file, completed=None, *, output=None, recovered=None, notes=None):
    """Keep publication order. Only recovery can substitute a verified post-stop receipt."""
    recovery = output is not None
    if not recovery and not completed:
        return
    destination = output or actor_file
    src = Path(actor_file)
    notes = notes if notes is not None else {}
    if recovery and (not src.exists() or not any(b'"kind":"tool_result_pending"' in line[:48]
                                                  for line in _durable_rows(src, notes))):
        return
    with NamedTemporaryFile(dir=destination.parent, prefix=".tool-archive-", delete=False) as raw:
        tmp = Path(raw.name)
    found = False
    try:
        with gzip.open(src, "rb") as source, tmp.open("wb") as raw:
            for line in (_durable_rows(src, notes) if recovery else source):
                if b'"kind":"tool_result_pending"' in line[:48]:
                    row = json.loads(line)
                    if row["kind"] == PENDING:
                        found = True
                        path = Path(row.pop("expected_receipt"))
                        origins = row.pop("started_traces")
                        for origin in origins:
                            if origin["native_call"] != {"actor": src.name.split(".")[0], "call_id": row["call_id"]}:
                                raise ValueError("Original command identity differs from the durable result")
                        if recovery:
                            # Recovery can run after the original cohort directory was moved.
                            paths = [src.parent / "reads" / src.name.split(".")[0] / path.name]
                            if recovered:
                                paths.extend(sorted(recovered.glob("[0-9]*.json"), reverse=True))
                            for candidate in paths:
                                try:
                                    ref = _receipt(candidate, origins, verify=True)
                                    break
                                except (FileNotFoundError, ValueError, KeyError, RuntimeError):
                                    continue
                            else:
                                raise RuntimeError(f"Missing verified command archive for {path}")
                            timing = None  # The worker could have died before measuring its return.
                        else:
                            if not completed.get(str(path)):
                                raise RuntimeError(f"Missing command archive for {path}")
                            expected, timing = completed[str(path)]
                            ref = _receipt(path, origins, verify=False)
                            if ref["sha256"] != expected:
                                raise ValueError(f"Command archive digest changed: {path}")
                        row.update(kind="tool_result", command_observation=ref, timing=timing)
                        line = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                # Preserve the original one-member-per-event layout so recovery
                # memory is bounded by the largest event, even for sealed actors.
                raw.write(gzip.compress(line, compresslevel=1, mtime=0))
            if not found:
                return
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(tmp, destination)
        fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        tmp.unlink(missing_ok=True)

