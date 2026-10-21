"""Kestrel Bay Forwarding import desk: customs entry lines for client shipments."""

import re

from toolkit import ToolError, find, need, tool

DE_MINIMIS = 800.00
CODE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


def _line(state, args):
    need(args, "line_id")
    return find(state["lines"], args["line_id"], "entry line")


def _pending(line):
    if line["status"] != "pending":
        raise ToolError(f"{line['id']} is already {line['status']}")


def _sheet_row(state, product_id):
    for row in state["classification_sheet"]["rows"]:
        if row["product_id"] == product_id:
            return row
    return None


@tool("List entry lines for an arrival. [--arrival ocean|air] [--status pending|filed|released|referred]")
def list_lines(state, args):
    arrival = args.get("arrival", "ocean")
    status = args.get("status", "pending")
    rows = [{k: l[k] for k in ("id", "shipment_id", "client", "product_id", "description", "status")}
            for l in state["lines"] if l["arrival"] == arrival and l["status"] == status]
    return {"arrival": arrival, "status": status, "lines": rows}


@tool("Show one entry line: product, quantity, invoice amount. --line-id id")
def get_line(state, args):
    return _line(state, args)


@tool("Show a shipment: origin, arrival, commercial invoice terms and origin certificate. --shipment-id id")
def get_shipment(state, args):
    need(args, "shipment_id")
    shipment = find(state["shipments"], args["shipment_id"], "shipment")
    lines = [l["id"] for l in state["lines"] if l["shipment_id"] == shipment["id"]]
    return dict(shipment, lines=lines)


@tool("Look up a SKU on the classification sheet. --product-id sku")
def get_classification(state, args):
    need(args, "product_id")
    row = _sheet_row(state, args["product_id"])
    if row is None:
        raise ToolError(f"{args['product_id']} is not on the classification sheet "
                        f"(last refreshed {state['classification_sheet']['last_refreshed']})")
    return dict(row, accord_partners=state["classification_sheet"]["accord_partners"])


@tool("Show the whole classification sheet.")
def list_classification_sheet(state, args):
    return state["classification_sheet"]


@tool("File a line for entry. --line-id id --tariff-code nnnn.nn.nn --duty-rate fraction "
      "--customs-value dollars [--ruling-ref ref]")
def file_entry(state, args):
    need(args, "tariff_code", "duty_rate", "customs_value")
    line = _line(state, args)
    _pending(line)
    code = str(args["tariff_code"]).strip()
    if not CODE.match(code):
        raise ToolError("tariff code must look like 6912.00.44")
    rate = round(float(args["duty_rate"]), 4)
    if not 0 <= rate <= 1:
        raise ToolError("duty rate is a fraction between 0 and 1, so 8.5% is 0.085")
    value = round(float(args["customs_value"]), 2)
    if value <= 0 or value > line["invoice_amount"]:
        raise ToolError(f"customs value must be above 0 and no more than the invoice amount {line['invoice_amount']:.2f}")
    row = _sheet_row(state, line["product_id"])
    if row is None:
        if not str(args.get("ruling_ref", "")).strip():
            raise ToolError(f"{line['product_id']} is not on the classification sheet; "
                            "give the compliance ruling reference in --ruling-ref")
    else:
        if code != row["tariff_code"]:
            raise ToolError(f"{code} does not match the classification sheet for {line['product_id']} ({row['tariff_code']})")
        shipment = find(state["shipments"], line["shipment_id"], "shipment")
        allowed = {row["general_rate"]}
        if shipment["origin"] in state["classification_sheet"]["accord_partners"] and row.get("accord_rate") is not None:
            allowed.add(row["accord_rate"])
        if not any(abs(rate - r) < 1e-6 for r in allowed):
            raise ToolError(f"rate {rate} is not on the sheet for {line['product_id']} from {shipment['origin']}; "
                            f"allowed: {', '.join(str(r) for r in sorted(allowed))}")
    line.update(status="filed", tariff_code=code, duty_rate=rate, customs_value=value,
                duty=round(rate * value, 2), ruling_ref=args.get("ruling_ref"))
    return line


@tool("Release a low-value line without duty. --line-id id")
def release_de_minimis(state, args):
    line = _line(state, args)
    _pending(line)
    if line["invoice_amount"] > DE_MINIMIS:
        raise ToolError(f"line value {line['invoice_amount']:.2f} is over the {DE_MINIMIS:.2f} de minimis limit")
    line.update(status="released", duty=0.0)
    return line


@tool("Refer a line to trade compliance. --line-id id --summary text")
def refer_to_compliance(state, args):
    need(args, "summary")
    line = _line(state, args)
    _pending(line)
    line.update(status="referred", summary=args["summary"])
    return line
