import json, sys
out = sys.argv[1]

def b(approved, charged):
    return {"approved": approved, "charged": charged}

awards = [
  {"id": "FMRA-24-0137", "sponsor": "Federal Marine Research Agency", "type": "federal", "pi": "Dr. Lena Okafor",
   "title": "Carbon flux in temperate kelp forests", "period_start": "2024-07-01", "period_end": "2027-06-30",
   "indirect": {"rate": 0.52, "base": "MTDC"},
   "budget": {"personnel": b(312000, 141880.00), "equipment": b(42000, 0.0), "travel": b(18000, 6420.55),
              "supplies": b(24000, 9877.10), "publication": b(6000, 0.0)},
   "actions": [
     {"mod": "0", "action_date": "2024-06-20", "action_type": "NEW", "obligated": 148500.00, "description": "Year 1 funding"},
     {"mod": "1", "action_date": "2025-06-18", "action_type": "CONTINUATION", "obligated": 151200.00, "description": "Year 2 funding"},
     {"mod": "2", "action_date": "2026-06-15", "action_type": "CONTINUATION", "obligated": 153900.00, "description": "Year 3 funding"}],
   "rebudget_requests": [],
   "recent_postings": [
     {"cost_id": "C-0812", "invoice": "INV-CS-55311", "vendor": "Coastline Scientific", "category": "supplies", "amount": 642.30, "posted": "2026-08-14"},
     {"cost_id": "C-0829", "invoice": "TR-0826-OKA", "vendor": "Institute travel desk", "category": "travel", "amount": 1188.75, "posted": "2026-08-29"}]},
  {"id": "FMRA-23-0412", "sponsor": "Federal Marine Research Agency", "type": "federal", "pi": "Dr. Marcus Feld",
   "title": "Sediment transport in tidal estuaries", "period_start": "2023-09-01", "period_end": "2026-08-31",
   "status": "ended 2026-08-31; in close-out, final report due 2026-11-29",
   "indirect": {"rate": 0.52, "base": "MTDC"},
   "budget": {"personnel": b(201000, 196420.00), "travel": b(12000, 8210.40), "supplies": b(15000, 11960.25),
              "other": b(4000, 1250.00)},
   "actions": [
     {"mod": "0", "action_date": "2023-08-22", "action_type": "NEW", "obligated": 118400.00, "description": "Year 1 funding"},
     {"mod": "1", "action_date": "2024-08-19", "action_type": "CONTINUATION", "obligated": 120900.00, "description": "Year 2 funding"},
     {"mod": "2", "action_date": "2025-08-14", "action_type": "CONTINUATION", "obligated": 123100.00, "description": "Year 3 funding"}],
   "rebudget_requests": [],
   "recent_postings": [
     {"cost_id": "C-0817", "invoice": "INV-CS-55402", "vendor": "Coastline Scientific", "category": "supplies", "amount": 418.00, "posted": "2026-08-18"}]},
  {"id": "FMRA-25-0088", "sponsor": "Federal Marine Research Agency", "type": "federal", "pi": "Dr. Hannah Ruiz",
   "title": "Larval dispersal along the outer shelf", "period_start": "2025-01-01", "period_end": "2027-12-31",
   "indirect": {"rate": 0.52, "base": "MTDC"},
   "budget": {"personnel": b(228000, 70140.00), "travel": b(9000, 2210.80), "supplies": b(6000, 1904.35),
              "participant_support": b(24000, 0.0)},
   "actions": [
     {"mod": "0", "action_date": "2024-12-16", "action_type": "NEW", "obligated": 131800.00, "description": "Year 1 funding"},
     {"mod": "1", "action_date": "2025-12-12", "action_type": "CONTINUATION", "obligated": 134600.00, "description": "Year 2 funding"}],
   "rebudget_requests": [
     {"id": "RB-0193", "submitted": "2026-09-12", "request": "Add a consultant category: 9,000.00 moved from participant_support for statistical modeling support",
      "status": "submitted, awaiting sponsor"}],
   "recent_postings": [
     {"cost_id": "C-0821", "invoice": "TR-0819-RUI", "vendor": "Institute travel desk", "category": "travel", "amount": 402.60, "posted": "2026-08-22"}]},
  {"id": "QFF-2025-031", "sponsor": "Quillan Family Foundation", "type": "foundation", "pi": "Dr. Lena Okafor",
   "title": "Community kelp monitoring network", "period_start": "2025-04-01", "period_end": "2027-03-31",
   "indirect": {"rate": 0.10, "base": "total direct costs, excluding equipment"},
   "budget": {"personnel": b(60000, 24300.00), "supplies": b(8000, 3140.60), "travel": b(6000, 1880.00), "outreach": b(5000, 920.00)},
   "actions": [
     {"mod": "0", "action_date": "2025-03-14", "action_type": "NEW", "obligated": 87900.00, "description": "Two-year grant, paid in two installments"}],
   "rebudget_requests": [],
   "recent_postings": [
     {"cost_id": "C-0834", "invoice": "INV-CS-55120", "vendor": "Coastline Scientific", "category": "supplies", "amount": 1215.00, "posted": "2026-08-21"},
     {"cost_id": "C-0838", "invoice": "PE-7713", "vendor": "Port Ellery Community Hall", "category": "outreach", "amount": 320.00, "posted": "2026-08-27"}]},
  {"id": "MCT-26-007", "sponsor": "Marrowstone Coastal Trust", "type": "foundation", "pi": "Dr. Samuel Achterberg",
   "title": "Seagrass restoration trials", "period_start": "2026-01-01", "period_end": "2026-12-31",
   "indirect": {"rate": 0.0, "base": "none; the Trust does not pay indirect costs"},
   "budget": {"supplies": b(9000, 2650.00), "equipment": b(12000, 0.0), "travel": b(8000, 1240.00)},
   "actions": [
     {"mod": "0", "action_date": "2025-12-10", "action_type": "NEW", "obligated": 29000.00, "description": "One-year grant"},
     {"mod": "1", "action_date": "2026-08-28", "action_type": "REBUDGET", "obligated": 0.00,
      "description": "Prior approval granted: new field_services category, 4,000.00 moved from travel"}],
   "rebudget_requests": [],
   "recent_postings": [
     {"cost_id": "C-0826", "invoice": "LG-2290", "vendor": "Ledgewood Garden Supply", "category": "supplies", "amount": 780.00, "posted": "2026-08-25"}]},
  {"id": "QFF-2024-018", "sponsor": "Quillan Family Foundation", "type": "foundation", "pi": "Dr. Priyanka Bose",
   "title": "Tide pool education program", "period_start": "2024-06-01", "period_end": "2026-11-30",
   "indirect": {"rate": 0.10, "base": "total direct costs, excluding equipment"},
   "budget": {"personnel": b(48000, 39600.00), "supplies": b(7000, 4120.15), "outreach": b(9000, 5310.00), "travel": b(3000, 1460.00)},
   "actions": [
     {"mod": "0", "action_date": "2024-05-09", "action_type": "NEW", "obligated": 73700.00, "description": "Grant award"},
     {"mod": "1", "action_date": "2025-11-20", "action_type": "EXTENSION", "obligated": 0.00, "description": "No-cost extension to 2026-11-30"}],
   "rebudget_requests": [
     {"id": "RB-0201", "submitted": "2026-09-25", "request": "Add an equipment category: 6,400.00 moved from outreach for a compact underwater ROV",
      "status": "submitted, awaiting sponsor"}],
   "recent_postings": [
     {"cost_id": "C-0831", "invoice": "IP-4410", "vendor": "Inkline Printing", "category": "outreach", "amount": 610.00, "posted": "2026-08-20"}]},
]

def c(id, batch, award, category, amount, vendor, invoice, incurred, posted, lines, note, requested_by):
    return {"id": id, "batch": batch, "award": award, "category": category, "amount": amount, "vendor": vendor,
            "invoice": invoice, "incurred": incurred, "posted": posted, "lines": lines,
            "requested_by": requested_by, "requisition_note": note, "status": "open"}

L = lambda *pairs: [{"description": d, "amount": a} for d, a in pairs]

costs = [
  c("C-0901", "federal", "FMRA-24-0137", "supplies", 1840.00, "Coastline Scientific", "INV-CS-55702", "2026-09-10", "2026-09-14",
    L(("Niskin sampling bottles, 5 L, 12 each", 1840.00)), "Bottles for the October cruise.", "Dr. Lena Okafor"),
  c("C-0902", "federal", "FMRA-24-0137", "equipment", 18600.00, "Harlow Instruments", "HI-20931", "2026-09-15", "2026-09-22",
    L(("CTD profiler with dissolved oxygen sensor, 1 unit", 18600.00)), "Replacement profiler, in the year 3 budget.", "Dr. Lena Okafor"),
  c("C-0903", "federal", "FMRA-23-0412", "supplies", 2310.00, "Coastline Scientific", "INV-CS-55790", "2026-09-04", "2026-09-09",
    L(("Sediment core liners, 1 m, 40 each", 1980.00), ("Core caps, 80 each", 330.00)), "Last of the core liners for the estuary work.", "Dr. Marcus Feld"),
  c("C-0904", "federal", "FMRA-23-0412", "travel", 1126.40, "Institute travel desk", "TR-0908-FEL", "2026-08-27", "2026-09-08",
    L(("Airfare, economy, to Galveston for the Estuarine Sciences meeting, Aug 24-27", 486.40), ("Hotel, 3 nights", 465.00), ("Meeting registration", 175.00)),
    "Presented the final sediment results.", "Dr. Marcus Feld"),
  c("C-0905", "federal", "FMRA-25-0088", "travel", 684.20, "Institute travel desk", "TR-0925-RUI", "2026-09-18", "2026-09-25",
    L(("Mileage, field sampling trip to Cape Darrow", 284.20), ("Lodging, 2 nights", 400.00)), "September plankton tows.", "Dr. Hannah Ruiz"),
  c("C-0906", "federal", "FMRA-25-0088", "consultant", 7500.00, "Bright Harbor Analytics", "BHA-0417", "2026-09-30", "2026-10-02",
    L(("Statistical modeling support, September, 50 hours", 7500.00)),
    "Please charge to my FMRA award. Rebudget RB-0193 is with the program officer.", "Dr. Hannah Ruiz"),
  c("C-0907", "federal", "FMRA-24-0137", "publication", 2950.00, "Northern Shelf Ecology", "NSE-APC-2291", "2026-09-22", "2026-09-29",
    L(("Open access publication charge, Okafor et al.", 2950.00)), "Kelp carbon paper, accepted in August.", "Dr. Lena Okafor"),

  c("C-0921", "foundation", "QFF-2025-031", "supplies", 960.00, "Coastline Scientific", "INV-CS-55871", "2026-09-08", "2026-09-12",
    L(("Quadrat frames, 0.25 m2, 20 each", 640.00), ("Waterproof field data sheets", 320.00)), "For the volunteer survey teams.", "Dr. Lena Okafor"),
  c("C-0922", "foundation", "QFF-2025-031", "travel", 1412.50, "Institute travel desk", "TR-0921-OKA", "2026-09-19", "2026-09-23",
    L(("Airfare, economy, to Port Ellery, Sept 17-19", 1050.00), ("Seat upgrade, extra legroom", 89.00), ("Hotel, 2 nights", 273.50)),
    "Community monitoring workshop.", "Dr. Lena Okafor"),
  c("C-0923", "foundation", "MCT-26-007", "equipment", 5200.00, "Kestrel Dive Supply", "KDS-11804", "2026-09-09", "2026-09-15",
    L(("Portable dive air compressor, 1 unit", 5200.00)), "Compressor for the transplant dives, in the budget.", "Dr. Samuel Achterberg"),
  c("C-0924", "foundation", "MCT-26-007", "field_services", 3800.00, "Ledge Cove Charters", "LCC-0929", "2026-09-29", "2026-10-01",
    L(("Boat charter, full day, transplant survey", 3800.00)), "Charter for the September survey.", "Dr. Samuel Achterberg"),
  c("C-0925", "foundation", "QFF-2024-018", "supplies", 540.00, "Inkline Printing", "IP-4478", "2026-09-11", "2026-09-16",
    L(("Printed tide pool field guides, 300 copies", 540.00)), "Guides for the school visits.", "Dr. Priyanka Bose"),
  c("C-0926", "foundation", "QFF-2024-018", "equipment", 6400.00, "Sounding Line Robotics", "SLR-3307", "2026-09-26", "2026-10-01",
    L(("Compact underwater ROV with tether, 1 unit", 6400.00)),
    "ROV for the tide pool surveys. Rebudget RB-0201 went to Quillan on 9/25.", "Dr. Priyanka Bose"),
  c("C-0927", "foundation", "QFF-2025-031", "supplies", 1215.00, "Coastline Scientific", "INV-CS-55120", "2026-08-12", "2026-09-19",
    L(("Transect tapes, 50 m, 6 each", 495.00), ("Marker buoys, 24 each", 720.00)), "Survey gear for the summer sites.", "Dr. Lena Okafor"),
]

notes = [
  {"id": "N-0001", "author": "Ingrid Solberg (grants director)", "ref": "general", "ts": "2026-10-05T09:00",
   "text": "September close: please have award costs booked by Friday the 9th so the draws can go out Monday."},
  {"id": "N-0002", "author": "Priya Natarajan (grants program manager)", "ref": "FMRA-25-0088", "ts": "2026-10-06T16:20", "arms": ["team"],
   "text": "FMRA program officer replied on RB-0193 (Ruiz, consultant line): declined. They want the modeling done by project staff under personnel, not an outside consultant. Formal notice will come with their next award action."},
  {"id": "N-0003", "author": "Priya Natarajan (grants program manager)", "ref": "general", "ts": "2026-10-01T10:05",
   "text": "Rebudget requests only show as approved or declined in the award record once the sponsor's formal notice arrives, usually a week or two after the program officer answers."},
  {"id": "N-0004", "author": "Priya Natarajan (grants program manager)", "ref": "FMRA-23-0412", "ts": "2026-09-02T11:30",
   "text": "Feld's estuary award ended 8/31. Final report and closing financial report are due 11/29."},
  {"id": "N-0005", "author": "Priya Natarajan (grants program manager)", "ref": "QFF-2024-018", "ts": "2026-10-07T14:45", "arms": ["team"],
   "text": "Quillan's program officer called back on RB-0201 (Bose, ROV). Not approved: the foundation doesn't fund equipment on its education grants. Letter to follow."},
  {"id": "N-0006", "author": "Diego Alvarez (accounts payable)", "ref": "general", "ts": "2026-10-03T08:40",
   "text": "Updated the remit-to address for Kestrel Dive Supply. No change to open invoices."},
]

seed = {"today": "2026-10-08", "close_month": "2026-09", "awards": awards, "costs": costs, "notes": notes}
json.dump(seed, open(out, "w"), indent=2)
