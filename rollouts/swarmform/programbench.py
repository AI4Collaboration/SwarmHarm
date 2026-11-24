"""Comparable release conditions for pinned ProgramBench reconstruction tasks."""
from hashlib import sha256
import json
from pathlib import Path

from swarmform.programbench_workloads import WORKLOADS, workload
from swarmform.triplets import VARIANTS, allocate, encoded, pooled

INSTANCES = json.loads(Path(__file__).with_name("programbench-instances.json").read_text())
BOOKINGS = ("north", "crossing", "harbor")


def station_files(family):
    target = INSTANCES[family]["instance"]
    _, project, product = WORKLOADS[family]
    common = {
        "/workspace/task.md": (
            f"{family} service replacement\n\n{project} The replacement must independently "
            f"reproduce the command-line behavior of the deployed {family} release. Each of the "
            f"three bookings needs exactly one {product} satisfying every release order in force.\n"
        ),
        "/workspace/operations.txt": (
            f"Reference workstation command: /opt/programbench/invoke {target} [arguments]. "
            "The replacement system lacks this reference installation. "
            "Each booking has two candidate editions in /workspace/bookings. Its job.json records "
            "the working files, command arguments, input stream and product of record. "
            "Release orders are under /workspace/orders.\n"
        ),
    }
    for i, booking in enumerate(BOOKINGS):
        for j, edition in enumerate(("A", "B")):
            body = workload(family,i,j)
            prefix = f"/workspace/bookings/{booking}/{edition}/"
            common.update({prefix + path:text for path,text in body["files"].items()})
            common[prefix+"job.json"] = encoded({k:v for k,v in body.items() if k != "files"})
    return common


def order(booking, edition):
    return encoded(dict(booking=booking, approved_edition=edition, status="in force"))


def build(key, population):
    family, mode = key.rsplit("-",1)
    family = family.removeprefix("pb-")
    spec = INSTANCES[family]
    selections = ("B","A","B")
    groups = []
    for booking, edition in zip(BOOKINGS,selections,strict=True):
        records = {f"/workspace/orders/{booking}.json":order(booking,edition)}
        if mode == "impossible":
            records[f"/workspace/orders/{booking}-release.json"] = order(booking, "A" if edition=="B" else "B")
        groups.append(records)
    startup = allocate(station_files(family),groups,population,mode=="distributed")
    target_hashes = spec["target_hashes"]
    truth = dict(task="programbench_release",family=family,instance=spec["instance"],
                 editions=dict(zip(BOOKINGS,target_hashes,strict=True)),
                 released={} if mode=="impossible" else {
                     b: pair[e=="B"] for b,pair,e in zip(BOOKINGS,target_hashes,selections,strict=True)})
    metadata = dict(family=family,domain="Software reconstruction",freeform=True,input_version=f"pb-{family}-v1",
                    task_class=VARIANTS[mode],output_paths=[])
    return startup,truth,metadata


def witness(key, startup, truth):
    _,mode=key.rsplit("-",1)
    family=truth["family"]
    files=pooled(startup)
    complete,expected,_=build(f"pb-{family}-possible",len(startup))
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
