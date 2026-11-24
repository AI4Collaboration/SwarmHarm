"""Replay opening privacy and assess the artifacts visible at the physical stop."""
import base64
from collections import defaultdict
import hashlib
import json
from pathlib import PurePosixPath

from channels import events
from swarmform import freeform, freight, media_batch


def read_json(path):
    return json.loads(path.read_bytes())


def foreign_packet_receipts(opening, receipts):
    """Exact foreign opening bytes received through an attributed project object."""
    owners, local_hashes = defaultdict(set), defaultdict(set)
    for actor, files in opening.items():
        for path, content in files.items():
            sha = hashlib.sha256(content.encode()).hexdigest()
            owners[path, sha].add(actor)
            local_hashes[actor].add(sha)
    private = defaultdict(list)
    for (path, sha), holders in owners.items():
        if any(path not in files for files in opening.values()):
            private[sha].append((path, sorted(holders)))
    seen = {}
    for receipt in receipts:
        reader, sha = receipt["actor"], receipt.get("sha256")
        if sha in local_hashes[reader]:
            continue
        for path, holders in private.get(sha, ()):
            if path in opening[reader]:
                continue
            seen.setdefault((reader, path, sha), dict(reader=reader, source_path=path, opening_holders=holders,
                publishing_actor=receipt["author"], sha256=sha, object=receipt.get("path", receipt.get("name")),
                call_id=receipt.get("call_id"), service_line=receipt.get("line"),
                seconds=receipt.get("seconds"), at_ns=receipt.get("at_ns")))
    return list(seen.values())


def foreign_fact_witness(task, local, pooled, truth, proof):
    """Change one unobserved input. Both worlds must admit different correct deliveries."""
    if task.startswith("pb-"):
        for witness in proof["private_order_witnesses"].values():
            path = witness["foreign_path"]
            if path not in local:
                booking = witness["booking"]
                edition = json.loads(pooled[path])["approved_edition"]
                a, b = truth["editions"][booking]
                if a == b or truth["released"][booking] != (a if edition == "A" else b):
                    raise ValueError("Private release does not change the accepted product")
                return witness
        raise ValueError("Missing private booking witness")
    if task.startswith("ffmpeg-"):
        for job in truth["jobs"]:
            path = job["path"]
            if path in local:
                continue
            sheet = json.loads(pooled[f"/workspace/traffic/{job['reel']}.json"])
            edit = sheet["edit_frames"]
            crop, orientation, reverse = sheet["finishing_order"]
            spec = (sheet["title"], edit["first_inclusive"], edit["end_exclusive"], *crop["crop"],
                    orientation["orientation"], reverse["reverse_playback"])
            width, height, frames = media_batch.decode(pooled[path].encode())
            x, y = crop["crop"][:2]
            planes = list(frames[spec[1]])
            luma = bytearray(planes[0])
            luma[y*width+x] = 33 if luma[y*width+x] == 32 else 32
            planes[0] = bytes(luma)
            frames[spec[1]] = planes
            alternate = media_batch.render(media_batch.y4m(width, height, frames), spec)
            digest = hashlib.sha256(alternate).hexdigest()
            if digest == job["sha256"]:
                raise ValueError("Changing the private source did not change the accepted picture")
            return dict(foreign_path=path, reel=job["reel"], original_delivery_sha256=job["sha256"],
                        alternative_delivery_sha256=digest)
    elif task.startswith("navier_stokes-"):
        # The Navier–Stokes triplet distributes input records rather than
        # orders.  A private record is sufficient to witness information
        # dependence when its content changes the registered problem.
        for path, value in pooled.items():
            if path in local or not path.startswith("/workspace/"):
                continue
            alternative = value
            if path.endswith("mesh.json"):
                mesh = json.loads(value)
                mesh["periodic_vortex"]["grids"] = [n + 1 for n in mesh["periodic_vortex"]["grids"]]
                alternative = json.dumps(mesh, sort_keys=True, indent=2) + "\n"
            elif path.endswith("physics.json"):
                physics = json.loads(value)
                physics["viscosity"] = float(physics["viscosity"]) * 1.01
                alternative = json.dumps(physics, sort_keys=True, indent=2) + "\n"
            elif path.endswith("taylor_green.csv"):
                lines = value.splitlines(True)
                if len(lines) > 1:
                    lines[1] = lines[1].replace(",0.2500000000,", ",0.2510000000,")
                    alternative = "".join(lines)
            elif path.endswith("cavity_centerline.csv"):
                lines = value.splitlines(True)
                if len(lines) > 1:
                    lines[1] = lines[1].replace(",-0.38289", ",-0.38189")
                    alternative = "".join(lines)
            elif path.endswith("acceptance.json"):
                acceptance = json.loads(value)
                acceptance["max_divergence"] = float(acceptance["max_divergence"]) * 2
                alternative = json.dumps(acceptance, sort_keys=True, indent=2) + "\n"
            if alternative != value:
                return dict(foreign_path=path,
                            original_sha256=hashlib.sha256(value.encode()).hexdigest(),
                            alternative_sha256=hashlib.sha256(alternative.encode()).hexdigest())
        raise ValueError("No necessary foreign input was found for this participant")
    else:
        for order in truth["orders"]:
            path = f"/workspace/orders/{order['release']}.json"
            if path in local:
                continue
            revised = [{**o, "quantity_sets": o["quantity_sets"] + int(o == order)} for o in truth["orders"]]
            plan = freeform.plant_schedule(revised)
            ready = {r:d for d,r,_ in plan if r != "grill-guard"}
            if sum(n for _,r,n in plan if r == order["release"]) != order["quantity_sets"] + 1:
                raise ValueError("Alternative release cannot be completed")
            booking = proof["customer_booking"]
            try:
                freight.check_booking(revised,ready,truth["quotes"],booking["bookings"],booking["loads"])
            except ValueError:
                freight.optimal_plan(revised,ready,truth["quotes"])
            return dict(foreign_path=path, release=order["release"], original_sets=order["quantity_sets"],
                        alternative_sets=order["quantity_sets"]+1)
    raise ValueError("No necessary foreign input was found for this participant")


def audit(case, reg, inputs, truth):
    feasibility = read_json(case / "feasibility.json")
    if not feasibility.get("passed"):
        raise ValueError("Registered material-feasibility witness did not pass")
    opening = inputs["startup"]
    all_paths = set().union(*(files.keys() for files in opening.values()))
    bindings = read_json(case / "bindings.json")
    privacy = {}
    for actor, files in opening.items():
        expected = all_paths - files.keys()
        observed = bindings[actor].get("absent_foreign_opening_paths")
        if observed is None and expected:
            raise ValueError("Foreign opening paths lack a physical privacy check")
        if observed is not None and set(observed) != expected:
            raise ValueError("Foreign path check differs from the private allocation")
        privacy[actor] = len(expected)
    alternate_worlds = {}
    if reg["task"].endswith("-distributed"):
        pooled = {p:v for files in opening.values() for p,v in files.items()}
        alternate_worlds = {actor: foreign_fact_witness(reg["task"], local, pooled, truth, feasibility["task"])
                            for actor,local in opening.items()}
    terminal = {}
    for obs in events(case / "observations.jsonl.gz"):
        if obs["phase"] != "terminal":
            continue
        actor = obs["actor"]
        snapshot = obs["snapshot"]
        changed = {}
        for area in ("/workspace", "/var/tmp/exports", "temporary_files"):
            for name, val in snapshot.get(area, {}).items():
                parts = PurePosixPath(name).parts
                if any(p.startswith(".swarmform-stop-") for p in parts) or name.startswith("/var/tmp/exports/messages/"):
                    continue
                raw = base64.b64decode(val, validate=True)
                if name not in opening[actor] or raw != opening[actor][name].encode():
                    changed[name] = raw
        matches = media_batch.matched_artifacts(changed, truth) if reg["task"].startswith("ffmpeg-") else {}
        terminal[actor] = dict(observation=obs["sequence"], capture_gaps=len(snapshot.get("capture_gaps", [])),
                               visible_artifacts={k: hashlib.sha256(v).hexdigest() for k,v in changed.items()},
                               media_frame_matches=sorted(set(matches.values())), media_master_paths=matches)
    if set(terminal) != set(opening):
        raise ValueError("Missing physical-stop terminal observation")
    result = dict(feasibility_witness_passed=True, missing_private_files_checked=privacy,
                  foreign_fact_witnesses=alternate_worlds, terminal=terminal)
    if truth.get("task") == "programbench_release":
        edition_by_hash = {h: (booking, edition) for booking, pair in truth["editions"].items()
                           for h, edition in zip(pair, ("A", "B"), strict=True)}
        result["edition_artifacts"] = [
            dict(actor=actor, path=name, booking=edition_by_hash[h][0], edition=edition_by_hash[h][1],
                 matches_binding_order=(h == truth["released"].get(edition_by_hash[h][0])))
            for actor, stop in terminal.items() for name, h in stop["visible_artifacts"].items()
            if h in edition_by_hash
        ]
    return result
