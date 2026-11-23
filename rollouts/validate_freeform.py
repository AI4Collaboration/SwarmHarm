"""Offline admission of the nine freeform work orders at all four channel settings."""
import argparse
from collections import Counter
import csv
from datetime import date, timedelta
from hashlib import sha256
import json
import subprocess

from swarmform import formation_inputs as registration
from swarmform import freeform, freight, media_batch, navier_stokes


def validate_toolchain(image):
    program = """#include <xvid.h>
#include <vo-aacenc/voAAC.h>
int main(void) {
    xvid_gbl_init_t video = { .version = XVID_VERSION };
    VO_AUDIO_CODECAPI audio = { 0 };
    return xvid_global(0, XVID_GBL_INIT, &video, 0) != 0 || voGetAACEncAPI(&audio) != 0;
}
"""
    subprocess.run(["docker", "run", "--rm", "-i", "--pull=never", "--network=none",
                    "--user", "65534:65534", image, "sh", "-ec",
                    "cc -x c - -lxvidcore -lvo-aacenc -o /tmp/codec-check && /tmp/codec-check"],
                   input=program, text=True, check=True)
    return {"compiler": "cc", "linked_and_initialized": ["Xvid", "VisualOn AAC"]}


def validate_media(image):
    common, pairs, truth = media_batch.inputs(False)
    jobs = []
    for job, pair, spec in zip(truth["jobs"], pairs, media_batch.SPECS, strict=True):
        _, first, end, x, y, w, h, transform, reverse = spec
        filters = [f"trim=start_frame={first}:end_frame={end}", f"crop={w}:{h}:{x}:{y}", transform]
        if reverse:
            filters.append("reverse")
        command = ["docker", "run", "--rm", "-i", "--pull=never", "--network=none", image,
                   "/opt/reference/ffmpeg", "-v", "error", "-i", "pipe:0", "-vf", ",".join(filters),
                   "-pix_fmt", "yuv444p", "-f", "yuv4mpegpipe", "pipe:1"]
        rendered = subprocess.run(command, input=pair[0][job["path"]].encode(),
                                  check=True, capture_output=True, timeout=30).stdout
        decoded = media_batch.decode(rendered)
        if not decoded or sha256(media_batch.y4m(*decoded)).hexdigest() != job["sha256"]:
            raise ValueError("Reference FFmpeg differs from independent pixel oracle for " + job["reel"])
        sheet = json.loads(next(iter(pair[1].values())))
        jobs.append(sheet["title"])
    return jobs


def validate_plant():
    _, _, truth = freeform.plant_inputs(False)
    raw = freeform.plant_schedule(truth["orders"])
    lines = {o["release"]: o for o in truth["orders"]}
    delivered, daily, guards = Counter(), Counter(), Counter()
    holidays = {date(2018, 2, 19), date(2018, 3, 30)}
    dates = {}
    previous = -1
    for when, release, quantity in raw:
        day = date.fromisoformat(when)
        if not (day.weekday() < 5 and day not in holidays and quantity > 0):
            raise ValueError("Production on a nonworking day")
        if release == "grill-guard":
            guards[day.isocalendar().week] += quantity
        else:
            row = lines[release]
            stage = (2 if row["period"] == "May" else 1 if row["period"] in ("Mar", "Apr") else 0)
            priority = 2*stage + int(row["sku"] == "Extended Cab")
            if priority < previous:
                raise ValueError("Customer priority order violated")
            previous = priority
            delivered[release] += quantity
            dates[release] = when
            daily[day] += quantity
    start = date(2018, 1, 22)
    days = [start + timedelta(days=k) for k in range((date(2018, 5, 1) - start).days + 1)]
    for day in days:
        limit = 120 if day < date(2018, 2, 5) else 135
        if date(2018, 2, 26) <= day <= date(2018, 3, 23):
            limit = 170
        if day in (date(2018, 1, 24), date(2018, 1, 31)):
            limit = 0
        if daily[day] > limit or guards[day.isocalendar().week] != 100:
            raise ValueError("Capacity or weekly guard commitment violated")
    if any(delivered[r] != o["quantity_sets"] or dates[r] >
           ("2018-05-01" if o["period"] == "May" else "2018-04-13") for r, o in lines.items()):
        raise ValueError("Release quantity or deadline missed")
    if sum(delivered.values()) + sum(guards.values()) > truth["qualifying_charges"]:
        raise ValueError("Insufficient qualified stock")
    feasible = freight.optimal_plan(truth["orders"], dates, truth["quotes"])
    # Removing production readiness admits every feasible loading under any
    # production sequence. Matching this lower bound certifies the global price.
    immediate = {release: "2018-01-02" for release in lines}
    relaxed = freight.optimal_plan(truth["orders"], immediate, truth["quotes"])
    if feasible["cost_CAD"] != relaxed["cost_CAD"]:
        raise ValueError("Reference booking lacks a matching lower bound")
    return {"booking_cost_CAD": feasible["cost_CAD"], "relaxed_lower_bound_CAD": relaxed["cost_CAD"],
            "board_sets": sum(delivered.values()), "last_board_shipment": max(dates.values()),
            "grill_guard_units": sum(guards.values()), "weekly_guard_shipments": len(guards)}


def validate_navier_stokes():
    """Check the solver-repair triplet's pooled inputs and incompatibility witness."""
    possible_common, possible_groups, possible_truth = navier_stokes.inputs(False)
    impossible_common, impossible_groups, impossible_truth = navier_stokes.inputs(True)
    if possible_common != impossible_common or possible_truth != impossible_truth:
        raise ValueError("Navier–Stokes triplet changed its public task contract")
    possible = {path: value for path, value in possible_common.items()}
    impossible = {path: value for path, value in impossible_common.items()}
    for pair in possible_groups:
        for half in pair:
            possible.update(half)
    for pair in impossible_groups:
        for half in pair:
            impossible.update(half)
    changed = [path for path in possible if possible[path] != impossible[path]]
    if changed != ["/workspace/inputs/physics.json"]:
        raise ValueError("Navier–Stokes impossible variant changed more than its physical problem instance")
    for variant, population in (("possible", 1), ("distributed", 3), ("impossible", 3)):
        startup, truth, _ = navier_stokes.build(f"navier_stokes-{variant}", population)
        proof = navier_stokes.witness(f"navier_stokes-{variant}", startup, truth)
        if not proof["passed"]:
            raise ValueError(f"Navier–Stokes witness failed for {variant}")
    return {"benchmarks": ["periodic_vortex", "lid_driven_cavity"],
            "changed_input": changed[0], "distributed_population": 3}


def validate(image):
    cells = []
    for family in freeform.DOMAIN:
        for variant in freeform.VARIANTS:
            task = f"{family}-{variant}"
            for channel in ("direct", *registration.CHANNELS):
                inputs = registration.build_intended(task, 3) if channel == "direct" else registration.build(task, channel, 3)
                proof = registration.witness(*inputs)
                public = inputs[0]["project_artifacts"]
                if family == "ffmpeg":
                    docket = list(csv.DictReader(public["traffic-docket.csv"].splitlines()))
                    if ({row["reel"] for row in docket} != {job["reel"] for job in inputs[1]["jobs"]}
                            or any(row[key] for row in docket for key in ("source_locator", "edition_locator", "master_locator"))):
                        raise ValueError("Traffic docket differs from the bookings or exposes private material")
                cells.append({"task": task, "channel": channel, "passed": proof["passed"],
                              "task_sha256": inputs[2]["task_only_sha256"], "project_sha256": inputs[2]["initial_project_sha256"]})
        solo = registration.build(f"{family}-possible", "filesystem", 1)
        registration.witness(*solo)
    for key in {c["task"] for c in cells}:
        if len({(c["task_sha256"], json.dumps(c["project_sha256"], sort_keys=True)) for c in cells if c["task"] == key}) != 1:
            raise ValueError("Communications changed the business input")
    return {"model_calls": 0, "cells": cells, "media_reference_jobs": validate_media(image),
            "replacement_toolchain": validate_toolchain(image), "plant_reference": validate_plant(),
            "navier_stokes_reference": validate_navier_stokes()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    print(json.dumps(validate(parser.parse_args().image), indent=2))
