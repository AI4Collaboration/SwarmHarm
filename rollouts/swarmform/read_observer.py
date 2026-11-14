"""Protected command observations for the actual file-volume fixture."""

import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import os
import secrets
import gzip
import subprocess
import time
from tempfile import NamedTemporaryFile
from collections.abc import Mapping

from atomic import atomic_json
from swarmform.file_deployment import FileStation
from swarmform.workstation import IMAGE
from swarmform.strace_timing import FORMAT, HOST_CLOCK, current_command, legacy_line

TRACE_ROOT = "/var/log/workstation"
CHUNK_BYTES = 1024 * 1024


READ_LOGS = r"""
import hashlib,json,os,sys,time
from pathlib import Path
root=Path('/var/log/workstation')
previous=json.load(sys.stdin)
opened=set()
for process in Path('/proc').iterdir():
    if not process.name.isdigit():continue
    try:
        for fd in (process/'fd').iterdir():
            try:opened.add(os.readlink(fd))
            except OSError:pass
    except OSError:pass
files=[]
for p in sorted(root.iterdir()):
    if not p.is_file():continue
    stat=p.stat()
    prior=previous.get(p.name)
    offset=prior['bytes'] if prior else 0
    if stat.st_size<offset:raise RuntimeError('Command observation shrank')
    if prior and prior['identity']!={'device':stat.st_dev,'inode':stat.st_ino}:
        raise RuntimeError('Command observation file identity changed')
    digest=hashlib.sha256()
    with p.open('rb') as source:
        remaining=offset
        while remaining:
            data=source.read(min(1024*1024,remaining))
            if not data:raise RuntimeError('Command observation shrank')
            digest.update(data);remaining-=len(data)
        if prior and digest.hexdigest()!=prior['sha256']:
            raise RuntimeError('Command observation prefix changed')
        source.seek(max(0,stat.st_size-1))
        last=source.read(1)
    files.append({'name':p.name,'bytes':stat.st_size,'offset':offset,
                  'device':stat.st_dev,'inode':stat.st_ino,
                  'complete_line':not stat.st_size or last==b'\n'})
try:time_namespace=os.readlink('/proc/self/ns/time')
except OSError:time_namespace=None
clock={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
       'time_namespace':time_namespace,'implementation':time.get_clock_info('monotonic').implementation,
       'resolution_seconds':repr(time.get_clock_info('monotonic').resolution)}
header={'files':files,'closed':[item['name'] for item in files if str(root/item['name']) not in opened],
        'guest_clock':clock}
output=sys.stdout.buffer
output.write(json.dumps(header).encode()+b'\n')
for item in files:
    with (root/item['name']).open('rb') as stream:
        stream.seek(item['offset'])
        remaining=item['bytes']-item['offset']
        while remaining:
            data=stream.read(min(1024*1024,remaining))
            if not data:raise RuntimeError('Command observation shrank during capture')
            output.write(data);remaining-=len(data)
output.flush()
"""
PRUNE_LOGS = r"""
import hashlib,json
from pathlib import Path
for name,digest in json.load(__import__('sys').stdin).items():
    if Path(name).name!=name:raise ValueError('Invalid observation filename')
    p=Path('/var/log/workstation')/name
    if not p.exists():continue
    with p.open('rb') as stream:
        actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=digest:raise ValueError('Closed observation changed')
    p.unlink()
"""


def store_chunk(directory, data):
    digest = sha256(data).hexdigest()
    destination = directory / (digest + ".gz")
    if destination.exists():
        with gzip.open(destination, "rb") as stream:
            if stream.read(CHUNK_BYTES + 1) != data:
                raise RuntimeError("Archived observation chunk changed")
    else:
        with NamedTemporaryFile(dir=directory, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            try:
                with gzip.GzipFile(
                    fileobj=temporary, mode="wb", compresslevel=1, mtime=0
                ) as compressed:
                    compressed.write(data)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path.replace(destination)
            finally:
                temporary_path.unlink(missing_ok=True)
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return {"blob": "chunks/" + destination.name, "bytes": len(data), "sha256": digest}


def trace_blocks(archive, record):
    """Read both original uncompressed receipts and chunked receipts."""
    digest = sha256()
    size = 0
    if "chunks" in record:
        for chunk in record["chunks"]:
            with gzip.open(Path(archive) / chunk["blob"], "rb") as source:
                data = source.read(chunk["bytes"] + 1)
            if (
                len(data) != chunk["bytes"]
                or sha256(data).hexdigest() != chunk["sha256"]
            ):
                raise RuntimeError(
                    "Archived observation chunk failed its integrity check"
                )
            digest.update(data)
            size += len(data)
            yield data
    else:
        with (Path(archive) / record["blob"]).open("rb") as source:
            while data := source.read(CHUNK_BYTES):
                digest.update(data)
                size += len(data)
                yield data
    if size != record["bytes"] or digest.hexdigest() != record["sha256"]:
        raise RuntimeError("Archived command observation failed its integrity check")


def observed_reads(log):
    """Extract complete scalar reads only; path presence alone never earns a read."""
    pattern = re.compile(
        r'^(\d+)\s+(\d+\.\d+)\s+(read|pread64)\(\d+<([^>]+)>, "((?:\\x[0-9a-f]{2})*)", (\d+)(?:, (\d+))?\) = (\d+)$'
    )
    reads = []
    for number, line in enumerate(log.splitlines(), 1):
        match = pattern.fullmatch(legacy_line(line))
        if not match:
            continue
        pid, timestamp, operation, raw_path, raw_bytes, requested, offset, returned = (
            match.groups()
        )
        path = re.sub(r"\\x([0-9a-f]{2})", lambda m: chr(int(m[1], 16)), raw_path)
        data = bytes.fromhex(raw_bytes.replace("\\x", ""))
        if not path.startswith(("/workspace/", "/var/tmp/exports/", "/tmp/")) or len(
            data
        ) != int(returned):
            continue
        reads.append(
            {
                "line": number,
                "pid": int(pid),
                "at_unix": timestamp,
                "operation": operation,
                "path": path,
                "requested_bytes": int(requested),
                "returned_bytes": len(data),
                "explicit_offset": int(offset) if offset is not None else None,
                "data_base64": base64.b64encode(data).decode(),
                "sha256": sha256(data).hexdigest(),
            }
        )
    return reads


class ObservedFileStation(FileStation):
    """The observer retains process reads; native traces still establish model exposure."""

    def __init__(self, initial_files, *, archive, **kwargs):
        self.configure_archive(archive)
        self.observation_volume = "office-observation-" + secrets.token_hex(8)
        self.observation_volume_removed = False
        subprocess.run(
            [
                "docker",
                "volume",
                "create",
                "--label",
                "org.swarmharm.managed=true",
                "--label",
                f"org.swarmharm.owner-pid={os.getpid()}",
                self.observation_volume,
            ],
            capture_output=True,
            check=True,
            timeout=20,
        )
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--mount",
                    f"type=volume,src={self.observation_volume},dst={TRACE_ROOT}",
                    IMAGE,
                    "python",
                    "-I",
                    "-c",
                    f"import os;os.chmod({TRACE_ROOT!r},0o700)",
                ],
                capture_output=True,
                check=True,
                timeout=20,
            )
            super().__init__(
                initial_files,
                trace_commands=True,
                trace_volume=self.observation_volume,
                **kwargs,
            )
        except BaseException:
            self.remove_observation_volume()
            raise
        try:
            self.observer_version = subprocess.check_output(
                ["docker", "exec", self.name, "strace", "--version"],
                text=True,
                timeout=10,
            ).splitlines()[0]
        except BaseException:
            self.close()
            raise

    def configure_archive(self, archive):
        self.archive = Path(archive).resolve()
        repo = Path(__file__).resolve().parents[2]
        if self.archive.is_relative_to(repo) or self.archive.exists():
            raise ValueError(
                "Choose a new observation directory outside the repository"
            )
        self.archive.mkdir(parents=True)
        self.command_count = self.capture_count = 0
        self.trace_files = {}
        self.trace_origins = {}
        self.observer_identity = secrets.token_hex(16)
        self.previous = ArchivedTraces(self.archive, self.trace_files)
        self.pruned = set()
        self.trace_hashes = {}
        self.terminal_captured = False

    def command_argv(self, command):
        self.command_count += 1
        original_hash = sha256(command.encode()).hexdigest()
        if self.creation_mask:
            command = "umask " + self.creation_mask + "\n" + command
        # This is before subprocess launch, in the collector's host process.
        # The immutable origin remains attached when a later command captures
        # this trace's still-running background descendants.
        if not hasattr(self, "trace_origins"):
            self.trace_origins = {}
            self.observer_identity = secrets.token_hex(16)
        name = f"{self.command_count:06d}.log"
        self.trace_origins[name] = {
            "trace_id": self.observer_identity + ":" + name,
            "command_ordinal": self.command_count,
            "trace_file": name,
            "station": self.name,
            "command_sha256": original_hash,
            "traced_shell_sha256": sha256(command.encode()).hexdigest(),
            "launch_before_ns": time.monotonic_ns(),
            "host_clock_domain": HOST_CLOCK["domain"],
            "native_call": current_command() or None,
        }
        atomic_json(self.archive / "origins.json", self.trace_origins)
        return [
            "docker",
            "exec",
            "--user",
            "0:0",
            "--workdir",
            "/workspace",
            self.name,
            *getattr(self, "account_view", ()),
            "strace",
            "-DDD",
            "-f",
            "-ttt",
            "--relative-timestamps=ns",
            "-yy",
            "-s",
            "262144",
            "-xx",
            # Pathname Unix sockets can cross a shared volume even with
            # network=none. Keep their actual send/receive operations.
            "-e",
            "trace=%file,%desc,%process,%memory,%network",
            "-e",
            "abbrev=!getdents64",
            "-o",
            f"{TRACE_ROOT}/{self.command_count:06d}.log",
            "-u",
            f"{self.business_uid}:{self.business_gid}",
            "timeout",
            "--kill-after=1s",
            "30s",
            "bash",
            "-lc",
            command,
        ]

    def remove_observation_volume(self):
        if not self.observation_volume_removed:
            subprocess.run(
                ["docker", "volume", "rm", self.observation_volume],
                capture_output=True,
                check=True,
                timeout=20,
            )
            self.observation_volume_removed = True

    def retain_traces(self):
        chunks = self.archive / "chunks"
        chunks.mkdir(exist_ok=True)
        previous = {
            name: {
                "bytes": row["bytes"],
                "sha256": row["sha256"],
                "identity": row["timing"]["file_identity"],
            }
            for name, row in self.trace_files.items()
            if name not in self.pruned
        }
        argv = [
            "docker",
            "exec",
            "-i",
            "--user",
            "0:0",
            self.name,
            *getattr(self, "account_view", ()),
            "python",
            "-I",
            "-c",
            READ_LOGS,
        ]
        started = time.monotonic_ns()
        with NamedTemporaryFile(dir=self.archive) as errors:
            with subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors
            ) as process:
                try:
                    process.stdin.write(json.dumps(previous).encode())
                    process.stdin.close()
                    receipt = self.archive_capture(process.stdout, started)
                    if process.wait() != 0:
                        errors.seek(0)
                        raise RuntimeError(
                            "Observation transfer failed: "
                            + errors.read(4000).decode(errors="replace")
                        )
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
        return self.commit_capture(*receipt, started)

    def archive_capture(self, capture, started):
        header = capture.readline(1024 * 1024)
        if not header.endswith(b"\n"):
            raise RuntimeError("Incomplete observation header")
        observed = json.loads(header)
        pending = dict(self.trace_files)
        hashes = dict(self.trace_hashes)
        seen = set()
        incomplete = []
        guest_clock = observed.get("guest_clock")
        guest_domain = sha256(
            json.dumps(guest_clock, sort_keys=True).encode()
        ).hexdigest()
        for item in observed["files"]:
            name, size, offset = item["name"], item["bytes"], item["offset"]
            if (
                Path(name).name != name
                or name in seen
                or type(size) is not int
                or not 0 <= offset <= size
            ):
                raise RuntimeError("Invalid command observation header")
            seen.add(name)
            if name in self.pruned:
                raise RuntimeError("A closed command observation was reopened")
            prior = self.trace_files.get(name)
            if offset != (prior["bytes"] if prior else 0):
                raise RuntimeError("Command observation offset changed")
            identity = {"device": item["device"], "inode": item["inode"]}
            if prior and prior["timing"]["file_identity"] != identity:
                raise RuntimeError("Command observation identity changed")
            digest = hashes[name].copy() if name in hashes else sha256()
            parts = list(prior["chunks"]) if prior else []
            remaining = size - offset
            while remaining:
                data = capture.read(min(CHUNK_BYTES, remaining))
                if not data:
                    raise RuntimeError("Command observation capture is incomplete")
                parts.append(store_chunk(self.archive / "chunks", data))
                digest.update(data)
                remaining -= len(data)
            closed = name in observed["closed"]
            if closed and not item["complete_line"]:
                incomplete.append(name)
            origin = self.trace_origins.get(name)
            pending[name] = {
                "bytes": size,
                "sha256": digest.hexdigest(),
                "chunks": parts,
                "storage": "gzip-chunks-v1",
                "timing": {
                    "format": FORMAT,
                    "origin": origin,
                    "prefix_from_byte_zero": True,
                    "single_tracer": origin is not None,
                    "file_identity": identity,
                    "closed": closed,
                    "capture": {
                        "sequence": self.capture_count + 1,
                        "started_ns": started,
                        "completed_ns": time.monotonic_ns(),
                        "host_clock_domain": HOST_CLOCK["domain"],
                        "guest_clock_domain": guest_domain,
                    },
                },
            }
            hashes[name] = digest
        if capture.read(1):
            raise RuntimeError("Unexpected bytes after command observation capture")
        missing = set(self.trace_files) - seen - self.pruned
        if any(not self.trace_files[name]["timing"]["closed"] for name in missing):
            raise RuntimeError("An unarchived command observation disappeared")
        return observed, pending, hashes, incomplete

    def commit_capture(self, observed, pending, hashes, incomplete, started):
        record = {
            "commands_started": self.command_count,
            "observer": getattr(self, "observer_version", None),
            "files": pending,
            "claim_scope": "process_operations_not_model_comprehension",
            "incomplete_closed_logs": incomplete,
            "timing_schema": 1,
            "host_clock": HOST_CLOCK,
            "guest_clock": observed.get("guest_clock"),
            "storage": {
                "kind": "gzip-chunks-v1",
                "chunk_bytes": CHUNK_BYTES,
                "captured_bytes": sum(r["bytes"] for r in pending.values()),
                "transferred_bytes": sum(
                    r["bytes"] - r["offset"] for r in observed["files"]
                ),
            },
        }
        path = self.archive / f"{self.capture_count + 1:06d}.json"
        atomic_json(path, record)
        self.capture_count += 1
        self.trace_files.clear()
        self.trace_files.update(pending)
        self.trace_hashes = hashes
        if incomplete:
            raise RuntimeError(
                "Closed command observation is truncated: " + ",".join(incomplete)
            )
        closed = {name: pending[name]["sha256"] for name in observed["closed"]}
        if closed and getattr(self, "prune_archived", True):
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    "--user",
                    "0:0",
                    self.name,
                    *getattr(self, "account_view", ()),
                    "python",
                    "-I",
                    "-c",
                    PRUNE_LOGS,
                ],
                input=json.dumps(closed),
                text=True,
                capture_output=True,
                check=True,
                timeout=180,
            )
            self.pruned.update(closed)
        return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}

    def execute(self, command, shared):
        self.terminal_captured = False
        before = self.command_count
        result, snapshot = super().execute(command, shared)
        snapshot["command_observation"] = self.retain_traces()
        snapshot["command_observation"]["started_traces"] = [
            self.trace_origins[f"{n:06d}.log"]
            for n in range(before + 1, self.command_count + 1)
        ]
        return result, snapshot

    def capture_terminal(self):
        if self.terminal_captured or self.closed or not self.initialized:
            return
        errors = []
        try:
            self.capture_frozen("terminal")
        except BaseException as error:
            errors.append(error)
        try:
            self.retain_traces()
        except BaseException as error:
            errors.append(error)
        if errors:
            raise BaseExceptionGroup(
                "Terminal observation capture failed; originals retained", errors
            )
        self.terminal_captured = True

    def close(self):
        if self.closed and self.observation_volume_removed:
            return
        self.capture_terminal()
        if not self.closed:
            removed = subprocess.run(
                ["docker", "rm", "-f", self.name], capture_output=True, timeout=20
            )
            if removed.returncode and b"No such container" not in removed.stderr:
                raise RuntimeError("Workstation removal unconfirmed")
            self.closed = True
        self.remove_observation_volume()


class ArchivedTraces(Mapping):
    """Load an explicitly requested trace; closed logs need only their receipts in RAM."""

    def __init__(self, archive, files):
        self.archive, self.files = archive, files

    def __getitem__(self, name):
        record = self.files[name]
        return b"".join(trace_blocks(self.archive, record))

    def __iter__(self):
        return iter(self.files)

    def __len__(self):
        return len(self.files)
