"""Operator-owned TCP links from individual workstations to one synthetic records server."""

from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

from . import records_server


def docker(*args, data=None):
    cmd = subprocess.run(["docker", *args], input=data, text=True, capture_output=True, timeout=25)
    if cmd.returncode:
        raise RuntimeError("Docker records service: " + cmd.stderr.strip()[:450])
    return cmd.stdout


class RecordsLink:
    def __init__(self, directory, image, truth, *, service_module=records_server, station_factory=None):
        self.directory = Path(directory)
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
            for idx, actor in enumerate(truth["owners"]):
                net = self.name + "-" + str(idx)
                docker(
                    "network",
                    "create",
                    "--internal",
                    "--driver",
                    "bridge",
                    "--opt",
                    "com.docker.network.bridge.gateway_mode_ipv4=isolated",
                    *label,
                    net,
                )
                self.networks[actor] = net
                links += ["--network", f"name={net},alias={service_module.HOSTNAME}"]
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
            )
            self.started = True
        except BaseException:
            self.close()
            raise

    def put(self, file, value):
        code = 'import os,sys; p=sys.argv[1]; open(p+".new","wb").write(sys.stdin.buffer.read()); os.replace(p+".new",p)'
        docker("exec", "-i", self.name, "python", "-I", "-c", code, "/tmp/" + file, data=json.dumps(value))

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
        for actor, net in self.networks.items():
            n = json.loads(docker("network", "inspect", net))[0]
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
        with ExitStack() as cleanup:
            for net in self.networks.values():
                cleanup.callback(docker, "network", "rm", net)
            self.networks.clear()
            if self.started:
                cleanup.callback(docker, "rm", "-f", self.name)
                self.started = False
                if (self.directory / "input.json").exists():
                    rows = self.journal()
                    (self.directory / "requests.jsonl").write_text(
                        "".join(json.dumps(r) + "\n" for r in rows)
                    )
                    if self.config.get('query_gateway'):
                        queue = docker("exec", self.name, "cat", "/tmp/query-queue-final.json")
                        json.loads(queue)
                        (self.directory / "query-queue-final.json").write_text(queue)
