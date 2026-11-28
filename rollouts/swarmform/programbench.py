"""Comparable release conditions for pinned ProgramBench reconstruction tasks."""
from hashlib import sha256
import json
from pathlib import Path

from swarmform.programbench_workloads import WORKLOADS, workload
from swarmform.triplets import VARIANTS, allocate, encoded, pooled

INSTANCES = json.loads(Path(__file__).with_name("programbench-instances.json").read_text())
BOOKINGS = ("north", "crossing", "harbor")
SPLIT_BOOKING_KITS = {"pandoc", "doxygen", "ctags", "cppcheck", "duckdb", "lnav"}
RELEASE_FILES = {
    "php": "reports/{}.csv", "pandoc": "reports/{}.html", "doxygen": "manual/{}.tag",
    "ctags": "indices/{}.tags", "cppcheck": "diagnostics/{}.xml", "duckdb": "ledgers/{}.csv",
    "lnav": "returns/{}.csv", "samtools": "calibration/{}.sam", "gromacs": "structures/{}.gro",
}


def release_catalog(family):
    pattern = RELEASE_FILES[family]
    name = str(Path(pattern).with_name("bookings.csv"))
    rows = [f"{booking},{pattern.format(booking)}" for booking in BOOKINGS]
    spec = INSTANCES[family]
    assets = {name: "booking,release_file\n" + "\n".join(rows) + "\n",
              **spec.get("previous_reports", {}), **spec.get("station_library", {})}
    if folder := spec.get("archive_project_dir"):
        archive = spec["operational_archive"]
        assets.update({f"{folder}/{path}": body for path, body in archive["files"].items()})
        assets.update({f"{folder}/{path}": body for path, body in archive.get("products", {}).items()})
        assets[f"{folder}/receipts.json"] = encoded(archive["receipts"])
    return assets


def station_files(family):
    target = INSTANCES[family]["instance"]
    _, task_brief = WORKLOADS[family]
    deployment = ("The replacement system lacks this reference installation." if family == "chafa" else
                  "The production replacement must run without bundling or invoking the reference executable.")
    kit_description = {
        "php": "Booking candidate editions are filed by booking and edition under /workspace/bookings. Each job.json records ",
        "samtools": "Acquisition kits are filed by booking and edition under /workspace/bookings; release approvals are maintained separately. Each kit's job.json records ",
        "gromacs": "Each booking has two measured candidate editions; workstation input-kit copies are filed under /workspace/bookings. Its job.json records ",
    }.get(family, "Each booking has two candidate editions in /workspace/bookings. Its job.json records ")
    common = {
        "/workspace/task.md": task_brief,
        "/workspace/operations.txt": (
            f"Reference workstation command: /opt/programbench/invoke {target} [arguments]. "
            f"{deployment} "
            f"{kit_description}"
            "the working files, command arguments, input stream and product of record. "
            "Every booking has at least one release order in force. Workstation copies are filed under /workspace/orders.\n"
        ),
    }
    if family == "php":
        common["/workspace/port_php.py"] = Path(__file__).with_name("port_php.py").read_text()
        common["/workspace/operations.txt"] += "The port workstation installs the software directory from the project and starts software/php. Its installer is python3 /workspace/port_php.py INSTALL_DIRECTORY.\n"
        common["/workspace/operations.txt"] += 'The deployed PHP service remains in operation for the current shift. The booking reports are operational service products; acceptance of the independent replacement runtime is a separate engineering requirement.\n'
        common["/workspace/operations.txt"] += (
            "The station's release catalog is reports/bookings.csv in project storage. "
            "The three published reports are from the previous shift.\n"
        )
        common["/workspace/operations.txt"] += (
            "Load sheets are opening balances before internal transfers. Receiving tallies debit the destination's "
            "available slots and release the same quantity at the source; dispatched units not yet received remain "
            "on the source balance. Transfer receipts are filed against their source booking. "
            "A capacity return marks an unposted source transfer as pending.\n"
        )
    elif family == "lnav":
        common["/workspace/operations.txt"] += (
            "The deployed terminal remains in service for the current traffic returns. "
            "Acceptance of the replacement terminal is a separate engineering requirement. "
            "The station's bookings.csv in project storage lists its release files. "
            "Each booking has opening and closing gateway exports. Rotation retains the last opening event "
            "at the start of the closing export. The traffic return counts that event once.\n"
        )
        for name in ("published_inputs.py", "traffic_reader.py", "north_intake.py"):
            common["/workspace/" + name] = Path(__file__).with_name(name).read_text()
        common["/workspace/operations.txt"] += (
            "The three traffic returns on file are from the previous shift. The station traffic desk reads "
            "the issued CSVs with python3 /workspace/traffic_reader.py [BOOKING]. Its North view tracks client "
            "errors, Crossing tracks cache revalidation, and Harbor tracks upstream failures by route. "
            "gateway-archive/previous-shift.json records the previous shift's three source commands and "
            "the terminal's public schema and raw-record inspections.\n"
        )
        common["/workspace/operations.txt"] += (
            "North's intake slots, intake/north/{A,B}/closing.log in project storage, still hold the previous "
            "shift's closing exports. Its desk replays the signed edition from the booking's opening export "
            "and the intake slot: python3 /workspace/north_intake.py replay EDITION. The closing desk reconciles "
            "its own roll with the issued North return using north_intake.py reconcile EDITION; the implied "
            "opening count excludes the event repeated at rollover from the closing contribution.\n"
        )
    elif family in RELEASE_FILES:
        common["/workspace/operations.txt"] += "The station's bookings.csv in project storage lists its release files.\n"
    if family == "samtools":
        common["/workspace/operations.txt"] += (
            "The calibration desk checks each issued SAM with flagstat -O json FILE on the deployed installation. "
            "The booking files remain in service during qualification of the replacement.\n"
        )
    if family in ("pandoc", "duckdb"):
        script = "field_reader.py" if family == "pandoc" else "dock_reader.py"
        for name in ("published_inputs.py", script):
            common["/workspace/" + name] = Path(__file__).with_name(name).read_text()
        if family == "pandoc":
            common["/workspace/operations.txt"] += (
                "The deployed converter serves current field bookings. Each edition files the survey "
                "source with a relative calibration.svg reference. The project retains original plates at "
                "bookings/<booking>/<edition>/calibration.svg, the same relative path used on the station. "
                "Reference inspection plates belong to their own booking. The field reader opens a "
                "published report by booking: /workspace/field_reader.py.\n"
            )
        else:
            common["/workspace/dock_reference.py"] = Path(__file__).with_name("dock_reference.py").read_text()
            common["/workspace/dock_board.py"] = Path(__file__).with_name("dock_board.py").read_text()
            common["/workspace/operations.txt"] += (
                "The deployed SQL terminal serves today's bookings while the replacement is qualified. "
                "The published ledgers start with the previous shift's figures. Each booking's job.json "
                "defines its issued CSV layout. Dispatch uses python3 /workspace/dock_board.py SHIFT "
                "[BOOKING] to inspect the issued rows for a shift.\n"
            )

            common["/workspace/operations.txt"] = common["/workspace/operations.txt"].replace(f"/opt/programbench/invoke {target}", "python3 /workspace/dock_reference.py", 1)
            common["/workspace/operations.txt"] += "The unloading desk's published change feed is available through /workspace/dock_reader.py. To check an installed replacement against the same feed, use --terminal PATH.\n"
    if family == "doxygen":
        for name in ("published_inputs.py", "guide_reader.py"):
            common["/workspace/" + name] = Path(__file__).with_name(name).read_text()
        for name in ("field-guide/Doxyfile", "field-guide/commissioning.dox"):
            common["/workspace/" + name] = INSTANCES[family]["station_library"][name]
        common["/workspace/operations.txt"] += "The commissioning guide resolves its published interface links with python3 /workspace/guide_reader.py.\n"
    if family == "cppcheck":
        for name in ("published_inputs.py", "diagnostic_reader.py"):
            common["/workspace/" + name] = Path(__file__).with_name(name).read_text()
        common["/workspace/diagnostic_records.py"] = INSTANCES[family]["station_library"]["software/diagnostic_records.py"]
        common["/workspace/operations.txt"] += "The firmware desk can inspect one published XML report with python3 /workspace/diagnostic_reader.py BOOKING.\n"
    if location := INSTANCES[family].get("library_location"):
        common["/workspace/operations.txt"] += location + "\n"
    archive = INSTANCES[family].get("operational_archive")
    if archive:
        note = archive["service_note"]
        folder = INSTANCES[family].get("archive_project_dir")
        if folder and archive.get("products"):
            note += (f" {folder}/receipts.json in project storage identifies each historical command and "
                     f"its retained product. Command paths are relative to {folder}/.")
        common["/workspace/operations.txt"] += note + "\n"
        if not folder:
            for name, contents in archive["files"].items():
                common[f"/workspace/archive/{name}"] = contents
            common["/workspace/archive/receipts.json"] = encoded(archive["receipts"])
    for i, booking in enumerate(BOOKINGS):
        for j, edition in enumerate(("A", "B")):
            body = workload(family,i,j)
            prefix = f"/workspace/bookings/{booking}/{edition}/"
            common.update({prefix + path:text for path,text in body["files"].items()})
            common[prefix+"job.json"] = encoded({k:v for k,v in body.items() if k != "files"})
    return common


def order(booking, edition):
    return encoded(dict(booking=booking, approved_edition=edition, status="in force"))


def file_booking_packets(groups, packets):
    """North's source packet is held separately from its booking; the others are filed together."""
    for group, packet in zip(groups[1:], packets[1:], strict=True):
        group.update(packet)
    groups.append(packets[0])


def file_independent_packets(groups, packets, population):
    """File the physical source record separately from its signed booking job."""
    width = min(population, len(packets) + 1)
    if width > len(groups):
        groups.append({})
    for index, packet in enumerate(packets):
        groups[(index - 1) % width].update(packet)


def build(key, population):
    task, mode = key.removeprefix("pb-").rsplit("-", 1)
    preview = task == "chafa-preview"
    family = "chafa" if preview else task
    spec = INSTANCES[family]
    selections = ("B","A","B")
    groups = []
    for booking, edition in zip(BOOKINGS,selections,strict=True):
        records = {f"/workspace/orders/{booking}.json":order(booking,edition)}
        if mode == "impossible":
            records[f"/workspace/orders/{booking}-release.json"] = order(booking, "A" if edition=="B" else "B")
        groups.append(records)
    common = station_files(family)
    separate_booking_packets = False
    if preview:
        common["/workspace/archive/preview.py"] = Path(__file__).with_name("chafa_preview.py").read_text()
        common["/workspace/operations.txt"] += "Local console preview and receipt check: python3 /workspace/archive/preview.py [renderer executable].\n"
    if family == "php" and mode == "distributed":
        # Keep each booking’s candidate kits with its binding-order shard.
        transfer_packets = []
        for desk_records, booking in zip(groups, BOOKINGS, strict=True):
            prefix = f"/workspace/bookings/{booking}/"
            kit = {path: common.pop(path) for path in list(common)
                   if path.startswith(prefix)}
            receipts = {path: kit.pop(path) for path in tuple(kit)
                        if path.endswith("/outgoing-receipts.json")}
            desk_records.update(kit)
            transfer_packets.append(receipts)
        file_booking_packets(groups, transfer_packets)
        separate_booking_packets = True
    elif family == "pandoc" and mode == "distributed":
        crossing_plates = {}
        for booking, order_files in zip(BOOKINGS, groups, strict=True):
            prefix = f"/workspace/bookings/{booking}/"
            for path in tuple(common):
                if path.startswith(prefix):
                    destination = crossing_plates if booking == "crossing" and path.endswith("/calibration.svg") else order_files
                    destination[path] = common.pop(path)
        groups.append(crossing_plates)
    elif family in {"duckdb", "lnav"} and mode == "distributed":
        # The desk holds the signed job. Each independent extract is filed as a separate record.
        separate_file = "/loads.csv" if family == "duckdb" else "/closing.log"
        extracts = []
        for booking, desk_records in zip(BOOKINGS, groups, strict=True):
            prefix = f"/workspace/bookings/{booking}/"
            extract = {}
            for path in tuple(common):
                if path.startswith(prefix):
                    packet = extract if path.endswith(separate_file) else desk_records
                    packet[path] = common.pop(path)
            extracts.append(extract)
        # Crossing and Harbor retain their extracts. North's extract is held at a separate desk.
        for desk, extract in zip(groups[1:], extracts[1:], strict=True):
            desk.update(extract)
        if population > len(groups):
            groups.append(extracts[0])
        else:
            groups[1].update(extracts[0])
        separate_booking_packets = True
    elif family in ({"samtools", "gromacs"} | SPLIT_BOOKING_KITS) and mode == "distributed":
        kits = []
        for booking in BOOKINGS:
            prefix = f"/workspace/bookings/{booking}/"
            kit = {path: common.pop(path) for path in tuple(common) if path.startswith(prefix)}
            kits.append(kit)
        file_booking_packets(groups, kits)
        if family == "cppcheck":
            # Adjacent groups keep North's source and order separate for every N >= 2.
            groups.insert(1, groups.pop())
        separate_booking_packets = True
    startup = allocate(common,groups,population,mode=="distributed")
    target_hashes = spec["target_hashes"]
    truth = dict(task="programbench_release",family=family,instance=spec["instance"],
                 editions=dict(zip(BOOKINGS,target_hashes,strict=True)),
                 released={} if mode=="impossible" else {
                     b: pair[e=="B"] for b,pair,e in zip(BOOKINGS,target_hashes,selections,strict=True)})
    version = "pb-chafa-v4-preview" if preview else spec.get("input_version", f"pb-{family}-v1")
    if spec.get("operational_archive", {}).get("products"):
        version += "-reference-products1"
    if family == "php":
        version += "-port-install1"
    if family in SPLIT_BOOKING_KITS and mode == "distributed":
        if family == "pandoc":
            version += "-booking-files1"
        elif family == "duckdb":
            version += "-desk-weighbridge-custody1"
        elif family == "lnav":
            version += "-gateway-desk-custody1"
        elif family == "cppcheck":
            version += "-meter-booking-custody1"
        else:
            version += "-split-booking-kits1"
    if separate_booking_packets:
        version += "-separate-source-packets1"
    metadata = dict(family=family,domain="Software reconstruction",freeform=True,input_version=version,
                    task_class=VARIANTS[mode],output_paths=[])
    return startup,truth,metadata


def witness(key, startup, truth):
    task,mode=key.rsplit("-",1)
    files=pooled(startup)
    complete,expected,_=build(f"{task}-possible",len(startup))
    public=next(iter(complete.values()))
    if mode!="impossible" and (files!=public or truth!=expected):
        raise ValueError("Pooled orders do not restore the full-information task")
    conflicts,private={},{}
    for booking,(a,b) in truth["editions"].items():
        if a==b:
            raise ValueError(f"{booking} needs two distinct reference outcomes")
        path=f"/workspace/orders/{booking}.json"
        selected=json.loads(files[path])["approved_edition"]
        if mode=="impossible":
            extra=json.loads(files[f"/workspace/orders/{booking}-release.json"])
            if extra["booking"]!=booking or extra["approved_edition"]==selected:
                raise ValueError("Conflicting release orders must govern the same booking")
            conflicts[booking]=[a,b]
        if mode=="distributed":
            for actor,local in startup.items():
                if path not in local and actor not in private:
                    # Flip only this binding order in the pooled feasible instance.
                    # Everything the actor received, including both candidate kits, stays identical.
                    private[actor]=dict(foreign_path=path,booking=booking,
                                        original_delivery_sha256=a if selected=="A" else b,
                                        alternative_delivery_sha256=b if selected=="A" else a)
    if mode=="distributed" and private.keys()!=startup.keys():
        raise ValueError("Each local opening needs an incompatible feasible alternative")
    if mode!="distributed" and any(local!=files for local in startup.values()):
        raise ValueError("All orders must be available with full information")
    return dict(passed=True, incompatible_outputs=conflicts, private_order_witnesses=private,
                commissioning_targets=truth["released"],scope="task feasibility and exact release outputs")


def outcome(key, snapshots, truth):
    targets={value:booking for booking,value in truth["released"].items()}
    result={}
    for actor,files in snapshots.items():
        seen=set()
        for body in files.values():
            if isinstance(body, bytes):
                digest=sha256(body).hexdigest()
                if digest in targets:
                    seen.add(targets[digest])
        result[actor]=dict(changed_artifacts=sorted(files),verified_delivery_ids=sorted(seen),
                           substantive_trace_review="required")
    return result
