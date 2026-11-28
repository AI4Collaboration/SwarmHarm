"""Socket artifact service with scoped accounts and private client networks."""

import base64
from concurrent.futures import ThreadPoolExecutor
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
from swarmform.workstation import IMAGE, docker_workers, remove_network
from swarmform.service_workstation import ServiceWorkstation


def command(argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=30)


def create_private_network(name):
    # Each network has just a client and service. Docker's automatic /16 pools
    # can run out before N=32, so allocate small, non-overlapping internal nets.
    for _ in range(256):
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
                    "org.swarmform.managed=true",
                    "--label",
                    f"org.swarmform.owner-pid={os.getpid()}",
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

    def service_files(self, accounts, startup):
        # Install the trusted server implementation matching the registered participant client.
        revision_client = (Path(__file__).parent / "manuscript_store.py").read_text()
        checked_revisions = all(files.get("/workspace/projects.py") == revision_client for files in startup.values())
        store = revision_client if checked_revisions else Path(__file__).with_name("formation_store.py").read_text()
        managed_client = all("/workspace/socket_worktree.py" in files for files in startup.values())
        if managed_client:
            store += "\n" + Path(__file__).with_name("socket_worktree_store.py").read_text()
        return {
            "/workspace/formation_store.py": store,
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
        self._res_lock = threading.Lock()
        self.closed = False
        self.retirement_error = None
        self.stations = {}
        self.volumes = {}
        self.locks = {a: threading.RLock() for a in startup}
        self.networks = {}
        accounts = {}
        self.terminal_service = None
        try:
            planned_nets = {}
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
                planned_nets[actor] = "office-network-" + secrets.token_hex(8)
            def _make_net(pair):
                actor, network = pair
                create_private_network(network)
                with self._res_lock:
                    self.resources.callback(self._remove_network, network)
                return actor, network
            net_items = list(planned_nets.items())
            if len(net_items) >= 4:
                with ThreadPoolExecutor(max_workers=docker_workers(len(net_items))) as pool:
                    created_nets = list(pool.map(_make_net, net_items))
            else:
                created_nets = [_make_net(p) for p in net_items]
            self.networks = dict(created_nets)
            initial = self.service_files(accounts, startup)
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
                named_volumes=((self.service_volume, "/workspace"),),
                fresh_project_root="/workspace",
                network=first,
                process_lifecycle="continuous",
                environment=WORKSTATION_ENVIRONMENT,
                registry_enabled=False,
            )
            # Added before the station callbacks: their removal happens first.
            self.resources.callback(self.service.retire)
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
            def _start_station(item):
                actor, files = item
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
                station = cls(
                    {
                        p: base64.b64encode(t.encode()).decode()
                        for p, t in files.items()
                    },
                    network=self.networks[actor],
                    environment=WORKSTATION_ENVIRONMENT,
                    process_lifecycle="continuous",
                    observation_settle_seconds=10,
                    observation_sink=sink,
                    named_volumes=((volume, "/var/tmp/exports"),),
                    fresh_project_root="/var/tmp/exports",
                    registry_enabled=False,
                    **extra,
                )
                with self._res_lock:
                    self.resources.callback(station.close)
                return actor, volume, station
            st_items = list(startup.items())
            if len(st_items) >= 4:
                with ThreadPoolExecutor(max_workers=docker_workers(len(st_items))) as pool:
                    built = list(pool.map(_start_station, st_items))
            else:
                built = [_start_station(item) for item in st_items]
            for actor, volume, station in built:
                self.volumes[actor] = volume
                self.stations[actor] = station
            self.bindings = {}
            st_names = [s.name for s in self.stations.values()]
            net_names = [self.networks[a] for a in self.stations]
            rows_by_name = ({r["Name"].lstrip("/"): r for r in json.loads(command(["docker", "inspect", *st_names]).stdout)}
                            if st_names else {})
            nets_by_name = ({r["Name"]: r for r in json.loads(command(["docker", "network", "inspect", *net_names]).stdout)}
                            if net_names else {})
            namespace_code = "import os,json; print(json.dumps({n:os.readlink('/proc/self/ns/'+n) for n in ('pid','ipc','mnt','net')}))"
            def _fetch_ns(station_name):
                return station_name, json.loads(command(["docker", "exec", station_name, "python", "-I", "-c", namespace_code]).stdout)
            if len(st_names) >= 4:
                with ThreadPoolExecutor(max_workers=docker_workers(len(st_names))) as pool:
                    ns_by_name = dict(pool.map(_fetch_ns, st_names))
            else:
                ns_by_name = dict(_fetch_ns(n) for n in st_names)
            for actor, station in self.stations.items():
                row = rows_by_name[station.name]
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
                network_row = nets_by_name[self.networks[actor]]
                if not network_row["Internal"] or {
                    v["Name"] for v in network_row["Containers"].values()
                } != {station.name, self.service.name}:
                    raise RuntimeError(
                        "Client network must contain only its workstation and its service"
                    )
                namespaces = ns_by_name[station.name]
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
        except BaseException as error:
            try:
                self.close()
            except Exception as cleanup_error:
                error.add_note(f"Socket cleanup also failed: {cleanup_error}")
            raise

    def _retained_service(self):
        service = getattr(self, "service", None)
        return service is not None and not service.closed

    def _remove_network(self, name):
        removed = getattr(self, "_removed_networks", None)
        if removed is not None and name in removed:
            return
        if self._retained_service():
            self.retained_resources = getattr(self, "retained_resources", []) + [
                {"kind": "network", "name": name}
            ]
            return
        remove_network(name)
        if removed is not None:
            with getattr(self, "_res_lock", threading.Lock()):
                removed.add(name)

    def _remove_volume(self, name):
        if name == getattr(self, "service_volume", None) and self._retained_service():
            self.retained_resources = getattr(self, "retained_resources", []) + [
                {"kind": "volume", "name": name}
            ]
            return
        FileDeployment._remove_volume(self, name)

    def _drain_service(self):
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
            self.service.capture_terminal()

    def close(self):
        if not self.closed:
            if getattr(self, "retirement_error", None) is not None:
                raise self.retirement_error
            self.capture_terminal()
            self._drain_service()
            try:
                try:
                    stations = [s for s in self.stations.values() if not getattr(s, "closed", False)]
                    if len(stations) >= 4:
                        with ThreadPoolExecutor(max_workers=docker_workers(len(stations))) as pool:
                            list(pool.map(lambda s: s.close(), stations))
                    else:
                        for station in stations:
                            station.close()
                    service = getattr(self, "service", None)
                    if service is not None and not service.closed:
                        service.retire()
                    if not self._retained_service():
                        self._removed_networks = getattr(self, "_removed_networks", set())
                        self._removed_volumes = getattr(self, "_removed_volumes", set())
                        nets = [n for n in getattr(self, "networks", {}).values() if n not in self._removed_networks]
                        vols = [v for v in set(getattr(self, "volumes", {}).values()) if v not in self._removed_volumes]
                        svc_vol = getattr(self, "service_volume", None)
                        if svc_vol and svc_vol not in self._removed_volumes:
                            vols.append(svc_vol)
                        if len(nets) + len(vols) >= 4:
                            with ThreadPoolExecutor(max_workers=docker_workers(len(nets) + len(vols))) as pool:
                                jobs = [pool.submit(self._remove_network, n) for n in nets]
                                jobs += [pool.submit(self._remove_volume, v) for v in vols]
                                for job in jobs:
                                    job.result()
                finally:
                    self.resources.close()
            except BaseException as error:
                # ExitStack consumed the callbacks even when retirement failed.
                self.retirement_error = error
                raise
            self.closed = True
