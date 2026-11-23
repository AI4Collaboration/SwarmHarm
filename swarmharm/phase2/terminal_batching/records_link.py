"""Operator-owned TCP links from individual workstations to one synthetic records server."""

from contextlib import ExitStack
from ipaddress import ip_network
import json
import os
from pathlib import Path
import secrets
import subprocess
from threading import Lock
import time

from . import records_server


def docker(*args, data=None, timeout=25):
    cmd = subprocess.run(["docker", *args], input=data, text=True, capture_output=True, timeout=timeout)
    if cmd.returncode:
        detail = cmd.stderr.strip() or cmd.stdout.strip() or 'no diagnostic output'
        raise RuntimeError(f"Docker records service ({args[0]}, exit {cmd.returncode}): {detail[:450]}")
    return cmd.stdout


def available_subnets():
    """Use small, disjoint links without exhausting Docker's default bridge pool.

    Docker atomically rejects overlaps, including concurrent collectors. The
    initial inventory skips occupied ranges; network creation remains decisive.
    """
    pool = ip_network(os.environ.get('SWARMHARM_NETWORK_POOL', '10.240.0.0/16'))
    if pool.version != 4 or not pool.is_private or pool.prefixlen > 22:
        raise ValueError('SWARMHARM_NETWORK_POOL must be a private IPv4 CIDR of /22 or larger')
    ids = docker('network', 'ls', '-q').split()
    occupied = []
    for network_id in ids:
        # Another collector can remove a network during inventory.
        try:
            rows = json.loads(docker('network', 'inspect', network_id))
        except RuntimeError as exc:
            if 'not found' in str(exc):
                continue
            raise
        occupied.extend(ip_network(row['Subnet']) for item in rows
                        for row in (item.get('IPAM', {}).get('Config') or []) if row.get('Subnet'))
    count = 1 << (29 - pool.prefixlen)
    start = secrets.randbelow(count)
    for offset in range(count):
        subnet = ip_network((int(pool.network_address) + ((start + offset) % count) * 8, 29))
        if not any(subnet.overlaps(other) for other in occupied if other.version == 4):
            yield str(subnet)


class RecordsLink:
    def __init__(self, directory, image, truth, *, service_module=records_server, station_factory=None, hostname=None):
        self.directory = Path(directory)
        self.journal_lock = Lock()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.name = "sh-records-" + secrets.token_hex(7)
        self.networks = {}
        self.started = False
        self.config = {**truth, "peers": {}}
        self.station_factory = station_factory
        label = [
            "--label",
            "org.swarmharm.managed=true",
            "--label",
            f"org.swarmharm.owner-pid={os.getpid()}",
        ]
        try:
            links = []
            owners = list(truth["owners"])
            subnets = iter(available_subnets())
            subnet_lock = Lock()

            def create_owner_network(item):
                idx, actor = item
                net = self.name + "-" + str(idx)
                while True:
                    with subnet_lock:
                        subnet = next(subnets, None)
                    if subnet is None:
                        raise RuntimeError('SWARMHARM_NETWORK_POOL has no free workstation links')
                    try:
                        docker('network', 'create', '--internal', '--driver', 'bridge',
                               '--subnet', subnet, '--opt',
                               'com.docker.network.bridge.gateway_mode_ipv4=isolated', *label, net)
                        return idx, actor, net
                    except RuntimeError as exc:
                        if 'overlap' not in str(exc).lower():
                            raise

            from concurrent.futures import ThreadPoolExecutor
            created = {}
            try:
                with ThreadPoolExecutor(max_workers=min(16, max(1, len(owners)))) as pool:
                    for idx, actor, net in pool.map(create_owner_network, enumerate(owners)):
                        created[actor] = net
            finally:
                self.networks.update(created)
            for actor in owners:
                net = self.networks[actor]
                links += ["--network", f"name={net},alias={hostname or service_module.HOSTNAME}"]
            docker(
                "run",
                "-d",
                "--pull=never",
                "--name",
                self.name,
                *label,
                *links,
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--user",
                "65534:65534",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,noexec,size=24m,mode=1777",
                "--memory=128m",
                "--pids-limit=32",
                image,
                "python",
                "-I",
                "-u",
                "-c",
                Path(service_module.__file__).read_text(),
                timeout=max(25, len(self.networks) * 2),
            )
            self.started = True
        except BaseException:
            self.close()
            raise

    def put(self, file, value):
        self.put_text(file, json.dumps(value))

    def put_text(self, file, text):
        code = 'import os,sys; p=sys.argv[1]; open(p+".new","wb").write(sys.stdin.buffer.read()); os.replace(p+".new",p)'
        docker("exec", "-i", self.name, "python", "-I", "-c", code, "/tmp/" + file, data=text)

    def station(self, actor, files):
        from phase1 import lab

        station = (self.station_factory(actor, files, network=self.networks[actor]) if self.station_factory
                   else lab.base.DockerWorkstation(files, network=self.networks[actor]))
        execute = station.execute

        def observed(command, shared):
            start = len(self.journal())
            reply, snapshot = execute(command, shared)
            snapshot["records_server_requests"] = [
                r["seq"] for r in self.journal()[start:] if r["actor"] == actor
            ]
            return reply, snapshot

        station.execute = observed
        return station

    def activate(self, stations):
        bindings = {}
        inspected = {n['Name']: n for n in json.loads(
            docker('network', 'inspect', *self.networks.values()))}
        for actor, net in self.networks.items():
            n = inspected[net]
            peers = {v["Name"]: v["IPv4Address"].split("/")[0] for v in n["Containers"].values()}
            if (
                not n["Internal"]
                or n["Options"].get("com.docker.network.bridge.gateway_mode_ipv4") != "isolated"
                or set(peers) != {self.name, stations[actor].name}
            ):
                raise RuntimeError("Records link must contain exactly its workstation and isolated server")
            client = peers[stations[actor].name]
            self.config["peers"][client] = actor
            bindings[actor] = {
                "network_id": n["Id"],
                "internal": True,
                "gateway_mode": "isolated",
                "station": stations[actor].name,
                "peer_ip": client,
                "server_ip": peers[self.name],
            }
        info = json.loads(docker("inspect", self.name))[0]
        if info["HostConfig"]["PortBindings"] or info["Mounts"]:
            raise RuntimeError("Records service must have no published ports or mounts")
        (self.directory / "topology.json").write_text(
            json.dumps(
                {
                    "server": self.name,
                    "container_id": info["Id"],
                    "image": info["Image"],
                    "port_bindings": {},
                    "links": bindings,
                },
                indent=2,
            )
            + "\n"
        )
        (self.directory / "input.json").write_text(json.dumps(self.config, indent=2) + "\n")
        self.put("records-config.json", self.config)
        for _ in range(80):
            if (
                docker(
                    "exec",
                    self.name,
                    "python",
                    "-c",
                    'from pathlib import Path; print(Path("/tmp/ready").exists())',
                ).strip()
                == "True"
            ):
                return
            time.sleep(0.05)
        raise RuntimeError("Records server did not start")

    def journal(self):
        # Observers must not spawn N concurrent processes inside the one server
        # container. Only capture is serialized; agent commands and HTTP traffic
        # remain concurrent, with server-authored request order preserved.
        with self.journal_lock:
            return [
                json.loads(line)
                for line in docker("exec", self.name, "cat", "/tmp/requests.jsonl").splitlines()
            ]

    def read_evidence(self, actor, receipt):
        return next(
            (
                r
                for r in self.journal()
                if r["actor"] == actor
                and r["method"] == "GET"
                and r["status"] == 200
                and r["response_sent"]
                and r["result"].get("read_receipt") == receipt
            ),
            None,
        )

    def close(self):
        nets = list(self.networks.values())
        was_started = self.started
        self.networks.clear()
        self.started = False
        try:
            if was_started and (self.directory / "input.json").exists():
                rows = self.journal()
                (self.directory / "requests.jsonl").write_text(
                    "".join(json.dumps(r) + "\n" for r in rows)
                )
                if self.config.get('query_gateway'):
                    queue = docker("exec", self.name, "cat", "/tmp/query-queue-final.json")
                    json.loads(queue)
                    (self.directory / "query-queue-final.json").write_text(queue)
        finally:
            try:
                if was_started:
                    docker("rm", "-f", self.name)
            finally:
                if nets:
                    try:
                        docker("network", "rm", *nets, timeout=max(25, len(nets)))
                    except RuntimeError:
                        for net in nets:
                            try: docker("network", "rm", net)
                            except RuntimeError: pass
