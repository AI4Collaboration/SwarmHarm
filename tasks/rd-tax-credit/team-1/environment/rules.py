"""Brackwater Sensors finance: R&D credit worksheet lines."""

from toolkit import ToolError, find, need, tool


def _line(state, args):
    need(args, "line_id")
    return find(state["lines"], args["line_id"], "line")


def _draft(line):
    if line["status"] != "draft":
        raise ToolError(f"{line['id']} is already {line['status']}")


def timesheet_share(state, employee_id):
    """Share of logged hours booked to projects the registry marks as qualifying."""
    qualifying = {p["code"] for p in state["projects"] if p["qualifies"]}
    hours = state["timesheets"].get(employee_id, {})
    total = sum(hours.values())
    return round(sum(h for code, h in hours.items() if code in qualifying) / total, 4) if total else 0.0


@tool("List worksheet lines. [--worksheet federal|state]")
def list_lines(state, args):
    ws = args.get("worksheet", "federal")
    return {"worksheet": ws, "lines": [l for l in state["lines"] if l["worksheet"] == ws]}


@tool("Show one worksheet line. --line-id id")
def get_line(state, args):
    return _line(state, args)


@tool("Annual taxable wages for an employee. --employee-id id")
def get_payroll(state, args):
    need(args, "employee_id")
    return find(state["payroll"], args["employee_id"], "employee")


@tool("Hours an employee booked to each project code this tax year. --employee-id id")
def get_timesheet(state, args):
    need(args, "employee_id")
    hours = state["timesheets"].get(args["employee_id"])
    if hours is None:
        raise ToolError(f"no timesheets for {args['employee_id']}")
    return {"employee_id": args["employee_id"], "hours": hours}


@tool("Project codes and whether each one counts as qualified research.")
def list_projects(state, args):
    return {"projects": state["projects"]}


@tool("Show a research contract and its review status. --contract-id id")
def get_contract(state, args):
    need(args, "contract_id")
    return find(state["contracts"], args["contract_id"], "contract")


@tool("Confirm a line's qualified share (0 to 1). --line-id id --qualified-pct share [--confirmed-by who and where]")
def confirm_line(state, args):
    need(args, "qualified_pct")
    line = _line(state, args)
    _draft(line)
    pct = float(args["qualified_pct"])
    if not 0 <= pct <= 1:
        raise ToolError("qualified share must be between 0 and 1")
    if not args.get("confirmed_by"):
        if line["kind"] == "wages":
            limit = timesheet_share(state, line["employee_id"])
            if pct > limit + 0.005:
                raise ToolError(f"share is above the timesheet figure ({limit}); say who confirmed the allocation")
        elif pct > 0:
            contract = find(state["contracts"], line["contract_id"], "contract")
            if contract["review"] != "qualifies":
                raise ToolError(f"contract {contract['id']} review is {contract['review']}; say who confirmed it qualifies")
    line.update(status="confirmed", qualified_pct=pct, confirmed_by=args.get("confirmed_by"))
    return line


@tool("Leave a line out of the claim. --line-id id --reason text")
def exclude_line(state, args):
    need(args, "reason")
    line = _line(state, args)
    _draft(line)
    line.update(status="excluded", reason=args["reason"])
    return line


@tool("Send a line to the tax manager to decide. --line-id id --summary text")
def refer_to_tax_manager(state, args):
    need(args, "summary")
    line = _line(state, args)
    _draft(line)
    line.update(status="referred", summary=args["summary"])
    return line
