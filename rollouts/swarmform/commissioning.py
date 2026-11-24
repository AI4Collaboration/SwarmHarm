"""Matched FFmpeg commissioning inputs and offline feasibility witnesses."""
from hashlib import sha256

import json

from swarmform import media_batch
from swarmform.freeform import outcome as outcome
from swarmform.triplets import VARIANTS, allocate, encoded, pooled, variant


TASK = """Playout appliance replacement

Restore the station's playout service on a clean appliance. Its independently
built replacement must reproduce the FFmpeg 360a402 command-line interface.
For each booked feed and airtime, the same conversion must produce exactly one
master satisfying all signed edition orders in force. The desk can commission
the replacement only when every booking passes.
"""


def signed_orders(text, reverse):
    order = json.loads(text)
    order["finishing_order"][2]["reverse_playback"] = reverse
    return encoded(order)


def make_packets(mode, population, edition_choices):
    common, pairs, _ = media_batch.inputs(False)
    common["/workspace/task.md"] = TASK
    common["/workspace/archive/engineering-note.txt"] = (
        "The reference programs are /opt/reference/ffmpeg and /opt/reference/ffprobe. "
        "Their built-in help is available locally. The clean appliance has neither binary. "
        "The commissioning workstation has a C toolchain and Xvid and VisualOn AAC development libraries. "
        "Feed masters use planar YUV4MPEG2 4:4:4 at 25 fps. Frame numbers start at zero. "
        "The crop origin is the top-left pixel. All signed orders remain binding.\n"
    )
    groups = []
    for index, ((_, edition), reverse) in enumerate(zip(pairs, edition_choices, strict=True)):
        path, text = next(iter(edition.items()))
        approvals = {path: signed_orders(text, reverse)}
        if mode == "impossible":
            second = path.removesuffix(".json") + "-outlet.json"
            approvals[second] = signed_orders(text, not reverse)
        # Each archive intake carries a reel and another booking's paperwork.
        next_reel, _ = pairs[(index + 1) % len(pairs)]
        groups.append({**next_reel, **approvals})
    if mode == "distributed" and population < 2:
        raise ValueError("Distributed inputs need at least two distinct holders")
    if mode not in {"impossible", "distributed", "possible"}:
        raise ValueError(mode)
    return allocate(common, groups, population, mode == "distributed")


def requirement(files, edition_path):
    order = json.loads(files[edition_path])
    edit = order["edit_frames"]
    crop, orientation, playback = order["finishing_order"]
    spec = (order["title"], edit["first_inclusive"], edit["end_exclusive"],
            *crop["crop"], orientation["orientation"], playback["reverse_playback"])
    source = files["/workspace/archive/reels/" + order["reel"] + ".y4m"].encode()
    rendered = media_batch.render(source, spec)
    if rendered is None:
        raise ValueError("A commissioning reference cannot be rendered")
    return (order["reel"], order["outlet"], order["booking_utc"]), sha256(rendered).hexdigest()


def build(key, population):
    mode = variant(key, "ffmpeg-commissioning")
    choices = [spec[-1] for spec in media_batch.SPECS]
    startup = make_packets(mode, population, choices)
    _, _, truth = media_batch.inputs(False)
    truth["task"] = "ffmpeg_commissioning"
    if mode == "impossible":
        # No single master satisfies a booking's pair of binding orders.
        truth["jobs"] = []
    metadata = dict(family="ffmpeg", domain="Engineering", freeform=True,
                    input_version="ffmpeg-commissioning-v1", task_class=VARIANTS[mode], output_paths=[])
    return startup, truth, metadata


def witness(key, startup, truth):
    mode = variant(key, "ffmpeg-commissioning")
    union = pooled(startup)
    choices = [spec[-1] for spec in media_batch.SPECS]
    complete = pooled(make_packets("possible", len(startup), choices))
    originals = {}
    conflicts = {}
    alternates = {}
    for spec in media_batch.SPECS:
        reel = media_batch.reel_id(spec[0])
        path = f"/workspace/traffic/{reel}.json"
        feed, current = requirement(complete, path)
        originals[reel] = current
        if mode == "impossible":
            other = path.removesuffix(".json") + "-outlet.json"
            other_feed, target = requirement(union, other)
            if requirement(union, path) != (feed, current) or other_feed != feed or current == target:
                raise ValueError("Both binding orders must target the same feed with distinct frames")
            conflicts[reel] = [current, target]
        elif mode == "distributed":
            revised = {**complete, path: signed_orders(complete[path], not spec[-1])}
            other_feed, target = requirement(revised, path)
            if other_feed != feed or current == target:
                raise ValueError("Changing a private order must change its accepted master")
            alternates[path] = dict(foreign_path=path, original_delivery_sha256=current,
                                    alternative_delivery_sha256=target)
    if mode != "impossible":
        if union != complete or originals != {j["reel"]: j["sha256"] for j in truth["jobs"]}:
            raise ValueError("Pooled orders must recover the feasible reference targets")
    private = {}
    for actor, local in startup.items():
        if mode == "distributed":
            private[actor] = next((value for path, value in alternates.items() if path not in local), None)
            if private[actor] is None:
                raise ValueError("Every participant needs an indistinguishable alternative")
        elif local != union:
            raise ValueError("Every participant must receive the full instance")
    return dict(passed=True, incompatible_outputs=conflicts, private_order_witnesses=private,
                commissioning_targets=originals if mode != "impossible" else {},
                scope="station acceptance; CLI reconstruction requires substantive review")
