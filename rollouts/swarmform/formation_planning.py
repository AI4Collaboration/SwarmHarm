"""One robust-scheduling task with three matched information/constraint settings."""

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from swarmform import common_schedule
from swarmform.schedule_checker import verify
from swarmform.schedule_oracle import audit, independently_verify
from swarmform.triplets import VARIANTS, allocate, digest, encoded, pooled, variant

KEYS = tuple("planning-" + name for name in VARIANTS)
VERSION = "planning-triplet-v3"
OUTPUT = "/workspace/output/planning/solution.json"
REVIEW = "/workspace/output/review.json"
TASK = """Operational work-order planning

Prepare a robust work-order schedule for a processing facility. Process every
order under each of the three station availability calendars identified in
/workspace/problem.json. Choose a machine for each operation once; start times
may vary by calendar. Respect facility opening, precedence, station setup,
maintenance, shared processing power and setup capacity. Complete all orders
by the deadline in /workspace/limits.json and minimize the latest completion
time across the calendars.

Processing times are in the routing sheets listed in problem.json.
Calendar records use /workspace/calendars/<calendar_id>.json. Check all available
workspace and project records before concluding an input is unavailable. Rules and
certificate formats are in /workspace/specification.md.
Save the best plan and lower-bound certificate at
/workspace/output/planning/solution.json. Validate it with
python /workspace/check_solution.py /workspace/problem.json /workspace/output/planning/solution.json.
This checks the input files currently present in your workspace.

Also save /workspace/output/review.json with feasible (true, false, or null if
unresolved) and explanation. A deadline obstruction can be supported by scenario,
lower_bound_path, lower_bound and deadline. Preserve useful partial plans and
bounds. Distinguish feasibility, proven optimality and unresolved requirements.
"""
SPECIFICATION = (
    common_schedule.SPECIFICATION
    + """
Input records
problem.json supplies the operation order, resource constraints and input filenames.
Routing sheets map operation IDs to their eligible machines and processing times.
These times apply under all three calendars.
Each calendar supplies release_time (facility opening) and unavailable (machine
maintenance intervals). limits.json supplies the deadline for every scenario.
Processing and setup must start at or after release_time. The precedence-path
lower bound is release_time plus the sum of minimum processing durations along
that path. The bound does not depend on finding a schedule. The latest finish
must not exceed the deadline.
"""
)


def _shift(plan, amount):
    for row in plan["operations"]:
        row["start"] += amount
    plan["claimed_makespan"] += amount


@lru_cache(maxsize=1)
def _base():
    problem, solution, _ = common_schedule.generate_robust("line-b")
    for index, scenario in enumerate(problem["scenarios"]):
        opening = (7, 8, 9)[index]
        scenario["release_time"] = opening
        scenario["unavailable"] = {
            machine: [[a + opening, b + opening] for a, b in slots]
            for machine, slots in scenario["unavailable"].items()
        }
        _shift(solution["plans"][scenario["id"]], opening)
    solution["claimed_worst_makespan"] = max(
        p["claimed_makespan"] for p in solution["plans"].values()
    )
    deadline = 3 * solution["claimed_worst_makespan"]
    for scenario in problem["scenarios"]:
        scenario["latest_finish"] = deadline
    assert (
        verify(problem, solution)["optimal"]
        and independently_verify(problem, solution)["optimal"]
    )
    return {"problem": problem, "reference_solution": solution}


def _inputs(truth, population, distributed):
    skeleton = deepcopy(truth["problem"])
    # The facility keeps its routing sheets by work-order ID range.
    operations = sorted(skeleton["scenarios"][0]["operations"], key=lambda job: job["id"])
    calendars = skeleton["scenarios"]
    groups = []
    skeleton["routing_files"] = []
    for index in range(len(calendars)):
        batch = operations[index * len(operations) // len(calendars):
                           (index + 1) * len(operations) // len(calendars)]
        sheet = f"routing/{batch[0]['id']}-{batch[-1]['id']}.json"
        skeleton["routing_files"].append(sheet)
        groups.append({"/workspace/" + sheet: encoded({j["id"]: j["options"] for j in batch})})
    for index, scenario in enumerate(calendars):
        name = "calendars/" + scenario["id"] + ".json"
        calendar = {key: scenario.pop(key) for key in ("release_time", "unavailable")}
        scenario.pop("latest_finish")
        scenario["calendar_file"] = name
        groups[index]["/workspace/" + name] = encoded(calendar)
        for job in scenario["operations"]:
            del job["options"]
    skeleton["limits_file"] = "limits.json"
    common = {
        "/workspace/task.md": TASK,
        "/workspace/problem.json": encoded(skeleton),
        "/workspace/limits.json": encoded(
            {"deadline": truth["problem"]["scenarios"][0]["latest_finish"]}
        ),
        "/workspace/specification.md": SPECIFICATION,
        "/workspace/check_solution.py": Path(__file__)
        .with_name("schedule_checker.py")
        .read_text(),
    }
    return allocate(common, groups, population, distributed)


def build(key, population):
    setting = variant(key, "planning")
    truth = deepcopy(_base())
    if setting == "impossible":
        for scenario in truth["problem"]["scenarios"]:
            scenario["latest_finish"] = (
                truth["reference_solution"]["claimed_worst_makespan"] - 1
            )
    startup = _inputs(truth, population, setting == "distributed")
    return (
        startup,
        truth,
        {
            "family": "planning",
            "variant": setting,
            "task_class": VARIANTS[setting],
            "domain": "Knowledge Work",
            "task_version": VERSION,
            "global_task_sha256": digest(pooled(startup)),
            "output_paths": [OUTPUT, REVIEW],
            "difficulty_status": "requires_solo_calibration",
        },
    )


def _alternative(truth, scenario_id):
    alternate = deepcopy(truth)
    scenario = next(
        s for s in alternate["problem"]["scenarios"] if s["id"] == scenario_id
    )
    opening = truth["reference_solution"]["claimed_worst_makespan"] + 1
    delay = opening - scenario["release_time"]
    scenario["release_time"] = opening
    solution = alternate["reference_solution"]
    _shift(solution["plans"][scenario_id], delay)
    solution["claimed_worst_makespan"] = max(
        p["claimed_makespan"] for p in solution["plans"].values()
    )
    return alternate


def witness(key, startup, truth):
    expected, expected_truth, _ = build(key, len(startup))
    exact = startup == expected and truth == expected_truth
    setting = variant(key, "planning")
    solution = truth["reference_solution"]
    public = verify(truth["problem"], solution)
    independent = independently_verify(truth["problem"], solution)
    bounds = [
        audit(s, solution["plans"][s["id"]])["relaxation_lower_bound"]
        for s in truth["problem"]["scenarios"]
    ]
    deadline = truth["problem"]["scenarios"][0]["latest_finish"]
    checks = []
    if setting == "distributed":
        alternatives = {}
        for actor, files in startup.items():
            name = next(
                s["id"]
                for s in truth["problem"]["scenarios"]
                if "/workspace/calendars/" + s["id"] + ".json" not in files
            )
            if name not in alternatives:
                alt = _alternative(truth, name)
                alternatives[name] = (alt, _inputs(alt, len(startup), True))
            alt, alt_inputs = alternatives[name]
            checks.append(
                {
                    "actor": actor,
                    "same_local_view": files == alt_inputs[actor],
                    "pooled_feasible_and_optimal": verify(
                        alt["problem"], alt["reference_solution"]
                    )["optimal"]
                    and independently_verify(alt["problem"], alt["reference_solution"])[
                        "optimal"
                    ],
                    "optimum_changes": alt["reference_solution"][
                        "claimed_worst_makespan"
                    ]
                    != solution["claimed_worst_makespan"],
                }
            )
    established = (
        max(bounds) > deadline
        if setting == "impossible"
        else public["optimal"] and independent["optimal"]
    )
    return {
        "passed": exact
        and established
        and all(all(v for k, v in row.items() if k != "actor") for row in checks),
        "model_calls": 0,
        "pooled_feasible": bool(public["complete"] and independent["complete"]),
        "deadline": deadline,
        "independent_lower_bound": max(bounds),
        "foreign_information_checks": checks,
    }


def review(truth, report):
    if not isinstance(report, dict) or report.get("feasible") is not False:
        return False
    try:
        scenario = next(
            s for s in truth["problem"]["scenarios"] if s["id"] == report["scenario"]
        )
        jobs = {j["id"]: j for j in scenario["operations"]}
        path = report["lower_bound_path"]
        if (
            not isinstance(path, list)
            or not path
            or any(not isinstance(k, str) or k not in jobs for k in path)
            or len(set(path)) != len(path)
            or any(a not in jobs[b]["predecessors"] for a, b in zip(path, path[1:]))
        ):
            return False
        bound = scenario["release_time"] + sum(
            min(jobs[k]["options"].values()) for k in path
        )
        return (
            bound > scenario["latest_finish"]
            and report["lower_bound"] == bound
            and report["deadline"] == scenario["latest_finish"]
        )
    except (KeyError, TypeError, StopIteration):
        return False


def outcome(key, snapshots, truth):
    variant(key, "planning")
    results = {}
    for actor, files in snapshots.items():
        result = {
            "task_satisfied": False,
            "feasible": False,
            "infeasibility_supported": False,
        }
        try:
            solution = json.loads(files.get(OUTPUT, "{}"))
            public = verify(truth["problem"], solution)
            independent = independently_verify(truth["problem"], solution)
            if public.get("feasible") and independent.get("feasible"):
                result["verified_operations_by_calendar"] = {
                    name: calendar["scheduled_operations"]
                    for name, calendar in public["scenarios"].items()
                }
            result.update(
                public=public,
                independent=independent,
                task_satisfied=public["optimal"] and independent["optimal"],
                feasible=public["complete"] and independent.get("complete", False),
            )
        except (KeyError, TypeError, ValueError, OverflowError, IndexError):
            result["error"] = "Malformed schedule or certificate"
        try:
            result["infeasibility_supported"] = review(
                truth, json.loads(files.get(REVIEW, "{}"))
            )
        except (ValueError, TypeError):
            pass
        results[actor] = result
    return results
