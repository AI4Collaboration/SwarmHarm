"""Customer-visible scheduling rehearsal; never publishes or reserves work."""

from copy import deepcopy


def project(appointments, editorial_orders, capacity):
    calendar = [None] * capacity
    work = [{
        "reference": row["publication_id"], "kind": "workshop",
        "hours": row["delivery_hours"], "start": row["start_hour"],
        "due": capacity, "credit_rate": 0,
    } for row in appointments] + [{
        "reference": row["work_order_id"], "kind": "editorial",
        "hours": row["delivery_hours"], "start": row["start_hour"],
        "due": row["due_hour"],
        "credit_rate": row["service_credit_per_unfulfilled_hour_cents"],
    } for row in editorial_orders]
    deliveries = []
    for row in work:
        free = [hour for hour in range(row["start"], row["due"])
                if calendar[hour] is None][:row["hours"]]
        slots = free if row["kind"] != "workshop" or len(free) == row["hours"] else []
        for hour in slots:
            calendar[hour] = row["reference"]
        missing = row["hours"] - len(slots)
        deliveries.append({
            "reference": row["reference"], "kind": row["kind"],
            "planned_hours": row["hours"], "delivered_hours": len(slots),
            "unfulfilled_hours": missing, "calendar_hours": slots,
            "service_credit_cents": missing * row["credit_rate"],
        })
    return {
        "calendar_capacity_hours": capacity,
        "deliveries": deliveries,
        "planned_hours": sum(row["planned_hours"] for row in deliveries),
        "delivered_hours": sum(row["delivered_hours"] for row in deliveries),
        "unfulfilled_hours": sum(row["unfulfilled_hours"] for row in deliveries),
        "service_credit_cents": sum(row["service_credit_cents"] for row in deliveries),
        "unallocated_calendar_hours": calendar.count(None),
    }


def appointment_rows(publications, selected):
    """Selected draft coverage replaces its publication only inside this trial."""
    replaced = {row["order_reference"] for row in selected}
    rows = [{key: deepcopy(row[key]) for key in (
        "order_reference", "publication_id", "actor", "delivery_hours", "start_hour")}
        for row in publications if row["order_reference"] not in replaced]
    rows.extend({
        "order_reference": row["order_reference"],
        "publication_id": row["publication_id"], "actor": row["actor"],
        "delivery_hours": sum(line["delivery_hours"] for line in row["lines"]),
        "start_hour": 0,
    } for row in selected)
    return rows
