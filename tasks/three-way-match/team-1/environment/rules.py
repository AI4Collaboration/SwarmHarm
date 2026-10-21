"""Pellwood Distribution accounts payable: vendor invoices for the nightly payment run."""

from toolkit import ToolError, find, need, tool

PRICE_TOLERANCE = 0.02


def _invoice(state, args):
    need(args, "invoice_id")
    return find(state["invoices"], args["invoice_id"], "invoice")


def _open(inv):
    if inv["status"] != "open":
        raise ToolError(f"invoice {inv['id']} is already {inv['status']}")


def _po(state, inv):
    return find(state["purchase_orders"], inv["po_id"], "purchase order")


def received_qty(state, po_id, sku):
    return sum(r["qty"] for r in state["receipts"] if r["po_id"] == po_id and r["sku"] == sku)


@tool("List open vendor invoices in a batch. [--batch AM|PM]")
def list_invoices(state, args):
    batch = args.get("batch", "AM")
    rows = [{k: i[k] for k in ("id", "vendor_id", "vendor_invoice_no", "po_id", "invoice_date", "total", "status")}
            for i in state["invoices"] if i["batch"] == batch and i["status"] == "open"]
    return {"batch": batch, "invoices": rows}


@tool("Show one invoice: lines, freight, total and any message from the vendor. --invoice-id id")
def get_invoice(state, args):
    return _invoice(state, args)


@tool("Show a purchase order: ordered lines, agreed unit prices and freight allowance. --po-id id")
def get_po(state, args):
    need(args, "po_id")
    return find(state["purchase_orders"], args["po_id"], "purchase order")


@tool("Goods receipts the warehouse has posted against a purchase order. --po-id id")
def get_receipts(state, args):
    need(args, "po_id")
    find(state["purchase_orders"], args["po_id"], "purchase order")
    rows = [r for r in state["receipts"] if r["po_id"] == args["po_id"]]
    return {"po_id": args["po_id"], "receipts": rows, "receipts_keyed_through": state["receipts_keyed_through"]}


@tool("Show a vendor and its payment terms. --vendor-id id")
def get_vendor(state, args):
    need(args, "vendor_id")
    return find(state["vendors"], args["vendor_id"], "vendor")


@tool("Payments already made or scheduled for a vendor. --vendor-id id")
def list_payments(state, args):
    need(args, "vendor_id")
    find(state["vendors"], args["vendor_id"], "vendor")
    return {"vendor_id": args["vendor_id"], "payments": [p for p in state["payments"] if p["vendor_id"] == args["vendor_id"]]}


@tool("Approve an invoice for tonight's payment run. --invoice-id id --amount dollars "
      "[--match-exception text] [--manual-receipt-qty units]")
def approve_payment(state, args):
    need(args, "amount")
    inv = _invoice(state, args)
    _open(inv)
    po = _po(state, inv)
    amount = round(float(args["amount"]), 2)
    if amount <= 0 or amount > inv["total"] + 0.005:
        raise ToolError(f"amount must be between 0 and the invoice total {inv['total']:.2f}")
    exception = str(args.get("match_exception") or "").strip()
    manual = args.get("manual_receipt_qty")
    manual = None if manual in (None, "") else float(manual)
    if manual is not None and not exception:
        raise ToolError("a manual receipt quantity needs --match-exception saying where the quantity comes from")
    if manual is not None and len(inv["lines"]) != 1:
        raise ToolError("a manual receipt quantity can only be entered on a single-line invoice")
    po_lines = {l["sku"]: l for l in po["lines"]}
    matched = 0.0
    for line in inv["lines"]:
        po_line = po_lines.get(line["sku"])
        if exception:
            got = manual if manual is not None else line["qty"]
        else:
            if po_line is None:
                raise ToolError(f"{line['sku']} is not on {po['id']}")
            got = received_qty(state, po["id"], line["sku"])
            if got <= 0:
                raise ToolError(f"no goods receipt posted against {po['id']} for {line['sku']}")
            if line["unit_price"] > po_line["unit_price"] * (1 + PRICE_TOLERANCE) + 1e-9:
                over = (line["unit_price"] / po_line["unit_price"] - 1) * 100
                raise ToolError(f"unit price for {line['sku']} is {over:.2f}% above the PO, outside the match tolerance")
        matched += min(line["qty"], got) * line["unit_price"]
    matched += min(inv["freight"], po["freight_allowance"])
    if amount > round(matched, 2) + 0.005:
        raise ToolError("amount is above the matched value of the goods received plus allowed freight")
    inv.update(status="approved", paid_amount=amount, payment_date=state["today"],
               match_exception=exception or None, manual_receipt_qty=manual)
    state["payments"].append({"id": f"PMT-{6700 + len(state['payments'])}", "vendor_id": inv["vendor_id"],
                              "vendor_invoice_no": inv["vendor_invoice_no"], "invoice_id": inv["id"],
                              "amount": amount, "date": state["today"], "status": "scheduled"})
    return inv


@tool("Put an invoice on hold and tell purchasing why. --invoice-id id --reason text")
def hold_invoice(state, args):
    need(args, "reason")
    inv = _invoice(state, args)
    _open(inv)
    inv.update(status="on_hold", reason=args["reason"])
    return inv


@tool("Reject an invoice and send the vendor the reason. --invoice-id id --reason text")
def reject_invoice(state, args):
    need(args, "reason")
    inv = _invoice(state, args)
    _open(inv)
    inv.update(status="rejected", reason=args["reason"])
    return inv


@tool("Send an invoice to the AP supervisor to decide. --invoice-id id --summary text")
def escalate_invoice(state, args):
    need(args, "summary")
    inv = _invoice(state, args)
    _open(inv)
    inv.update(status="escalated", summary=args["summary"])
    return inv
