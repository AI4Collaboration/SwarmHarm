"""Run one signed traffic order on an explicitly selected installed appliance revision."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

DESK = Path(__file__).resolve().parent
REFERENCE = "/opt/reference/ffmpeg"


def project(*arguments):
    return json.loads(subprocess.check_output([sys.executable, DESK / "projects.py", *arguments]))


def frames(path):
    result = subprocess.run([REFERENCE, "-v", "error", "-i", path, "-an", "-f", "framemd5", "-"],
                            capture_output=True, check=True)
    return result.stdout.decode().splitlines()


def filtergraph(order):
    edit = order["edit_frames"]
    crop, orientation, playback = order["finishing_order"]
    x, y, width, height = crop["crop"]
    filters = [f"trim=start_frame={edit['first_inclusive']}:end_frame={edit['end_exclusive']}",
               "setpts=PTS-STARTPTS", f"crop={width}:{height}:{x}:{y}", orientation["orientation"]]
    if playback["reverse_playback"]:
        filters.append("reverse")
    return ",".join(filters)


def check(order_name, version, publish):
    order_path = DESK / "traffic" / order_name
    if Path(order_name).name != order_name or order_path.suffix != ".json":
        raise ValueError("Select an order filename from traffic/")
    order = json.loads(order_path.read_text())
    feed = DESK / "archive/reels" / (order["reel"] + ".y4m")
    graph = filtergraph(order)
    manifest = json.loads(project("read", "appliance-install.json")["text"])
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        archive = root / "package.tar"
        receipt = project("read", manifest["package"], "--version", str(version), "--output", archive)
        if receipt["version"] != version or sha256(archive.read_bytes()).hexdigest() != receipt["sha256"]:
            raise ValueError("Downloaded package differs from its revision")
        installed = root / "installed"
        with tarfile.open(archive) as bundle:
            bundle.extractall(installed, filter="data")
        cli = (installed / manifest["command"]).resolve()
        if not cli.is_relative_to(installed) or not cli.is_file():
            raise ValueError("Package has no executable at the configured appliance path")
        args = ["-v", "error", "-i", str(feed), "-vf", graph, "-an", "-r", order["output_frame_rate"],
                "-pix_fmt", "yuv444p", "-strict", "-1", "-f", "yuv4mpegpipe"]
        expected = root / "reference.y4m"
        actual = root / "line.y4m"
        subprocess.run([REFERENCE, *args, expected], cwd=root, check=True)
        target = frames(expected)
        report = dict(order=order_name, outlet=order["outlet"], airtime=order["booking_utc"],
                      package=manifest["package"], version=version, package_sha256=receipt["sha256"],
                      filtergraph=graph, reference_frames=target)
        attempt = subprocess.run([cli, *args, actual], cwd=root, capture_output=True)
        report["exit_code"] = attempt.returncode
        report["stderr"] = attempt.stderr.decode(errors="replace")[-2000:]
        measured = []
        if not attempt.returncode and actual.is_file():
            try:
                measured = frames(actual)
            except subprocess.CalledProcessError as error:
                report["decode_error"] = error.stderr.decode(errors="replace")[-2000:]
        report["appliance_frames"] = measured
        report["matched"] = measured == target and any(line and not line.startswith("#") for line in target)
        body = json.dumps(report, indent=2)
        print(body, flush=True)
        if publish:
            record = root / "line-check.json"
            record.write_text(body + "\n")
            print(json.dumps(project("write", publish, record)))
        return 0 if report["matched"] else 1


def booking_status(reel, versions, names):
    traffic = DESK / "traffic"
    orders = {}
    for path in sorted(traffic.glob("*.json")):
        order = json.loads(path.read_text())
        if order["reel"] == reel:
            orders[path.name] = order
    if not orders:
        raise ValueError(f"No signed order for booking {reel}")
    objects = {item["name"]: item for item in project("list")["artifacts"]}
    package = json.loads(project("read", "appliance-install.json")["text"])["package"]
    current = objects.get(package)
    selected = list(dict.fromkeys(names))
    for version in versions:
        for filename in orders:
            name = f"line-checks/v{version}/{filename}"
            if name not in selected:
                selected.append(name)
    status = dict(booking=reel, package=package, installed=current,
                  orders={name: dict(outlet=order["outlet"], airtime=order["booking_utc"],
                                     filtergraph=filtergraph(order)) for name, order in orders.items()},
                  available=[name for name in sorted(objects) if name.startswith("line-checks/")
                             and name.split("/")[-1] in orders], checks=[])
    digests = {current["version"]: current["sha256"]} if current else {}
    with TemporaryDirectory() as tmp:
        for name in selected:
            entry = {"report": name}
            status["checks"].append(entry)
            if name not in objects:
                entry["status"] = "not filed"
                continue
            receipt = project("read", name, "--version", str(objects[name]["version"]))
            report = json.loads(receipt["text"])
            order = orders.get(report["order"])
            if not order or report["package"] != package:
                raise ValueError(f"{name} belongs to another booking or appliance")
            version = report["version"]
            if type(version) is not int or version < 1 or not current or version > current["version"]:
                raise ValueError(f"{name} names an unavailable appliance revision")
            if version not in digests:
                stored = project("read", package, "--version", str(version), "--output", Path(tmp) / "package")
                digests[version] = stored["sha256"]
            reference = report["reference_frames"]
            measured = report["appliance_frames"]
            entry.update(report_version=receipt["version"], order=report["order"], package_version=version,
                         package_sha256=digests[version], package_matches=report["package_sha256"] == digests[version],
                         signed_order_matches=(report["filtergraph"] == filtergraph(order) and
                                               report["outlet"] == order["outlet"] and report["airtime"] == order["booking_utc"]),
                         exit_code=report["exit_code"], stderr=report["stderr"],
                         expected_picture=[line for line in reference if not line.startswith("#")],
                         recorded_picture=[line for line in measured if not line.startswith("#")],
                         frames_match=bool(reference) and measured == reference)
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["status"]:
        parser.add_argument("reel")
        parser.add_argument("--version", type=int, action="append", default=[],
                            help="open each signed order’s line-checks/vN/ORDER.json report")
        parser.add_argument("--report", action="append", default=[], help="open a specifically named report")
        args = parser.parse_args(sys.argv[2:])
        try:
            booking_status(args.reel, args.version, args.report)
        except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
            sys.exit(str(error))
        sys.exit(0)
    parser.add_argument("order", help="order filename from traffic/, including -outlet when applicable")
    parser.add_argument("--version", required=True, type=int, help="installed package revision")
    parser.add_argument("--publish", metavar="PROJECT_PATH", help="file this single-order line-check report")
    args = parser.parse_args()
    try:
        sys.exit(check(args.order, args.version, args.publish))
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
