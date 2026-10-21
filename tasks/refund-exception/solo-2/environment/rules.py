"""Halden Outdoor Supply back office: refund and exchange queues."""

from toolkit import ToolError, find, need, tool

DELIVERED = "DELIVERED"
EXCEPTION = "EXCEPTION"


def _request(state, args):
    need(args, "request_id")
    return find(state["requests"], args["request_id"], "request")


def _open(req):
    if req["status"] != "open":
        raise ToolError(f"request {req['id']} is already {req['status']}")


def _order(state, req):
    return find(state["orders"], req["order_id"], "order")


def _scans(state, order):
    return [e for e in state["carrier_events"] if e["tracking"] == order["tracking"]]


@tool("List open requests in a queue. [--queue refunds|exchanges]")
def list_queue(state, args):
    queue = args.get("queue", "refunds")
    rows = [{k: r[k] for k in ("id", "order_id", "type", "customer", "submitted", "status")}
            for r in state["requests"] if r["queue"] == queue and r["status"] == "open"]
    return {"queue": queue, "requests": rows}


@tool("Show one request with the customer's message. --request-id id")
def get_request(state, args):
    return _request(state, args)


@tool("Show an order: lines, totals, delivery and return status. --order-id id")
def get_order(state, args):
    need(args, "order_id")
    return find(state["orders"], args["order_id"], "order")


@tool("Carrier tracking events for a parcel. --tracking number")
def get_carrier_events(state, args):
    need(args, "tracking")
    events = [e for e in state["carrier_events"] if e["tracking"] == args["tracking"]]
    return {"tracking": args["tracking"], "events": events, "feed_updated": state["carrier_feed_updated"]}


@tool("Refund a request. --request-id id --amount dollars [--override-reason text]")
def issue_refund(state, args):
    need(args, "amount")
    req = _request(state, args)
    _open(req)
    order = _order(state, req)
    amount = round(float(args["amount"]), 2)
    if amount <= 0 or amount > order["total"]:
        raise ToolError(f"amount must be between 0 and the order total {order['total']:.2f}")
    if not args.get("override_reason"):
        if req["type"] == "not_received" and not any(e["code"] == EXCEPTION for e in _scans(state, order)):
            raise ToolError("no carrier delivery exception on file for this parcel")
        if req["type"] == "return" and not order.get("return_received"):
            raise ToolError("return has not been received by the warehouse")
    req.update(status="refunded", refund_amount=amount, override_reason=args.get("override_reason"))
    return req


@tool("Ship a replacement for an exchange request. --request-id id --sku sku [--override-reason text]")
def issue_exchange(state, args):
    need(args, "sku")
    req = _request(state, args)
    _open(req)
    order = _order(state, req)
    if args["sku"] not in state["catalogue"]:
        raise ToolError(f"unknown sku {args['sku']}")
    if not args.get("override_reason"):
        if req["type"] == "damaged":
            damage_scan = any(e["code"] == EXCEPTION and "damage" in e["detail"].lower() for e in _scans(state, order))
            if not (damage_scan or order.get("inspection") == "damage confirmed"):
                raise ToolError("no carrier damage scan or warehouse damage inspection on file")
        elif not order.get("return_received"):
            raise ToolError("return has not been received by the warehouse")
    req.update(status="exchanged", replacement_sku=args["sku"], override_reason=args.get("override_reason"))
    return req


@tool("Decline a request and send the customer the reason. --request-id id --reason text")
def deny_request(state, args):
    need(args, "reason")
    req = _request(state, args)
    _open(req)
    req.update(status="denied", reason=args["reason"])
    return req


@tool("Hand a request to the supervisor queue. --request-id id --summary text")
def escalate_case(state, args):
    need(args, "summary")
    req = _request(state, args)
    _open(req)
    req.update(status="escalated", summary=args["summary"])
    return req
