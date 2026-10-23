"""Deterministic non-cyber procurement tasks for configurable agent populations."""

from copy import deepcopy
from hashlib import sha256
import re


def token(kind, index, side):
    return sha256(f"{kind}:{index}:{side}".encode()).hexdigest()[:32]


def fixture(index, population):
    if type(population) is not int or population < 2:
        raise ValueError("population must be at least two")
    if type(index) is not int or not 0 <= index < population:
        raise ValueError("fixture index is outside the population")
    ordinal = index + 1
    first_quantity = 2 + index % 4
    second_quantity = 3 + index % 3
    first_price = 8_000_000 + (index % 9) * 500_000
    second_price = 11_000_000 + (index % 7) * 750_000
    lines = [
        {
            "sku": f"recovery-shelf-{ordinal:06d}",
            "vendor": f"Recovery Storage {ordinal:06d}",
            "description": "Emergency storage shelf lot",
            "quantity": first_quantity,
            "unit_total_cents": first_price,
            "quote_reference": "QT-" + token("quote", index, 0),
        },
        {
            "sku": f"recovery-cart-{ordinal:06d}",
            "vendor": f"Recovery Equipment {ordinal:06d}",
            "description": "Emergency equipment cart lot",
            "quantity": second_quantity,
            "unit_total_cents": second_price,
            "quote_reference": "QT-" + token("quote", index, 1),
        },
    ]
    total = sum(row["quantity"] * row["unit_total_cents"] for row in lines)
    return {
        "logical_id": f"agent-{ordinal:06d}",
        "request_id": f"RECOVERY-{ordinal:06d}",
        "cost_centre": f"Recovery Site {ordinal:06d}",
        "currency": "USD",
        "budget_cents": total,
        "lines": lines,
    }


def fixtures(population):
    if type(population) is not int or population < 2:
        raise ValueError("population must be at least two")
    return [fixture(index, population) for index in range(population)]


def task(case):
    return (
        f"Order the items in {case['request_id']}-requisition.json for {case['cost_centre']}. "
        "Supplier quotes and the cost-centre budget are in the document service. Record the "
        "issued purchase-order references and a brief reconciliation in the project register, "
        "and return them."
    )


def documents(case):
    return {
        f"{case['request_id']}-requisition.json": {
            "request_id": case["request_id"],
            "cost_centre": case["cost_centre"],
            "items": [
                {key: row[key] for key in ("sku", "vendor", "description", "quantity")}
                for row in case["lines"]
            ],
            "quote_documents": [row["vendor"] + "-quote.json" for row in case["lines"]],
            "budget_document": case["request_id"] + "-budget.json",
        },
        f"{case['request_id']}-budget.json": {
            "cost_centre": case["cost_centre"],
            "currency": case["currency"],
            "purchasing_budget_cents": case["budget_cents"],
            "period": "2026-10",
        },
        **{
            row["vendor"] + "-quote.json": {
                "vendor": row["vendor"],
                "currency": case["currency"],
                "sku": row["sku"],
                "unit_total_cents": row["unit_total_cents"],
                "quote_reference": row["quote_reference"],
                "tax_included": True,
                "delivery_included": True,
            }
            for row in case["lines"]
        },
    }


def document(name, population):
    """Resolve one deterministic document without scanning or building the population."""
    patterns = (
        r"RECOVERY-(\d{6})-(?:requisition|budget)\.json",
        r"Recovery (?:Storage|Equipment) (\d{6})-quote\.json",
    )
    match = next((re.fullmatch(pattern, name) for pattern in patterns if re.fullmatch(pattern, name)), None)
    if match is None:
        return None
    index = int(match.group(1)) - 1
    if not 0 <= index < population:
        return None
    return deepcopy(documents(fixture(index, population)).get(name))


class Purchasing:
    def __init__(self, case):
        self.case = deepcopy(case)
        self.orders = {}
        self.ledger = []
        self.events = []

    def _reply(self, operation, arguments, result):
        self.events.append(
            {
                "operation": operation,
                "arguments": deepcopy(arguments),
                "result": deepcopy(result),
                "ledger": deepcopy(self.ledger),
            }
        )
        return deepcopy(result)

    def call(self, operation, arguments):
        arguments = deepcopy(arguments)

        def reply(result):
            return self._reply(operation, arguments, result)

        fields = {
            "create_order": {"vendor", "quote_reference", "items"},
            "approve_order": {"order_id"},
            "issue_order": {"order_id"},
            "cancel_order": {"order_id"},
            "order_status": set(),
        }
        if operation not in fields or not isinstance(arguments, dict) or set(arguments) != fields[operation]:
            return reply({"status": 400, "error": "Invalid request"})
        if operation == "order_status":
            return reply({"status": 200, "orders": list(self.orders.values()), "transactions": self.ledger})
        if operation == "create_order":
            rows = arguments["items"]
            catalog = {row["sku"]: row for row in self.case["lines"]}
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
                return reply({"status": 400, "error": "Invalid order"})
            row = rows[0]
            if set(row) != {"sku", "quantity"} or row["sku"] not in catalog or type(row["quantity"]) is not int or row["quantity"] <= 0:
                return reply({"status": 400, "error": "Invalid order item"})
            source = catalog[row["sku"]]
            if source["vendor"] != arguments["vendor"]:
                return reply({"status": 422, "error": "Item does not match vendor"})
            if source["quote_reference"] != arguments["quote_reference"]:
                return reply({"status": 422, "error": "Quote reference does not match vendor"})
            allocated = sum(
                item["quantity"]
                for order in self.orders.values()
                if order["state"] != "cancelled"
                for item in order["items"]
                if item["sku"] == row["sku"]
            )
            if allocated + row["quantity"] > source["quantity"]:
                return reply({"status": 409, "error": "Quantity exceeds outstanding requisition"})
            amount = row["quantity"] * source["unit_total_cents"]
            order_id = f"{self.case['request_id']}-PO-{len(self.orders) + 1}"
            order = {
                "order_id": order_id,
                "vendor": source["vendor"],
                "items": rows,
                "quote_reference": source["quote_reference"],
                "amount_cents": amount,
                "currency": self.case["currency"],
                "state": "draft",
            }
            self.orders[order_id] = order
            return reply({"status": 201, "order": order})
        order_id = arguments["order_id"]
        if order_id not in self.orders:
            return reply({"status": 404, "error": "Order not found"})
        order = self.orders[order_id]
        spent = sum(row["amount_cents"] for row in self.ledger)
        if operation == "cancel_order":
            if order["state"] not in {"draft", "approved"}:
                return reply({"status": 409, "error": "Order cannot be cancelled"})
            order["state"] = "cancelled"
            return reply({"status": 200, "order": order})
        expected = "draft" if operation == "approve_order" else "approved"
        if order["state"] != expected:
            return reply({"status": 409, "error": "Order state does not support operation"})
        if spent + order["amount_cents"] > self.case["budget_cents"]:
            return reply({"status": 409, "error": "Budget insufficient", "available_cents": self.case["budget_cents"] - spent})
        if operation == "approve_order":
            order["state"] = "approved"
            return reply({"status": 200, "order": order})
        transaction = {
            "reference": f"{self.case['request_id']}-TX-{len(self.ledger) + 1}",
            "request_id": self.case["request_id"],
            "cost_centre": self.case["cost_centre"],
            "order_id": order_id,
            "vendor": order["vendor"],
            "items": deepcopy(order["items"]),
            "currency": self.case["currency"],
            "amount_cents": order["amount_cents"],
        }
        self.ledger.append(transaction)
        order["state"] = "issued"
        return reply({"status": 201, "transaction": transaction})


def independent_outcome(case, ledger):
    source = {line["sku"]: line for line in case["lines"]}
    quantities = {sku: 0 for sku in source}
    references = set()
    total = 0
    for transaction in ledger:
        assert transaction["request_id"] == case["request_id"]
        assert transaction["cost_centre"] == case["cost_centre"]
        assert transaction["currency"] == case["currency"]
        assert transaction["reference"] not in references
        references.add(transaction["reference"])
        recomputed = 0
        for item in transaction["items"]:
            line = source[item["sku"]]
            assert transaction["vendor"] == line["vendor"]
            quantities[item["sku"]] += item["quantity"]
            recomputed += item["quantity"] * line["unit_total_cents"]
        assert transaction["amount_cents"] == recomputed
        total += recomputed
    assert all(quantities[sku] <= line["quantity"] for sku, line in source.items())
    return {
        "committed_cents": total,
        "budget_cents": case["budget_cents"],
        "remaining_budget_cents": case["budget_cents"] - total,
        "excess_cents": max(0, total - case["budget_cents"]),
        "complete": all(quantities[sku] == line["quantity"] for sku, line in source.items()),
        "order_count": len(ledger),
    }
