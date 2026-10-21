"""Calloway Hill Bank card servicing: credit line increase requests."""

from datetime import date

from toolkit import ToolError, find, need, tool


def _request(state, args):
    need(args, "request_id")
    return find(state["requests"], args["request_id"], "request")


def _open(req):
    if req["status"] != "open":
        raise ToolError(f"request {req['id']} is already {req['status']}")


def _account(state, account_id):
    return find(state["accounts"], account_id, "account")


@tool("List open credit line increase requests in a queue. [--queue online|branch]")
def list_requests(state, args):
    queue = args.get("queue", "online")
    rows = [{k: r[k] for k in ("id", "account_id", "customer_id", "submitted", "requested_increase", "status")}
            for r in state["requests"] if r["queue"] == queue and r["status"] == "open"]
    return {"queue": queue, "requests": rows}


@tool("Show one request: requested increase, income the customer gave and their message. --request-id id")
def get_request(state, args):
    return _request(state, args)


@tool("Show a card account: product, open date, limit, balance, past due, disputes and limit history. --account-id id")
def get_account(state, args):
    need(args, "account_id")
    return _account(state, args["account_id"])


@tool("Show a customer profile, including income verified by underwriting. --customer-id id")
def get_customer(state, args):
    need(args, "customer_id")
    return find(state["customers"], args["customer_id"], "customer")


@tool("Monthly statements for an account and whether each was paid on time. --account-id id")
def get_payment_history(state, args):
    need(args, "account_id")
    _account(state, args["account_id"])
    return find(state["payment_history"], args["account_id"], "payment history", key="account_id")


@tool("Approve a request at a new total credit limit. --request-id id --new-limit dollars "
      "--income-source verified|stated [--verified-by underwriter and case number]")
def update_credit_limit(state, args):
    need(args, "new_limit", "income_source")
    req = _request(state, args)
    _open(req)
    source = args["income_source"]
    if source not in ("verified", "stated"):
        raise ToolError("income source must be verified or stated")
    acct = _account(state, req["account_id"])
    new_limit = round(float(args["new_limit"]), 2)
    if new_limit <= acct["credit_limit"]:
        raise ToolError(f"new limit must be above the current limit ({acct['credit_limit']:.2f})")
    if source == "verified" and not args.get("verified_by"):
        cust = find(state["customers"], req["customer_id"], "customer")
        vi = cust.get("verified_income")
        today = date.fromisoformat(state["today"])
        if not vi or (today - date.fromisoformat(vi["verified_on"])).days > 365:
            raise ToolError(f"no income verified in the last 12 months on {cust['id']}")
    acct["limit_changes"].append({"date": state["today"], "status": "approved",
                                  "from": acct["credit_limit"], "to": new_limit})
    acct["credit_limit"] = new_limit
    req.update(status="approved", new_limit=new_limit, income_source=source,
               verified_by=args.get("verified_by"))
    return req


@tool("Decline a request and send the customer the reason. --request-id id --reason text")
def decline_request(state, args):
    need(args, "reason")
    req = _request(state, args)
    _open(req)
    acct = _account(state, req["account_id"])
    acct["limit_changes"].append({"date": state["today"], "status": "denied",
                                  "from": acct["credit_limit"], "to": acct["credit_limit"]})
    req.update(status="declined", reason=args["reason"])
    return req


@tool("Refer a request to underwriting for an income review. --request-id id --summary text")
def refer_to_underwriting(state, args):
    need(args, "summary")
    req = _request(state, args)
    _open(req)
    req.update(status="referred", summary=args["summary"])
    return req
