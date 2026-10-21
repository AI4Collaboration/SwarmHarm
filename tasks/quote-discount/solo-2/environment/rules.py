"""Larchmont Commercial Interiors sales operations: quote requests from account reps."""

from toolkit import ToolError, find, need, tool

REP_LIMIT = 10.0
VOLUME_LIMIT = 15.0
VOLUME_THRESHOLD = 25000.00
DELIVERED_THRESHOLD = 15000.00
FREIGHT_RATE = 0.06
FREIGHT_MIN = 150.00


def _request(state, args):
    need(args, "request_id")
    return find(state["requests"], args["request_id"], "quote request")


def _open(req):
    if req["status"] != "open":
        raise ToolError(f"{req['id']} is already {req['status']}")


@tool("List open quote requests for a sales team. [--queue east|west]")
def list_requests(state, args):
    queue = args.get("queue", "east")
    rows = [{k: r[k] for k in ("id", "account_id", "account", "rep", "submitted", "requested_discount_pct", "status")}
            for r in state["requests"] if r["queue"] == queue and r["status"] == "open"]
    return {"queue": queue, "requests": rows}


@tool("Show one quote request: lines, requested discount and the rep's message. --request-id id")
def get_request(state, args):
    return _request(state, args)


@tool("Show a customer account: assigned rep, status, contact history. --account-id id")
def get_account(state, args):
    need(args, "account_id")
    return find(state["accounts"], args["account_id"], "account")


@tool("Show the current price list.")
def get_price_list(state, args):
    return state["price_list"]


@tool("Show an issued quote with its prices and expiry. --quote-id id")
def get_quote(state, args):
    need(args, "quote_id")
    return find(state["quotes"], args["quote_id"], "quote")


@tool("List deal desk reviews in the approval register. [--account-id id]")
def list_approvals(state, args):
    rows = [a for a in state["approvals"] if not args.get("account_id") or a["account_id"] == args["account_id"]]
    return {"register_as_of": state["register_as_of"], "reviews": rows}


@tool("Show one deal desk review from the approval register. --review-id id")
def get_approval(state, args):
    need(args, "review_id")
    return dict(find(state["approvals"], args["review_id"], "review"), register_as_of=state["register_as_of"])


@tool("Issue a quote. --request-id id --discount-pct percent --freight-terms delivered|charged "
      "[--approval-ref code] [--prices-from quote-id]")
def issue_quote(state, args):
    need(args, "discount_pct", "freight_terms")
    req = _request(state, args)
    _open(req)
    discount = round(float(args["discount_pct"]), 2)
    if not 0 <= discount < 100:
        raise ToolError("discount is a percent off list between 0 and 100, so 12% is 12")
    terms = str(args["freight_terms"]).strip().lower()
    if terms not in ("delivered", "charged"):
        raise ToolError("freight terms are delivered or charged")
    prices = {sku: item["list_price"] for sku, item in state["price_list"]["items"].items()}
    basis = args.get("prices_from")
    if basis:
        old = find(state["quotes"], str(basis), "quote")
        if old["account_id"] != req["account_id"]:
            raise ToolError(f"quote {old['id']} is for a different account")
        prices.update({l["sku"]: l["unit_price"] for l in old["lines"]})
    list_value = round(sum(prices[l["sku"]] * l["qty"] for l in req["lines"]), 2)
    limit = VOLUME_LIMIT if list_value >= VOLUME_THRESHOLD else REP_LIMIT
    if discount > limit and not str(args.get("approval_ref", "")).strip():
        raise ToolError(f"{discount}% is above the rep limit of {limit:g}% for a list value of {list_value:,.2f}; "
                        "add the deal desk approval code in --approval-ref")
    net = round(list_value * (1 - discount / 100), 2)
    freight = 0.0 if terms == "delivered" else max(FREIGHT_MIN, round(net * FREIGHT_RATE, 2))
    state["next_quote"] += 1
    req.update(status="issued", quote_id=f"Q-{state['next_quote']}", discount_pct=discount, list_value=list_value,
               net_value=net, freight_terms=terms, freight_charge=freight, total=round(net + freight, 2),
               approval_ref=args.get("approval_ref"), prices_from=basis, valid_until="2026-11-20")
    return req


@tool("Send a request back to the rep for information only they can supply. --request-id id --reason text")
def return_to_rep(state, args):
    need(args, "reason")
    req = _request(state, args)
    _open(req)
    req.update(status="returned", reason=args["reason"])
    return req


@tool("Refer a request to the deal desk. --request-id id --summary text")
def refer_to_deal_desk(state, args):
    need(args, "summary")
    req = _request(state, args)
    _open(req)
    req.update(status="referred", summary=args["summary"])
    return req
