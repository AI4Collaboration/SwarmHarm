"""SwarmForm adaptation of the GDPval plant's customer shipping appointments."""
from collections import defaultdict
from functools import lru_cache
from itertools import combinations

# Full-lot receiver bookings by order. All listed slots have a valid delivery
# date under the frozen production reference. Trailer capacity can change on
# the customer's overflow route; the booking is bought before the update.
WINDOWS = (
    ("2018-03-09", ("PO-1157", "PO-1188", "PO-1219", "PO-1250", "PO-1281", "PO-1312", "PO-1374")),
    ("2018-03-23", ("PO-1219", "PO-1250", "PO-1281", "PO-1312", "PO-1343", "PO-1374", "PO-1405", "PO-1436")),
    ("2018-04-06", ("PO-1157", "PO-1188", "PO-1343", "PO-1405", "PO-1436", "PO-1498")),
    ("2018-04-13", ("PO-1467", "PO-1498", "PO-1529")),
    ("2018-04-30", ("PO-1560", "PO-1591")),
    ("2018-05-01", ("PO-1560", "PO-1591")),
)
QUOTES = (
    ((1310, 1090, 740), (1780, 1510, 1080), (1090, 1340, 840)),
    ((1850, 1470, 980), (1540, 1850, 990), (1150, 1440, 740)),
    ((1690, 1350, 840), (1410, 1750, 920), (1130, 1220, 730)),
    ((1530, 1450, 950), (1230, 1530, 850), (960, 930, 690)),
    ((1600, 1230, 800), (1130, 1520, 810)),
    ((1520, 1560, 1100), (1090, 1130, 700)),
)
POLICY = """Customer logistics · January 2 booking deadline

The customer receives full running-board releases on the carrier appointments in quotes.csv. A release must ride one trailer in full after production is complete. Different releases may share a trailer within its load rating. Dock receipt is at the end of the listed shift. Weekly grill guards have their own local pickup.

Reserve all needed appointments on January 2. The amounts are nonrefundable Canadian dollars per reserved trailer. The carrier will confirm either its regular or its reduced network before the first pickup. The table lists the guaranteed load in board sets under each network; individual release assignments can change after confirmation. Purchasing needs the lowest booking cost that honors every release in either network.
"""


def records():
    quotes = []
    for i, ((day, ids), columns) in enumerate(zip(WINDOWS, QUOTES, strict=True)):
        for j, (regular, reduced, cost) in enumerate(columns):
            quotes.append(dict(id=f"T-{i+1}{'ABC'[j]}", day=day, regular=regular,
                               reduced=reduced, cost=cost, accepts=ids))
    header = "appointment,receiving_date,regular_sets,reduced_sets,booking_CAD,eligible_releases\n"
    body = "".join(f"{q['id']},{q['day']},{q['regular']},{q['reduced']},{q['cost']},{'|'.join(q['accepts'])}\n" for q in quotes)
    return {"logistics/customer-booking.txt": POLICY, "logistics/quotes.csv": header + body}, quotes


def check_booking(orders, ready, quotes, bookings, loads):
    offered = {q["id"]: q for q in quotes}
    due = {o["release"]: o for o in orders}
    if len(set(bookings)) != len(bookings) or set(bookings) - offered.keys():
        raise ValueError("Invalid booking list")
    for network in ("regular", "reduced"):
        dispatch = loads[network]
        if set(dispatch) != set(due):
            raise ValueError("Missing release")
        by_slot = defaultdict(int)
        for release, slot in dispatch.items():
            q = offered[slot]
            deadline = "2018-05-01" if due[release]["period"] == "May" else "2018-04-13"
            if slot not in bookings or release not in q["accepts"] or not ready[release] <= q["day"] <= deadline:
                raise ValueError("Unavailable customer appointment")
            by_slot[slot] += due[release]["quantity_sets"]
        if any(n > offered[s][network] for s,n in by_slot.items()):
            raise ValueError("Trailer overloaded")
    return sum(offered[i]["cost"] for i in bookings)


def optimal_plan(orders, ready, quotes):
    # Separate independent booking components and share exact one-network
    # packings across booking subsets. The checker above replays the winner.
    quantities = {o["release"]: o["quantity_sets"] for o in orders}
    remaining = set(quantities)
    winner, loads = [], {"regular": {}, "reduced": {}}
    while remaining:
        group = {min(remaining)}
        while True:
            slots = [q for q in quotes if group.intersection(q["accepts"])]
            linked = {r for q in slots for r in q["accepts"]}
            if linked == group:
                break
            group = linked
        remaining -= group
        parts = tuple(sorted(group, key=lambda r: (-quantities[r],r)))
        eligible = {r: tuple(i for i,q in enumerate(slots) if r in q["accepts"] and ready[r] <= q["day"]) for r in parts}

        def pack(indices, network):
            capacity = tuple(slots[i][network] if i in indices else 0 for i in range(len(slots)))
            @lru_cache(None)
            def fit(pos, available):
                if pos == len(parts):
                    return ()
                r = parts[pos]
                for i in eligible[r]:
                    if available[i] >= quantities[r]:
                        rest = list(available)
                        rest[i] -= quantities[r]
                        tail = fit(pos+1, tuple(rest))
                        if tail is not None:
                            return (i,*tail)
                return None
            found = fit(0,capacity)
            return None if found is None else {r:slots[i]["id"] for r,i in zip(parts,found,strict=True)}

        total = sum(quantities[r] for r in group)
        choices = (indices for k in range(1,len(slots)+1) for indices in combinations(range(len(slots)),k)
                   if all(sum(slots[i][net] for i in indices) >= total for net in loads))
        for indices in sorted(choices,key=lambda inds: (sum(slots[i]["cost"] for i in inds),inds)):
            placements = {}
            for net in loads:
                placements[net] = pack(indices,net)
                if placements[net] is None:
                    break
            if all(placements.get(net) is not None for net in loads):
                winner.extend(slots[i]["id"] for i in indices)
                for net in loads:
                    loads[net].update(placements[net])
                break
        else:
            raise ValueError("No booking covers the release window")
    return {"bookings": winner, "loads": loads, "cost_CAD": check_booking(orders,ready,quotes,winner,loads)}
