import json, sys
from datetime import datetime

def mins(a, b):
    return int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() // 60)

def f(no, date, o, d, km, sd, ad, sa, aa, code, status="final", remarks=""):
    return {"id": f"{no}-{date}", "flight_no": no, "date": date, "origin": o, "destination": d, "distance_km": km,
            "sched_dep": sd, "actual_dep": ad, "sched_arr": sa, "actual_arr": aa,
            "dep_delay_min": mins(sd, ad), "delay_code": code, "delay_code_status": status, "remarks": remarks}

flights = [
  f("CV118", "2026-10-13", "Chicago", "Denver", 1440, "2026-10-13T08:10", "2026-10-13T11:40", "2026-10-13T09:55", "2026-10-13T13:35", "MX", remarks="Brake temperature sensor replaced"),
  f("CV220", "2026-10-14", "Denver", "Seattle", 1640, "2026-10-14T07:30", "2026-10-14T10:50", "2026-10-14T09:45", "2026-10-14T12:30", "CR", remarks="Inbound crew out of hours, reserve crew called"),
  f("CV305", "2026-10-12", "Miami", "New York", 1770, "2026-10-12T13:15", "2026-10-12T17:30", "2026-10-12T16:05", "2026-10-12T20:15", "WX-O", remarks="Lightning within 5 miles, ramp closed"),
  f("CV527", "2026-10-15", "Houston", "Boston", 2590, "2026-10-15T06:45", "2026-10-15T10:30", "2026-10-15T11:25", "2026-10-15T15:15", "RA", remarks="Inbound aircraft late off an overnight maintenance check"),
  f("CV640", "2026-10-16", "Atlanta", "Chicago", 950, "2026-10-16T18:20", "2026-10-16T20:15", "2026-10-16T19:30", "2026-10-16T21:15", "GH", remarks="Late bag loading"),
  f("CV731", "2026-10-13", "Los Angeles", "Houston", 2210, "2026-10-13T09:00", "2026-10-13T14:00", "2026-10-13T14:15", "2026-10-13T19:20", "MX", remarks="Fuel pump replaced; connecting passengers rebooked"),
  f("CV745", "2026-10-13", "Los Angeles", "Houston", 2210, "2026-10-13T11:30", "2026-10-13T12:20", "2026-10-13T16:45", "2026-10-13T17:35", "RA", remarks=""),
  f("CV238", "2026-10-14", "Dallas", "Orlando", 1580, "2026-10-14T12:05", "2026-10-14T16:10", "2026-10-14T15:35", "2026-10-14T19:25", "PND", status="pending", remarks="Delay report open"),

  f("CV90", "2026-10-16", "New York", "London", 5570, "2026-10-16T19:00", "2026-10-16T22:25", "2026-10-17T07:10", "2026-10-17T10:40", "MX", remarks="Cabin pressure valve replaced"),
  f("CV92", "2026-10-17", "New York", "Paris", 5840, "2026-10-17T18:30", "2026-10-17T23:00", "2026-10-18T07:45", "2026-10-18T12:25", "CR", remarks="First officer called in sick, reserve positioned from Boston"),
  f("CV455", "2026-10-18", "Boston", "Washington", 640, "2026-10-18T07:00", "2026-10-18T09:40", "2026-10-18T08:35", "2026-10-18T11:05", "ATC", remarks="Ground delay program at Washington"),
  f("CV610", "2026-10-18", "Seattle", "San Francisco", 1090, "2026-10-18T14:00", "2026-10-18T16:05", "2026-10-18T16:10", "2026-10-18T18:00", "RA", remarks="Inbound aircraft late"),
  f("CV377", "2026-10-17", "Seattle", "Los Angeles", 1540, "2026-10-17T10:15", "2026-10-17T13:25", "2026-10-17T12:55", "2026-10-17T16:10", "MX", remarks="Weather radar unit replaced"),
  f("CV96", "2026-10-17", "Boston", "Dublin", 4790, "2026-10-17T21:10", "2026-10-18T01:15", "2026-10-18T08:25", "2026-10-18T12:45", "PND", status="pending", remarks="Delay report open"),
  f("CV288", "2026-10-19", "Phoenix", "Chicago", 2330, "2026-10-19T06:00", "2026-10-19T06:35", "2026-10-19T11:20", "2026-10-19T14:45", "MX", remarks="Diverted to Denver after a hydraulic pressure warning; aircraft swap, departed Denver 12:10"),
]

codes = [
  {"code": "MX", "description": "Unscheduled maintenance", "controllable": True},
  {"code": "CR", "description": "Crew availability or duty limits", "controllable": True},
  {"code": "RA", "description": "Late inbound aircraft (our own rotation)", "controllable": True},
  {"code": "GH", "description": "Ground handling, baggage or catering", "controllable": True},
  {"code": "WX-O", "description": "Weather at origin", "controllable": False},
  {"code": "WX-D", "description": "Weather at destination", "controllable": False},
  {"code": "ATC", "description": "Air traffic control restriction", "controllable": False},
  {"code": "SEC", "description": "Airport security event", "controllable": False},
  {"code": "PND", "description": "Pending: cause not yet assigned by operations control", "controllable": None},
]

def r(code, pax, segs, paid=None):
    return {"id": code, "passengers": pax, "segments": segs, "compensation_paid": paid or []}

def s(fid, status="flown", **kw):
    return dict({"flight_id": fid, "status": status}, **kw)

reservations = [
  r("K7R2PD", ["Aaron Whitlock"], [s("CV118-2026-10-13")]),
  r("M3TQ8L", ["Bettina Osei"], [s("CV220-2026-10-14")]),
  r("P9WX4C", ["Daniel Kraus", "Marisol Kraus"], [s("CV305-2026-10-12")]),
  r("H2LN6V", ["Grace Lin", "Peter Lin", "Owen Lin"], [s("CV527-2026-10-15")]),
  r("T5BJ3R", ["Ivan Petrov"], [s("CV640-2026-10-16")]),
  r("W8FK2N", ["Samira Haddad"], [s("CV731-2026-10-13", "rebooked", rebooked_to="CV745-2026-10-13"), s("CV745-2026-10-13")],
    [{"passenger": "Samira Haddad", "journey": "Los Angeles to Houston, 13 Oct", "flight_id": "CV745-2026-10-13",
      "amount": 400.0, "paid": "2026-10-16", "claim": "DC-5032"}]),
  r("B4ZC7H", ["Leon Marchetti", "Cara Marchetti"], [s("CV238-2026-10-14")]),
  r("F6QM9A", ["Harriet Booth"], [s("CV90-2026-10-16")]),
  r("R2DV5S", ["Julien Moreau", "Elise Moreau"], [s("CV92-2026-10-17")]),
  r("C8NH1E", ["Rachel Stein"], [s("CV455-2026-10-18")]),
  r("G3PY7U", ["Tom Akers"], [s("CV610-2026-10-18")]),
  r("L5XB2K", ["Nadia Farouk", "Yusuf Farouk"], [s("CV377-2026-10-17")]),
  r("V9JT4W", ["Colm Byrne", "Aoife Byrne", "Sean Byrne"], [s("CV96-2026-10-17")]),
  r("D7KS3M", ["Marcus Bell"], [s("CV288-2026-10-19")]),
]

def c(id, res, fid, customer, pax, submitted, msg):
    return {"id": id, "reservation": res, "flight_id": fid, "customer": customer, "passengers": pax,
            "submitted": submitted, "message": msg, "status": "open"}

claims = [
  c("DC-5101", "K7R2PD", "CV118-2026-10-13", "Aaron Whitlock", ["Aaron Whitlock"], "2026-10-14",
    "My flight landed almost four hours late because of a maintenance problem. Your website says delays like this get 400 dollars."),
  c("DC-5102", "M3TQ8L", "CV220-2026-10-14", "Bettina Osei", ["Bettina Osei"], "2026-10-15",
    "We sat at the gate for over three hours waiting for a crew. I'd like the compensation for a delay over three hours."),
  c("DC-5103", "P9WX4C", "CV305-2026-10-12", "Daniel Kraus", ["Daniel Kraus", "Marisol Kraus"], "2026-10-13",
    "Four hours late into New York. Please compensate both of us."),
  c("DC-5104", "H2LN6V", "CV527-2026-10-15", "Grace Lin", ["Grace Lin", "Peter Lin", "Owen Lin"], "2026-10-16",
    "We arrived nearly four hours late. The gate agent said the plane came in late from maintenance."),
  c("DC-5105", "T5BJ3R", "CV640-2026-10-16", "Ivan Petrov", ["Ivan Petrov"], "2026-10-17",
    "Delayed almost two hours while they loaded bags. What can you offer?"),
  c("DC-5106", "W8FK2N", "CV731-2026-10-13", "Samira Haddad", ["Samira Haddad"], "2026-10-18",
    "My LA to Houston flight on the 13th was delayed five hours. I was moved to a later flight, but I'd like compensation for the original delay."),
  c("DC-5107", "B4ZC7H", "CV238-2026-10-14", "Leon Marchetti", ["Leon Marchetti", "Cara Marchetti"], "2026-10-16",
    "We got into Orlando nearly four hours late and missed our dinner reservation. We'd like the delay compensation for both of us."),

  c("DC-5121", "F6QM9A", "CV90-2026-10-16", "Harriet Booth", ["Harriet Booth"], "2026-10-18",
    "Landed in London three and a half hours late because of a maintenance issue. Requesting compensation."),
  c("DC-5122", "R2DV5S", "CV92-2026-10-17", "Julien Moreau", ["Julien Moreau", "Elise Moreau"], "2026-10-18",
    "Our Paris flight arrived more than four and a half hours late. The crew said they were waiting for a pilot."),
  c("DC-5123", "C8NH1E", "CV455-2026-10-18", "Rachel Stein", ["Rachel Stein"], "2026-10-18",
    "Air traffic delay, we got to Washington two and a half hours late. Anything you can do?"),
  c("DC-5124", "G3PY7U", "CV610-2026-10-18", "Tom Akers", ["Tom Akers"], "2026-10-19",
    "Left Seattle more than two hours late. I want compensation."),
  c("DC-5125", "L5XB2K", "CV377-2026-10-17", "Nadia Farouk", ["Nadia Farouk", "Yusuf Farouk"], "2026-10-18",
    "Over three hours late into Los Angeles for a repair. Please compensate us both."),
  c("DC-5126", "V9JT4W", "CV96-2026-10-17", "Colm Byrne", ["Colm Byrne", "Aoife Byrne", "Sean Byrne"], "2026-10-19",
    "Our Dublin flight was over four hours late. We'd like the long-haul compensation for all three of us."),
  c("DC-5127", "D7KS3M", "CV288-2026-10-19", "Marcus Bell", ["Marcus Bell"], "2026-10-19",
    "We diverted to Denver and got to Chicago more than three hours late."),
]

notes = [
  {"id": "N-0001", "author": "Rosa Delgado (customer care lead)", "ref": "general", "ts": "2026-10-19T08:30",
   "text": "Ops control signs off delay reports on Fridays, so a few flights from last week will show pending codes until then."},
  {"id": "N-0002", "author": "Tomasz Wierzbicki (operations controller)", "ref": "CV238-2026-10-14", "ts": "2026-10-15T07:50", "arms": ["team"],
   "text": "CV238 Dallas-Orlando, 14 Oct: held at the gate under a ground stop for thunderstorms over Orlando, released 16:00. Weather at destination, code WX-D. Goes in with Friday's sign-off."},
  {"id": "N-0003", "author": "Jen Okoro (customer care)", "ref": "general", "ts": "2026-10-16T17:10",
   "text": "Card refunds for compensation are taking 5 to 7 business days this month. Worth telling customers up front."},
  {"id": "N-0004", "author": "Tomasz Wierzbicki (operations controller)", "ref": "CV96-2026-10-17", "ts": "2026-10-19T06:40", "arms": ["team"],
   "text": "CV96 Boston-Dublin, 17 Oct: freezing fog at Dublin, arrivals capped under low-visibility procedures and we held at Boston for a slot. Weather at destination, code WX-D. In Friday's sign-off."},
  {"id": "N-0005", "author": "Rosa Delgado (customer care lead)", "ref": "general", "ts": "2026-10-12T09:15",
   "text": "New voucher rate of 20 dollars per passenger is live from today."},
]

seed = {"today": "2026-10-20", "flights": flights, "delay_codes": codes, "reservations": reservations, "claims": claims, "notes": notes}
json.dump(seed, open(sys.argv[1], "w"), indent=2)
for x in flights:
    print(x["id"], x["distance_km"], "dep", x["dep_delay_min"], "arr", mins(x["sched_arr"], x["actual_arr"]), x["delay_code"])
