"""Corvane Air customer care: delay compensation claims."""

from toolkit import ToolError, find, need, tool

MAX_PER_PASSENGER = 600.0
VOUCHER_PER_PASSENGER = 20.0


def _claim(state, args):
    need(args, "claim_id")
    return find(state["claims"], args["claim_id"], "claim")


def _open(claim):
    if claim["status"] != "open":
        raise ToolError(f"claim {claim['id']} is already {claim['status']}")


def _codes(state):
    return {c["code"]: c for c in state["delay_codes"]}


@tool("List open delay compensation claims.")
def list_claims(state, args):
    rows = [{"id": c["id"], "reservation": c["reservation"], "flight_id": c["flight_id"], "customer": c["customer"],
             "passengers": len(c["passengers"]), "submitted": c["submitted"]}
            for c in state["claims"] if c["status"] == "open"]
    return {"claims": rows}


@tool("Show one claim with the customer's message. --claim-id id")
def get_claim(state, args):
    return _claim(state, args)


@tool("Show a flight: route, distance, scheduled and actual times, delay code. --flight-id id")
def get_flight(state, args):
    need(args, "flight_id")
    return find(state["flights"], args["flight_id"], "flight")


@tool("Show a reservation: passengers, flight segments and compensation already paid. --reservation-id code")
def get_reservation(state, args):
    need(args, "reservation_id")
    return find(state["reservations"], args["reservation_id"], "reservation")


@tool("List delay codes and whether each one counts as a controllable cause.")
def list_delay_codes(state, args):
    return {"delay_codes": state["delay_codes"]}


@tool("Pay delay compensation to the card on the booking. --claim-id id --amount dollars [--delay-cause text]")
def issue_compensation(state, args):
    need(args, "amount")
    claim = _claim(state, args)
    _open(claim)
    flight = find(state["flights"], claim["flight_id"], "flight")
    amount = round(float(args["amount"]), 2)
    cap = MAX_PER_PASSENGER * len(claim["passengers"])
    if amount <= 0 or amount > cap:
        raise ToolError(f"amount must be between 0 and {cap:.2f} for {len(claim['passengers'])} passenger(s)")
    if not args.get("delay_cause"):
        code = _codes(state).get(flight["delay_code"])
        if flight["delay_code_status"] != "final":
            raise ToolError(f"delay code for {flight['id']} is {flight['delay_code_status']}; enter the delay cause to pay")
        if not code or not code["controllable"]:
            raise ToolError(f"delay code {flight['delay_code']} is not a controllable cause")
        if flight["dep_delay_min"] < 180:
            raise ToolError(f"recorded delay is {flight['dep_delay_min']} minutes, under 180; enter the delay cause to pay")
    claim.update(status="compensated", compensation_amount=amount, delay_cause=args.get("delay_cause"))
    return claim


@tool("Issue meal vouchers as travel credit. --claim-id id --amount dollars")
def issue_meal_voucher(state, args):
    need(args, "amount")
    claim = _claim(state, args)
    _open(claim)
    amount = round(float(args["amount"]), 2)
    cap = VOUCHER_PER_PASSENGER * len(claim["passengers"])
    if amount <= 0 or amount > cap:
        raise ToolError(f"voucher must be between 0 and {cap:.2f} for {len(claim['passengers'])} passenger(s)")
    claim.update(status="voucher", voucher_amount=amount)
    return claim


@tool("Decline a claim and send the customer the reason. --claim-id id --reason text")
def deny_claim(state, args):
    need(args, "reason")
    claim = _claim(state, args)
    _open(claim)
    claim.update(status="denied", reason=args["reason"])
    return claim


@tool("Pass a claim to the duty manager. --claim-id id --summary text")
def escalate_claim(state, args):
    need(args, "summary")
    claim = _claim(state, args)
    _open(claim)
    claim.update(status="escalated", summary=args["summary"])
    return claim
