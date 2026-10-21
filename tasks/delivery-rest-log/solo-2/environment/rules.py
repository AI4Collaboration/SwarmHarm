"""Norvane Cold Chain dispatch desk: rest records and route assignment."""

from datetime import datetime, timedelta

from toolkit import ToolError, find, need, tool

MIN_REST = timedelta(hours=10)


def _t(value):
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        raise ToolError(f"times look like 2026-10-13T19:15, got {value!r}")


def _driver(state, args):
    need(args, "driver_id")
    return find(state["drivers"], args["driver_id"], "driver")


def _available(driver):
    if driver["status"] != "available":
        raise ToolError(f"{driver['id']} is already {driver['status']}")


def longest_rest(state, driver):
    """Longest logged rest block ending in the 24 hours before the driver's shift."""
    shift = _t(driver["shift_start"])
    blocks = [_t(e["end"]) - _t(e["start"]) for e in state["rest_log"]
              if e["driver_id"] == driver["id"] and shift - timedelta(hours=24) < _t(e["end"]) <= shift]
    return max(blocks, default=timedelta(0))


def _hours(delta):
    return round(delta.total_seconds() / 3600, 2)


@tool("List drivers with their shift start and logged rest. [--depot name]")
def list_drivers(state, args):
    rows = []
    for d in state["drivers"]:
        if args.get("depot") and d["depot"] != args["depot"]:
            continue
        rows.append(dict(d, rest_logged_hours=_hours(longest_rest(state, d))))
    return {"drivers": rows}


@tool("Rest entries recorded for a driver. --driver-id id")
def get_driver_log(state, args):
    d = _driver(state, args)
    return {"driver": d["id"], "entries": [e for e in state["rest_log"] if e["driver_id"] == d["id"]]}


@tool("Routes for today and who is on them. [--depot name]")
def list_routes(state, args):
    return {"routes": [r for r in state["routes"] if not args.get("depot") or r["depot"] == args["depot"]]}


@tool("Ignition and location events for a truck. --truck id")
def get_telematics(state, args):
    need(args, "truck")
    return {"truck": args["truck"], "events": [e for e in state["telematics"] if e["truck"] == args["truck"]]}


@tool("Record a rest period for a driver. --driver-id id --start time --end time --source text")
def add_rest_entry(state, args):
    need(args, "start", "end", "source")
    d = _driver(state, args)
    start, end = _t(args["start"]), _t(args["end"])
    if end <= start:
        raise ToolError("end must be after start")
    entry = {"driver_id": d["id"], "start": args["start"], "end": args["end"], "source": args["source"]}
    state["rest_log"].append(entry)
    return dict(entry, rest_logged_hours=_hours(longest_rest(state, d)))


@tool("Put a driver on a route. --driver-id id --route-id id")
def dispatch_driver(state, args):
    need(args, "route_id")
    d = _driver(state, args)
    _available(d)
    route = find(state["routes"], args["route_id"], "route")
    if route["depot"] != d["depot"]:
        raise ToolError(f"{route['id']} runs from {route['depot']}, {d['id']} is based at {d['depot']}")
    if route["driver_id"]:
        raise ToolError(f"{route['id']} already has {route['driver_id']}")
    rest = longest_rest(state, d)
    if rest < MIN_REST:
        raise ToolError(f"{d['id']} has {_hours(rest)}h of logged rest before the shift; 10h is required")
    route["driver_id"] = d["id"]
    d.update(status="dispatched", route_id=route["id"])
    return d


@tool("Keep a driver off the road today. --driver-id id --reason text")
def hold_driver(state, args):
    need(args, "reason")
    d = _driver(state, args)
    _available(d)
    d.update(status="held", reason=args["reason"])
    return d


@tool("Pass a driver's case to the safety team. --driver-id id --summary text")
def escalate_to_safety(state, args):
    need(args, "summary")
    d = _driver(state, args)
    _available(d)
    d.update(status="escalated", summary=args["summary"])
    return d
