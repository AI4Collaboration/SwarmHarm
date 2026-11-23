"""Socket artifact service with scoped accounts and private client networks."""

import base64
from contextlib import ExitStack
import json
from ipaddress import IPv4Network
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from swarmform.file_deployment import FileDeployment, WORKSTATION_ENVIRONMENT
from swarmform.read_observer import ObservedFileStation
from swarmform.workstation import IMAGE
from swarmform.service_workstation import ServiceWorkstation


def command(argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=30)


def create_private_network(name):
    # Each network has just a client and service. Docker's automatic /16 pools
    # can run out before N=32, so allocate small, non-overlapping internal nets.
    for _ in range(128):
        subnet = IPv4Network(((10 << 24) | (secrets.randbits(21) << 3), 29))
        try:
            command(
                [
                    "docker",
                    "network",
                    "create",
                    "--internal",
                    "--subnet",
                    str(subnet),
                    "--label",
                    "org.swarmharm.managed=true",
                    "--label",
                    f"org.swarmharm.owner-pid={os.getpid()}",
                    name,
                ]
            )
            return
        except subprocess.CalledProcessError as error:
            if "Pool overlaps" not in (error.stderr or ""):
                raise
    raise RuntimeError("Could not allocate a free private network subnet")


class SocketStation(ObservedFileStation):
    def command_argv(self, command):
        return [
            value + ",%network"
            if value == "trace=%file,%desc,%process,%memory"
            else value
            for value in super().command_argv(command)
        ]


class SocketDeployment(FileDeployment):
    observed_station_class = SocketStation
    connection_path = "/workspace/project-access.json"
    service_url = "http://projects:8080"
    service_alias = "projects"

    def service_files(self, accounts):
        return {
            "/workspace/formation_store.py": Path(__file__)
            .with_name("formation_store.py")
            .read_text(),
            "/workspace/formation_service.py": Path(__file__)
            .with_name("formation_service.py")
            .read_text(),
            "/workspace/server.py": "from formation_service import serve\nserve()\n",
            "/workspace/accounts.json": json.dumps(accounts),
        }

    def __init__(
        self, startup, *, shared=True, observation_sink=None, observation_archive=None, project_artifacts=None
    ):
        if not startup or type(shared) is not bool:
            raise ValueError("Expected workstations and a shared/private service scope")
        if observation_archive is None:
            raise ValueError(
                "Socket service requires an external observation directory"
            )
        self.resources = ExitStack()
        self.closed = False
        self.stations = {}
        self.volumes = {}
        self.locks = {a: threading.RLock() for a in startup}
        self.networks = {}
        accounts = {}
        self.terminal_service = None
        try:
            for actor, files in startup.items():
                config = json.loads(files[self.connection_path])
                if config["url"] != self.service_url:
                    raise ValueError("Unexpected socket service address")
                if config["key"] in accounts:
                    raise ValueError("Account identities must differ")
                accounts[config["key"]] = {
                    "actor": actor,
                    "scope": "office" if shared else actor,
                }
                network = "office-network-" + secrets.token_hex(8)
                create_private_network(network)
                self.resources.callback(self._remove_network, network)
                self.networks[actor] = network
            initial = self.service_files(accounts)
            if project_artifacts:
                from swarmform.formation_store import apply
                state = {"objects": {}}
                seeded = {}
                for name, body in project_artifacts.items():
                    data = base64.b64encode(body.encode()).decode()
                    seeded[name] = apply(state, {"operation": "write", "name": name, "data": data})["sha256"]
                scopes = {account["scope"]: state for account in accounts.values()}
                initial["/workspace/project-store.json"] = json.dumps(scopes)
                initial["/workspace/project-seeds.json"] = json.dumps(seeded)
            first = next(iter(self.networks.values()))
            self.service_volume = self._volume()
            self.service = ServiceWorkstation(
                {p: base64.b64encode(t.encode()).decode() for p, t in initial.items()},
                archive=Path(observation_archive) / "_service",
                named_volumes=((self.service_volume, "/var/tmp/exports"),),
                network=first,
                process_lifecycle="continuous",
                environment=WORKSTATION_ENVIRONMENT,
                registry_enabled=False,
            )
            # Added before the station callbacks: their removal happens first.
            self.resources.callback(self._close_service)
            command(["docker", "network", "disconnect", first, self.service.name])
            for network in self.networks.values():
                command(
                    [
                        "docker",
                        "network",
                        "connect",
                        "--alias",
                        self.service_alias,
                        network,
                        self.service.name,
                    ]
                )
            result, _ = self.service.execute(
                "python server.py </dev/null >/workspace/service.log 2>&1 &", {}
            )
            if result["exit_code"] != 0:
                raise RuntimeError(result)
            for actor, files in startup.items():
                sink = (
                    (
                        lambda phase, value, actor=actor: observation_sink(
                            actor, phase, value
                        )
                    )
                    if observation_sink
                    else None
                )
                cls, extra = (
                    self.observed_station_class,
                    {"archive": Path(observation_archive) / actor},
                )
                volume = self._volume()
                self.volumes[actor] = volume
                station = cls(
                    {
                        p: base64.b64encode(t.encode()).decode()
                        for p, t in files.items()
                    },
                    network=self.networks[actor],
                    environment=WORKSTATION_ENVIRONMENT,
                    process_lifecycle="continuous",
                    observation_sink=sink,
                    named_volumes=((volume, "/var/tmp/exports"),),
                    registry_enabled=False,
                    **extra,
                )
                self.resources.callback(station.close)
                self.stations[actor] = station
            self.bindings = {}
            for actor, station in self.stations.items():
                row = json.loads(command(["docker", "inspect", station.name]).stdout)[0]
                network = row["NetworkSettings"]["Networks"]
                mounts = [
                    m
                    for m in row["Mounts"]
                    if m["Type"] == "volume" and m["Destination"] == "/var/tmp/exports"
                ]
                observation_mounts = [
                    m
                    for m in row["Mounts"]
                    if m["Type"] == "volume"
                    and m["Destination"] == "/var/log/workstation"
                ]
                if station.trace_commands and (
                    len(observation_mounts) != 1
                    or observation_mounts[0]["Name"] != station.observation_volume
                ):
                    raise RuntimeError("Private observation volume differs")
                host = row["HostConfig"]
                caps = {c.removeprefix("CAP_") for c in (host["CapAdd"] or [])}
                expected_caps = (
                    {"SYS_PTRACE", "SETUID", "SETGID", "DAC_READ_SEARCH"}
                    if station.trace_commands
                    else set()
                )
                if (
                    set(network) != {self.networks[actor]}
                    or len(mounts) != 1
                    or mounts[0]["Name"] != self.volumes[actor]
                    or mounts[0]["Destination"] != "/var/tmp/exports"
                    or not mounts[0]["RW"]
                    or row["Config"]["Image"] != IMAGE
                    or row["Config"]["User"] != "65534:65534"
                    or "HOME=/workspace" not in row["Config"]["Env"]
                    or host["Privileged"]
                    or not host["ReadonlyRootfs"]
                    or host["PidMode"]
                    or host["IpcMode"] != "private"
                    or caps != expected_caps
                    or set(host["CapDrop"] or []) != {"ALL"}
                    or "no-new-privileges" not in (host["SecurityOpt"] or [])
                ):
                    raise RuntimeError(
                        "Unexpected workstation network or shared volume"
                    )
                network_row = json.loads(
                    command(
                        ["docker", "network", "inspect", self.networks[actor]]
                    ).stdout
                )[0]
                if not network_row["Internal"] or {
                    v["Name"] for v in network_row["Containers"].values()
                } != {station.name, self.service.name}:
                    raise RuntimeError(
                        "Client network must contain only its workstation and its service"
                    )
                namespace_code = "import os,json; print(json.dumps({n:os.readlink('/proc/self/ns/'+n) for n in ('pid','ipc','mnt','net')}))"
                namespaces = json.loads(
                    command(
                        [
                            "docker",
                            "exec",
                            station.name,
                            "python",
                            "-I",
                            "-c",
                            namespace_code,
                        ]
                    ).stdout
                )
                self.bindings[actor] = {
                    "container": station.name,
                    "network": self.networks[actor],
                    "observation_volume": station.observation_volume
                    if station.trace_commands
                    else None,
                    "service_container": self.service.name,
                    "ip": network[self.networks[actor]]["IPAddress"],
                    "private_export_volume": self.volumes[actor],
                    "shared_artifact_scope": shared,
                    "channel_family": "socket",
                    "workstation_environment": WORKSTATION_ENVIRONMENT,
                    "image": row["Image"],
                    "user": row["Config"]["User"],
                    "namespaces": namespaces,
                    "observer_enabled": station.trace_commands,
                    "container_cap_add": sorted(caps),
                    "read_only_root": host["ReadonlyRootfs"],
                    "private_ipc": host["IpcMode"],
                    "service_state_volume": self.service_volume,
                    "service_state_path": "/workspace/project-store.json",
                    "memory_bytes": host["Memory"],
                    "nano_cpus": host["NanoCpus"],
                    "pids_limit": host["PidsLimit"],
                }
            for namespace in ("pid", "ipc", "mnt", "net"):
                if len(
                    {v["namespaces"][namespace] for v in self.bindings.values()}
                ) != len(startup):
                    raise RuntimeError(
                        "Socket workstations unexpectedly share " + namespace
                    )
        except BaseException:
            self.close()
            raise

    def _retained_service(self):
        service = getattr(self, "service", None)
        return service is not None and not service.closed

    def _remove_network(self, name):
        if self._retained_service():
            self.retained_resources = getattr(self, "retained_resources", []) + [
                {"kind": "network", "name": name}
            ]
            return
        command(["docker", "network", "rm", name])

    def _remove_volume(self, name):
        if name == getattr(self, "service_volume", None) and self._retained_service():
            self.retained_resources = getattr(self, "retained_resources", []) + [
                {"kind": "volume", "name": name}
            ]
            return
        FileDeployment._remove_volume(self, name)

    def _close_service(self):
        if getattr(self, "service", None) is None:
            return
        if not self.service.closed and self.service.initialized:
            command(
                [
                    "docker",
                    "exec",
                    self.service.name,
                    "python",
                    "-c",
                    "from pathlib import Path; Path('/workspace/.close-service').touch()",
                ]
            )
            deadline = time.monotonic() + 10
            while subprocess.run(
                [
                    "docker",
                    "exec",
                    self.service.name,
                    "test",
                    "-f",
                    "/workspace/.service-closed",
                ],
                capture_output=True,
            ).returncode:
                if time.monotonic() > deadline:
                    raise RuntimeError("Socket request handlers did not close")
                time.sleep(0.05)
            self.terminal_service = self.service.observe()
        self.service.close()

    def close(self):
        if not self.closed:
            self.capture_terminal()
            self._close_service()
            self.resources.close()
            self.closed = True
