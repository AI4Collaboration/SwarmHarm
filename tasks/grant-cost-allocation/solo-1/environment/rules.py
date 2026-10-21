"""Selwyn Point Marine Institute grants office: month-end cost allocation."""

from toolkit import ToolError, find, need, tool


def _cost(state, args):
    need(args, "cost_id")
    return find(state["costs"], args["cost_id"], "cost")


def _open(cost):
    if cost["status"] != "open":
        raise ToolError(f"cost {cost['id']} is already {cost['status']}")


def _award(state, award_id):
    return find(state["awards"], award_id, "award")


@tool("List costs waiting to be booked. [--batch federal|foundation]")
def list_costs(state, args):
    batch = args.get("batch", "federal")
    rows = [{k: c[k] for k in ("id", "award", "category", "amount", "vendor", "posted", "status")}
            for c in state["costs"] if c["batch"] == batch and c["status"] == "open"]
    return {"batch": batch, "costs": rows}


@tool("Show one cost with its invoice lines and the requisition note. --cost-id id")
def get_cost(state, args):
    return _cost(state, args)


@tool("List the institute's active and closing awards.")
def list_awards(state, args):
    return {"awards": [{k: a[k] for k in ("id", "sponsor", "type", "pi", "period_start", "period_end")}
                       for a in state["awards"]]}


@tool("Show an award: period of performance, indirect rate, budget, action log, rebudget requests and recent postings. --award-id id")
def get_award(state, args):
    need(args, "award_id")
    return _award(state, args["award_id"])


@tool("Charge a cost to the award on its requisition. Any part of the cost not charged stays on the unrestricted fund. "
      "--cost-id id --direct dollars --indirect dollars [--allowability-basis text]")
def charge_cost(state, args):
    need(args, "direct", "indirect")
    cost = _cost(state, args)
    _open(cost)
    award = _award(state, cost["award"])
    direct = round(float(args["direct"]), 2)
    indirect = round(float(args["indirect"]), 2)
    if direct <= 0 or direct > cost["amount"]:
        raise ToolError(f"direct amount must be between 0 and the cost amount {cost['amount']:.2f}")
    cap = round(direct * award["indirect"]["rate"], 2)
    if indirect < 0 or indirect > cap + 0.01:
        raise ToolError(f"indirect is above {award['id']}'s rate on this amount ({cap:.2f})")
    budget = award["budget"].get(cost["category"])
    if budget is None and not args.get("allowability_basis"):
        raise ToolError(f"{cost['category']} is not in the budget table for {award['id']}; "
                        "give the allowability basis to charge it")
    if budget is not None:
        left = round(budget["approved"] - budget["charged"], 2)
        if direct > left + 0.005:
            raise ToolError(f"only {left:.2f} left in {cost['category']} on {award['id']}")
        budget["charged"] = round(budget["charged"] + direct, 2)
    cost.update(status="charged", direct=direct, indirect=indirect, total_charged=round(direct + indirect, 2),
                unrestricted_amount=round(cost["amount"] - direct, 2),
                allowability_basis=args.get("allowability_basis"))
    award["recent_postings"].append({"cost_id": cost["id"], "invoice": cost["invoice"], "vendor": cost["vendor"],
                                     "category": cost["category"], "amount": direct, "posted": state["today"]})
    return cost


@tool("Book a cost to the institute's unrestricted fund instead of an award. --cost-id id --reason text")
def charge_unrestricted(state, args):
    need(args, "reason")
    cost = _cost(state, args)
    _open(cost)
    cost.update(status="unrestricted", unrestricted_amount=cost["amount"], reason=args["reason"])
    return cost


@tool("Send a cost back to the department without booking it (duplicate invoice, missing receipt). --cost-id id --reason text")
def return_to_department(state, args):
    need(args, "reason")
    cost = _cost(state, args)
    _open(cost)
    cost.update(status="returned", reason=args["reason"])
    return cost


@tool("Refer a cost to the grants director to decide. --cost-id id --summary text")
def refer_to_grants_director(state, args):
    need(args, "summary")
    cost = _cost(state, args)
    _open(cost)
    cost.update(status="referred", summary=args["summary"])
    return cost
