"""Preview a working draft and its source coverage. --keep NAME retains the selected draft in project storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from submit import copy_candidate, project_name, source_coverage


def build_status(work, assessment):
    release = json.loads((work / "release.json").read_bytes())
    name = release["assessment" if assessment else "build"]
    client = work / "projects.py"
    if client.is_file():
        listing = subprocess.check_output([sys.executable, str(client), "list"])
        size = next((v["bytes"] for v in json.loads(listing)["artifacts"] if v["name"] == name), None)
    else:
        try:
            size = (Path("/var/tmp/exports/project") / name).stat().st_size
        except FileNotFoundError:
            size = None
    return {"name": name, "starter_bytes": release["assessment_starter_bytes" if assessment else "starter_bytes"],
            "current_bytes": size}


def planning_preview(work, candidate):
    from check_solution import check
    problem = json.loads((work / "problem.json").read_text())
    routes = {}
    for name in problem["routing_files"]:
        path = work / name
        if path.is_file():
            routes.update(json.loads(path.read_text()))
    plan = json.loads(candidate.read_text())
    results = {}
    for calendar in problem["scenarios"]:
        path = work / calendar["calendar_file"]
        if not path.is_file():
            continue
        draft = plan["plans"][calendar["id"]]
        rows = draft["operations"]
        calendar.update(json.loads(path.read_text()))
        calendar["latest_finish"] = json.loads((work / problem["limits_file"]).read_text())["deadline"]
        for job in calendar["operations"]:
            job["options"] = routes.get(job["id"], {})
        local = [r for r in rows if r["id"] in routes]
        bound = draft.get("lower_bound_path", [])
        partial = dict(draft, operations=local, lower_bound_path=bound if all(k in routes for k in bound) else [])
        checked = check(calendar, partial)
        results[calendar["id"]] = {"checked_rows": checked["scheduled_operations"],
                                   "rows_without_routing": [r["id"] for r in rows if r["id"] not in routes],
                                   "errors": checked["errors"], "certificate_errors": checked["certificate_errors"]}
    return {"local_calendar_checks": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="Local working draft or project:PATH")
    parser.add_argument("--assessment", action="store_true", help="Preview the release assessment")
    parser.add_argument("--keep", metavar="NAME", help="Retain this draft by name in the project work area")
    args = parser.parse_args()
    work = Path("/workspace")
    with tempfile.TemporaryDirectory() as scratch:
        candidate = None
        if args.file:
            if args.file.startswith("project:"):
                candidate = Path(scratch) / "candidate"
                try:
                    copy_candidate(args.file, work, candidate)
                except ValueError as error:
                    parser.error(str(error))
            else:
                candidate = Path(args.file)
        preview(work, candidate, args.keep, parser, args.assessment)


def preview(work, candidate, keep, parser, assessment):
    output = source_coverage(work)
    output["project_assessment" if assessment else "project_build"] = build_status(work, assessment)
    if candidate:
        data = candidate.read_bytes()
        output["candidate_sha256"] = hashlib.sha256(data).hexdigest()
        try:
            if assessment:
                report = json.loads(data)
                if not isinstance(report, dict) or not any(report.get("feasible", "missing") is v for v in (True, False, None)):
                    raise ValueError("Assessment needs a feasible field containing true, false or null")
                output["reported_feasible"] = report["feasible"]
                if output["release"] == "TREE-CLI":
                    output["reported_commands"] = sorted({row["argv"][0] for row in report.get("conflicts", [])})
                else:
                    rows = report.get("obstructions", [report] if "scenario" in report else [])
                    output["reported_calendars"] = sorted({row["scenario"] for row in rows})
            elif output["release"] == "TREE-CLI":
                check = runpy.run_path(str(candidate))["run"]
                examples = json.loads((work / "examples.json").read_bytes())
                output["public_examples"] = [check(e["argv"], e["stdin"]) == e["result"] for e in examples]
            else:
                output.update(planning_preview(work, candidate))
        except (ValueError, KeyError, TypeError, IndexError, SyntaxError, RuntimeError) as error:
            output["candidate_error"] = str(error)
    if keep is not None:
        if not candidate:
            parser.error("--keep needs a local draft")
        try:
            project_name(keep)
        except ValueError as error:
            parser.error(str(error))
        client = work / "projects.py"
        if client.is_file():
            with tempfile.NamedTemporaryFile() as snapshot:
                snapshot.write(data)
                snapshot.flush()
                receipt = subprocess.check_output([sys.executable, str(client), "write", keep, snapshot.name])
            output["retained"] = json.loads(receipt)
        else:
            dest = Path("/var/tmp/exports/project") / keep
            mask = os.umask(0)
            try:
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o777)
            finally:
                os.umask(mask)
            with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".draft-", delete=False) as snapshot:
                temporary = Path(snapshot.name)
            try:
                temporary.write_bytes(data)
                temporary.chmod(0o666)
                os.replace(temporary, dest)
            finally:
                temporary.unlink(missing_ok=True)
            output["retained"] = {"name": keep, "sha256": output["candidate_sha256"]}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
