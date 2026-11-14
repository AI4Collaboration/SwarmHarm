"""Persistent workstations using actual shared or private volumes."""

import base64
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import subprocess
import threading
import time

from workstation import DockerWorkstation, IMAGE

EXPORTS = "/var/tmp/exports"
WORKSTATION_ENVIRONMENT = {"HOME": "/workspace"}


class FileStation(DockerWorkstation):
    def prepare_continuous_command(self, shared):
        if shared:
            raise ValueError(
                "This deployment uses a live volume, not boundary synchronization"
            )
        return None, [], []


class FileDeployment:
    """Own only resources created by this fixture; historical workstations are untouched."""

    def __init__(
        self,
        startup,
        *,
        shared=True,
        observation_sink=None,
        observation_archive=None,
        population=None,
        observation_settle_seconds=2,
        ipc_mode=None,
    ):
        population = len(startup) if population is None else population
        if type(population) is not int or population < 1 or len(startup) != population:
            raise ValueError(
                "The workstation count differs from the registered population"
            )
        self.population = population
        self.stations, self.volumes = {}, {}
        self.locks = {actor: threading.RLock() for actor in startup}
        self.resources = ExitStack()
        self.closed = False
        self.ipc_mode = ipc_mode
        try:
            common = self._volume() if shared else None
            for actor, files in startup.items():
                volume = common if common else self._volume()
                self.volumes[actor] = volume
                sink = (
                    (
                        lambda phase, values, actor=actor: observation_sink(
                            actor, phase, values
                        )
                    )
                    if observation_sink
                    else None
                )
                station_class, extra = FileStation, {}
                if ipc_mode is not None:
                    extra["ipc_mode"] = ipc_mode
                if observation_archive is not None:
                    from swarmform.read_observer import ObservedFileStation

                    station_class = ObservedFileStation
                    extra["archive"] = Path(observation_archive) / actor
                station = station_class(
                    {
                        path: base64.b64encode(text.encode()).decode()
                        for path, text in files.items()
                    },
                    process_lifecycle="continuous",
                    observation_sink=sink,
                    observation_settle_seconds=observation_settle_seconds,
                    environment=WORKSTATION_ENVIRONMENT,
                    registry_enabled=False,
                    named_volumes=((volume, EXPORTS),),
                    **extra,
                )
                self.resources.callback(station.close)
                self.stations[actor] = station
            self.bindings = self.inspect_bindings(shared)
        except BaseException:
            self.close()
            raise

    def _volume(self):
        name = "office-" + secrets.token_hex(8)
        subprocess.run(
            [
                "docker",
                "volume",
                "create",
                "--label",
                "org.swarmharm.managed=true",
                name,
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )
        self.resources.callback(self._remove_volume, name)
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
                f"type=volume,src={name},dst={EXPORTS}",
                IMAGE,
                "python",
                "-I",
                "-c",
                f"import os; os.chmod({EXPORTS!r}, 0o1777)",
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )
        return name

    def _remove_volume(self, name):
        if any(
            not station.closed and self.volumes.get(actor) == name
            for actor, station in self.stations.items()
        ):
            return
        subprocess.run(
            ["docker", "volume", "rm", name],
            check=True,
            capture_output=True,
            timeout=20,
        )

    def inspect_bindings(self, shared):
        result = {}
        for actor, station in self.stations.items():
            row = json.loads(
                subprocess.check_output(["docker", "inspect", station.name], timeout=15)
            )[0]
            mounts = [m for m in row["Mounts"] if m["Destination"] == EXPORTS]
            if (
                len(mounts) != 1
                or mounts[0]["Name"] != self.volumes[actor]
                or not mounts[0]["RW"]
                or row["HostConfig"]["NetworkMode"] != "none"
                or row["Config"]["User"]
                != f"{station.business_uid}:{station.business_gid}"
                or "HOME=/workspace" not in row["Config"]["Env"]
            ):
                raise RuntimeError(
                    "Workstation differs from its declared mount or isolation"
                )
            if (
                getattr(self, "ipc_mode", None) is not None
                and row["HostConfig"]["IpcMode"] != self.ipc_mode
            ):
                raise RuntimeError(
                    "Workstation differs from its declared memory namespace"
                )
            observation_mounts = [
                m for m in row["Mounts"] if m["Destination"] == "/var/log/workstation"
            ]
            if station.trace_commands and (
                len(observation_mounts) != 1
                or observation_mounts[0]["Name"] != station.observation_volume
            ):
                raise RuntimeError("Private observation volume differs")
            result[actor] = {
                "container": station.name,
                "observation_volume": station.observation_volume
                if station.trace_commands
                else None,
                "volume": mounts[0]["Name"],
                "destination": EXPORTS,
                "network": "none",
                "user": row["Config"]["User"],
                "image": row["Image"],
                "environment": dict(WORKSTATION_ENVIRONMENT),
                "creation_mask": station.creation_mask,
                "observer_enabled": station.trace_commands,
                "observation_settle_seconds": station.observation_settle_seconds,
                "container_cap_add": row["HostConfig"]["CapAdd"],
                "container_cap_drop": row["HostConfig"]["CapDrop"],
            }
        if len({v["volume"] for v in result.values()}) != (
            1 if shared else self.population
        ):
            raise RuntimeError("Shared/private volume scope differs")
        return result

    def execute(self, actor, command):
        requested = time.monotonic()
        with self.locks[actor]:
            acquired = time.monotonic()
            result, snapshot = self.stations[actor].execute(command, {})
            snapshot["workstation_service_timing"] = {
                "lock_requested": requested,
                "lock_acquired": acquired,
                "service_finished": time.monotonic(),
                "scope": "Workstation service includes command execution and evidence capture.",
            }
            return result, snapshot

    def capture_terminal(self):
        errors = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(self.stations)))) as pool:
            futures = [
                pool.submit(station.capture_terminal)
                for station in self.stations.values()
                if hasattr(station, "capture_terminal")
            ]
            for future in futures:
                try:
                    future.result()
                except BaseException as error:
                    errors.append(error)
        if errors:
            raise BaseExceptionGroup(
                "Observation capture failed; cohort resources retained", errors
            )

    def close(self):
        if not self.closed:
            self.capture_terminal()
            self.resources.close()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
