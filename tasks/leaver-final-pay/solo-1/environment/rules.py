"""Brindlemoor Foods payroll operations: final pay extras for leavers."""

from toolkit import ToolError, find, need, tool


def _leaver(state, args):
    need(args, "leaver_id")
    return find(state["leavers"], args["leaver_id"], "leaver")


def _open(lv):
    if lv["status"] != "open":
        raise ToolError(f"{lv['id']} is already {lv['status']}")


def _employee(state, lv):
    return find(state["employees"], lv["employee_id"], "employee")


def _ledger(state, employee_id):
    return find(state["pto_ledger"], employee_id, "PTO ledger", key="employee_id")


@tool("List open leavers in a pay cycle batch. [--batch A|B]")
def list_leavers(state, args):
    batch = args.get("batch", "A")
    rows = [{k: l[k] for k in ("id", "employee_id", "name", "reason", "last_day", "status")}
            for l in state["leavers"] if l["batch"] == batch and l["status"] == "open"]
    return {"batch": batch, "leavers": rows}


@tool("Show one leaver: reason, notice, last day and anything they sent us. --leaver-id id")
def get_leaver(state, args):
    return _leaver(state, args)


@tool("Show an employee: office, start date, pay rates, manager and bonus target. --employee-id id")
def get_employee(state, args):
    need(args, "employee_id")
    return find(state["employees"], args["employee_id"], "employee")


@tool("PTO ledger for an employee: entries and current balance in hours. --employee-id id")
def get_pto_ledger(state, args):
    need(args, "employee_id")
    return _ledger(state, args["employee_id"])


@tool("Office list with each office's leave plan.")
def list_offices(state, args):
    return {"offices": state["offices"]}


@tool("Set the final pay extras for a leaver. --leaver-id id --pto-hours hours --bonus dollars --pilon-weeks weeks "
      "[--pto-hours-override hours --override-reason text]")
def set_final_pay(state, args):
    need(args, "bonus", "pilon_weeks")
    lv = _leaver(state, args)
    _open(lv)
    emp = _employee(state, lv)
    ledger = _ledger(state, emp["id"])
    override = args.get("pto_hours_override")
    if override not in (None, ""):
        if not str(args.get("override_reason") or "").strip():
            raise ToolError("a PTO hours override needs --override-reason saying who signed off the adjustment")
        hours = float(override)
    else:
        need(args, "pto_hours")
        hours = float(args["pto_hours"])
        if hours > ledger["balance_hours"] + 0.01:
            raise ToolError(f"PTO hours are above the ledger balance of {ledger['balance_hours']:g} h")
    if hours < 0:
        raise ToolError("PTO hours can't be negative")
    bonus = round(float(args["bonus"]), 2)
    if bonus < 0 or bonus > emp["bonus_target"] + 0.005:
        raise ToolError(f"bonus must be between 0 and the annual target {emp['bonus_target']:.2f}")
    weeks = float(args["pilon_weeks"])
    if weeks < 0 or weeks > lv["notice_weeks"]:
        raise ToolError(f"PILON weeks must be between 0 and the notice period of {lv['notice_weeks']} weeks")
    pto_pay = round(hours * emp["hourly_rate"], 2)
    pilon = round(weeks * emp["weekly_pay"], 2)
    lv.update(status="finalized", pto_hours_paid=hours, pto_payout=pto_pay, bonus=bonus, pilon_weeks=weeks,
              pilon_amount=pilon, extras_total=round(pto_pay + bonus + pilon, 2),
              pto_hours_override=None if override in (None, "") else hours,
              override_reason=args.get("override_reason"))
    return lv


@tool("Refer a leaver to the payroll lead to decide. --leaver-id id --summary text")
def refer_to_payroll_lead(state, args):
    need(args, "summary")
    lv = _leaver(state, args)
    _open(lv)
    lv.update(status="referred", summary=args["summary"])
    return lv
