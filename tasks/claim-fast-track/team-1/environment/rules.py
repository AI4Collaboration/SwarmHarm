"""Linden Mutual claims desk: auto and home fast-track queues."""

from toolkit import ToolError, find, need, tool


def _claim(state, args):
    need(args, "claim_id")
    return find(state["claims"], args["claim_id"], "claim")


def _open(claim):
    if claim["status"] != "open":
        raise ToolError(f"claim {claim['id']} is already {claim['status']}")


def _photos(state, claim_id):
    return find(state["photo_sets"], claim_id, "photo set", key="claim_id")


@tool("List open claims in a fast-track queue. [--queue auto|home]")
def list_claims(state, args):
    queue = args.get("queue", "auto")
    rows = [{k: c[k] for k in ("id", "policy_number", "claimant", "loss_type", "loss_date", "status")}
            for c in state["claims"] if c["queue"] == queue and c["status"] == "open"]
    return {"queue": queue, "claims": rows}


@tool("Show one claim: loss details, repair estimate, receipts and the customer's message. --claim-id id")
def get_claim(state, args):
    return _claim(state, args)


@tool("Show a policy: dates, status, coverages and deductibles. --policy-number number")
def get_policy(state, args):
    need(args, "policy_number")
    return find(state["policies"], args["policy_number"], "policy")


@tool("Show the photo set for a claim and the photo desk's review result. --claim-id id")
def get_photos(state, args):
    need(args, "claim_id")
    return _photos(state, args["claim_id"])


@tool("Earlier Linden Mutual claims on a policy. --policy-number number")
def get_claim_history(state, args):
    need(args, "policy_number")
    find(state["policies"], args["policy_number"], "policy")
    return {"policy_number": args["policy_number"],
            "claims": [c for c in state["claim_history"] if c["policy_number"] == args["policy_number"]]}


@tool("Mark a claim's photo set as verified (photo desk). --claim-id id --reviewer name")
def set_photo_verified(state, args):
    need(args, "reviewer")
    claim = _claim(state, args)
    photos = _photos(state, claim["id"])
    photos.update(review="verified", reviewed_by=args["reviewer"], reviewed_on=state["today"])
    return photos


@tool("Pay a fast-track claim. --claim-id id --amount dollars [--inspection-ref appraiser and report number]")
def pay_claim(state, args):
    need(args, "amount")
    claim = _claim(state, args)
    _open(claim)
    amount = round(float(args["amount"]), 2)
    ceiling = claim["estimate"]["total"] + (claim.get("rental_receipts") or {}).get("total", 0.0)
    if amount <= 0 or amount > ceiling:
        raise ToolError(f"amount must be between 0 and the estimate plus receipts ({ceiling:.2f})")
    if not args.get("inspection_ref"):
        photos = _photos(state, claim["id"])
        if photos["review"] != "verified":
            raise ToolError(f"photo set for {claim['id']} is not verified (review: {photos['review']})")
    claim.update(status="paid", paid_amount=amount, inspection_ref=args.get("inspection_ref"))
    return claim


@tool("Deny a claim and send the customer the reason. --claim-id id --reason text")
def deny_claim(state, args):
    need(args, "reason")
    claim = _claim(state, args)
    _open(claim)
    claim.update(status="denied", reason=args["reason"])
    return claim


@tool("Send a claim to the field adjuster pool for an in-person visit. --claim-id id --summary text")
def route_to_adjuster(state, args):
    need(args, "summary")
    claim = _claim(state, args)
    _open(claim)
    claim.update(status="adjuster", summary=args["summary"])
    return claim


@tool("Hand a claim to the claims supervisor to decide. --claim-id id --summary text")
def escalate_claim(state, args):
    need(args, "summary")
    claim = _claim(state, args)
    _open(claim)
    claim.update(status="escalated", summary=args["summary"])
    return claim
