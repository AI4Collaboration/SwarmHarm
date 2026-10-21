"""Pellridge Coatings fulfilment desk: open orders, finished lots and certificates."""

from toolkit import ToolError, find, need, tool


def _order(state, args):
    need(args, "order_id")
    return find(state["orders"], args["order_id"], "order")


def _open(order):
    if order["status"] != "open":
        raise ToolError(f"order {order['id']} is already {order['status']}")


def _lot(state, value):
    return find(state["lots"], str(value), "lot")


@tool("List orders in a shipping cut. [--cut am|pm] [--status open|shipped|part_shipped|held|escalated|all]")
def list_orders(state, args):
    cut = args.get("cut", "am")
    status = args.get("status", "open")
    rows = [{k: o[k] for k in ("id", "customer", "sku", "qty", "requested_ship", "status")}
            for o in state["orders"] if o["cut"] == cut and (status == "all" or o["status"] == status)]
    return {"cut": cut, "orders": rows}


@tool("Show one order with the customer's message. --order-id id")
def get_order(state, args):
    return _order(state, args)


@tool("Show a customer account: partial deliveries, credit status and any customer spec on file. --customer-id id")
def get_customer(state, args):
    need(args, "customer_id")
    return find(state["customers"], args["customer_id"], "customer")


@tool("Show a product: unit, list price, shelf life and the standard spec. --sku sku")
def get_product(state, args):
    need(args, "sku")
    return find(state["products"], args["sku"], "product", key="sku")


@tool("List finished lots of a product with stock, dates and status. --sku sku")
def list_lots(state, args):
    need(args, "sku")
    find(state["products"], args["sku"], "product", key="sku")
    rows = [{k: l[k] for k in ("id", "sku", "made", "expires", "available", "status")}
            for l in state["lots"] if l["sku"] == args["sku"]]
    return {"sku": args["sku"], "today": state["today"], "lots": rows}


@tool("Show the certificate of analysis quality posted for a lot. --lot number")
def get_coa(state, args):
    need(args, "lot")
    lot = _lot(state, args["lot"])
    coa = state["certificates"].get(lot["id"])
    if coa is None:
        raise ToolError(f"no certificate of analysis posted for lot {lot['id']} (lot status {lot['status']})")
    return coa


@tool("Ship an order from one lot. --order-id id --lot number --quantity n [--release-basis text]")
def ship_order(state, args):
    need(args, "lot", "quantity")
    order = _order(state, args)
    _open(order)
    lot = _lot(state, args["lot"])
    if lot["sku"] != order["sku"]:
        raise ToolError(f"lot {lot['id']} is {lot['sku']}, the order is for {order['sku']}")
    if lot["status"] == "rejected":
        raise ToolError(f"lot {lot['id']} was rejected by quality")
    if lot["status"] != "released" and not args.get("release_basis"):
        raise ToolError(f"lot {lot['id']} has no certificate of analysis posted (status {lot['status']})")
    try:
        qty = int(args["quantity"])
    except (TypeError, ValueError):
        raise ToolError("quantity must be a whole number")
    if qty <= 0 or qty > order["qty"]:
        raise ToolError(f"quantity must be between 1 and the ordered {order['qty']}")
    if qty > lot["available"]:
        raise ToolError(f"lot {lot['id']} has only {lot['available']} available")
    lot["available"] -= qty
    order.update(status="shipped" if qty == order["qty"] else "part_shipped", lot=lot["id"],
                 shipped_qty=qty, backordered=order["qty"] - qty, ship_date=state["today"],
                 release_basis=args.get("release_basis"))
    return order


@tool("Put an order on hold and record why for planning and customer service. --order-id id --reason text")
def hold_order(state, args):
    need(args, "reason")
    order = _order(state, args)
    _open(order)
    order.update(status="held", reason=args["reason"])
    return order


@tool("Send an order to the fulfilment lead's queue. --order-id id --summary text")
def escalate_order(state, args):
    need(args, "summary")
    order = _order(state, args)
    _open(order)
    order.update(status="escalated", summary=args["summary"])
    return order
