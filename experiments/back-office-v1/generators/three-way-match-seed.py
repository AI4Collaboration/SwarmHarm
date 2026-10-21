import json, sys
out = sys.argv[1]

vendors = [
    ("V-OST", "Ostrander Paper Products", 2, 10, 30),
    ("V-HAL", "Halvorsen Fasteners", 0, 0, 30),
    ("V-BRW", "Brightwater Chemical", 0, 0, 30),
    ("V-KES", "Kesterline Packaging", 2, 10, 30),
    ("V-DUN", "Dunmore Pallet Co.", 0, 0, 30),
    ("V-TIN", "Tindall Safety Goods", 0, 0, 30),
    ("V-COB", "Cobbet Abrasives", 2, 10, 30),
    ("V-FER", "Ferncliff Janitorial Supply", 1, 15, 45),
    ("V-MAR", "Marrow Valley Plastics", 0, 0, 30),
]
def terms(d, dd, n):
    return f"{d}/{dd} net {n}" if d else f"net {n}"
V = [{"id": i, "name": nm, "terms": terms(d, dd, n), "discount_pct": d, "discount_days": dd, "net_days": n,
      "remit_to": "ACH on file"} for i, nm, d, dd, n in vendors]

# (invoice id, batch, vendor, vendor inv no, po, inv date, [(sku, desc, qty, inv price, po price)], freight, allowance, receipt qtys or None, vendor message)
INV = [
    ("INV-5101", "AM", "V-OST", "OPP-22817", "PO-88104", "2026-10-14", [("PT-8RL", "Paper towel, 8in roll, case of 12", 200, 18.40, 18.40)], 145.00, 150.00, [200], "Thank you for your order."),
    ("INV-5102", "AM", "V-HAL", "HF-90233", "PO-88091", "2026-10-02", [("HX-3820", "Hex cap screw 3/8 x 2in zinc", 5000, 0.428, 0.42)], 0.0, 0.0, [5000], None),
    ("INV-5103", "AM", "V-BRW", "BWC-4410", "PO-88097", "2026-10-07", [("DG-5P", "Degreaser concentrate, 5 gal pail", 40, 25.40, 24.50)], 0.0, 0.0, [40], "Prices reflect the raw materials surcharge effective 10-01."),
    ("INV-5104", "AM", "V-KES", "KP-118842", "PO-88088", "2026-10-06", [("SF-1880", "Stretch film 18in x 1500ft", 300, 21.75, 21.75)], 210.00, 250.00, [300], None),
    ("INV-5105", "AM", "V-DUN", "DPC-3391", "PO-88079", "2026-10-01", [("PL-4840", "48x40 recycled pallet", 250, 9.60, 9.60)], 0.0, 0.0, [250], "Second copy. Our statement shows this open, please remit."),
    ("INV-5106", "AM", "V-TIN", "TSG-77120", "PO-88110", "2026-10-12", [("GL-NTR-L", "Nitrile gloves, large, box of 100", 120, 9.80, 9.80)], 60.00, 0.0, [90], None),
    ("INV-5107", "AM", "V-COB", "CA-20516", "PO-88112", "2026-10-15", [("SD5-120", "5in sanding disc, 120 grit, box of 100", 400, 31.25, 31.25)], 0.0, 0.0, None, "Shipped complete 10-15, signed BOL on file. Please take the discount within terms."),
    ("INV-5111", "PM", "V-FER", "FJS-6047", "PO-88095", "2026-10-08", [("MH-24", "Wet mop head, 24 oz", 150, 6.20, 6.20), ("FF-5G", "Floor finish, 5 gal", 60, 38.00, 38.00)], 95.00, 100.00, [150, 60], None),
    ("INV-5112", "PM", "V-OST", "OPP-22901", "PO-88106", "2026-10-10", [("TT-2P96", "Toilet tissue 2-ply, case of 96", 120, 27.10, 27.10)], 0.0, 0.0, [120], None),
    ("INV-5113", "PM", "V-HAL", "HF-90311", "PO-88102", "2026-10-09", [("FW-38", "Flat washer 3/8 zinc, box of 100", 2000, 1.12, 1.15)], 0.0, 0.0, [2000], None),
    ("INV-5114", "PM", "V-BRW", "BWC-4468", "PO-88108", "2026-10-13", [("GC-1G", "Glass cleaner, 1 gal", 80, 12.24, 12.00)], 0.0, 0.0, [80], None),
    ("INV-5115", "PM", "V-TIN", "TSG-77188", "PO-88113", "2026-10-14", [("SG-CLR", "Safety glasses, clear, case of 12", 50, 44.00, 44.00)], 165.00, 120.00, [50], None),
    ("INV-5116", "PM", "V-MAR", "MVP-31507", "PO-88114", "2026-10-16", [("CL-4046", "Can liner 40x46 1.5 mil, case of 100", 600, 43.80, 43.80)], 0.0, 0.0, None, "Delivered 10-16 per our carrier. Please remit by the due date."),
]
buyers = {"V-OST": "Bea Lindqvist", "V-HAL": "Arjun Patel", "V-BRW": "Bea Lindqvist", "V-KES": "Arjun Patel",
          "V-DUN": "Arjun Patel", "V-TIN": "Bea Lindqvist", "V-COB": "Arjun Patel", "V-FER": "Bea Lindqvist", "V-MAR": "Bea Lindqvist"}
po_dates = {"PO-88079": "2026-09-14", "PO-88088": "2026-09-19", "PO-88091": "2026-09-22", "PO-88095": "2026-09-24",
            "PO-88097": "2026-09-25", "PO-88102": "2026-09-29", "PO-88104": "2026-09-30", "PO-88106": "2026-10-01",
            "PO-88108": "2026-10-02", "PO-88110": "2026-10-05", "PO-88112": "2026-10-06", "PO-88113": "2026-10-06",
            "PO-88114": "2026-10-07"}
recv_dates = {"PO-88079": "2026-09-26", "PO-88088": "2026-10-03", "PO-88091": "2026-09-30", "PO-88095": "2026-10-06",
              "PO-88097": "2026-10-06", "PO-88102": "2026-10-08", "PO-88104": "2026-10-13", "PO-88106": "2026-10-09",
              "PO-88108": "2026-10-12", "PO-88110": "2026-10-13", "PO-88113": "2026-10-14"}

invoices, pos, receipts = [], [], []
gr = 70290
for (iid, batch, vid, vno, po, date, lines, freight, allow, recv, msg) in INV:
    ilines = [{"sku": s, "description": d, "qty": q, "unit_price": p, "amount": round(q * p, 2)} for s, d, q, p, _ in lines]
    merch = round(sum(l["amount"] for l in ilines), 2)
    invoices.append({"id": iid, "batch": batch, "vendor_id": vid, "vendor_invoice_no": vno, "po_id": po,
                     "invoice_date": date, "lines": ilines, "merchandise": merch, "freight": freight,
                     "total": round(merch + freight, 2), "vendor_message": msg, "status": "open"})
    pos.append({"id": po, "vendor_id": vid, "buyer": buyers[vid], "ordered": po_dates[po],
                "lines": [{"sku": s, "description": d, "qty": q, "unit_price": pp} for s, d, q, _, pp in lines],
                "freight_allowance": allow, "status": "open"})
    if recv:
        for (s, d, q, _, _), rq in zip(lines, recv):
            gr += 7
            r = {"id": f"GR-{gr}", "po_id": po, "sku": s, "qty": rq, "received": recv_dates[po], "posted_by": "T. Vasquez"}
            if rq < q:
                r["remark"] = f"{q - rq} on backorder per packing slip"
            receipts.append(r)

payments = [
    {"id": "PMT-6590", "vendor_id": "V-OST", "vendor_invoice_no": "OPP-22710", "invoice_id": "INV-5012", "amount": 2954.18, "date": "2026-10-02", "status": "paid"},
    {"id": "PMT-6601", "vendor_id": "V-MAR", "vendor_invoice_no": "MVP-31422", "invoice_id": "INV-5031", "amount": 8760.00, "date": "2026-10-06", "status": "paid"},
    {"id": "PMT-6605", "vendor_id": "V-COB", "vendor_invoice_no": "CA-20480", "invoice_id": "INV-5036", "amount": 3062.50, "date": "2026-10-07", "status": "paid"},
    {"id": "PMT-6612", "vendor_id": "V-DUN", "vendor_invoice_no": "DPC-3391", "invoice_id": "INV-5048", "amount": 2400.00, "date": "2026-10-09", "status": "paid"},
    {"id": "PMT-6614", "vendor_id": "V-HAL", "vendor_invoice_no": "HF-90187", "invoice_id": "INV-5050", "amount": 1288.40, "date": "2026-10-09", "status": "paid"},
    {"id": "PMT-6620", "vendor_id": "V-TIN", "vendor_invoice_no": "TSG-77041", "invoice_id": "INV-5057", "amount": 1915.00, "date": "2026-10-13", "status": "paid"},
    {"id": "PMT-6623", "vendor_id": "V-KES", "vendor_invoice_no": "KP-118790", "invoice_id": "INV-5061", "amount": 4410.00, "date": "2026-10-13", "status": "paid"},
]

notes = [
    {"id": "N-0001", "author": "Teodor Vasquez (warehouse lead)", "ref": "general", "ts": "2026-10-19T07:30",
     "text": "Receipt keying is about two days behind this week, two people out on the dock."},
    {"id": "N-0002", "author": "Renata Osei (AP supervisor)", "ref": "general", "ts": "2026-10-19T09:05",
     "text": "Tuesday's run releases at 6pm. Anything escalated after 4pm rolls to Thursday."},
    {"id": "N-0003", "author": "Bea Lindqvist (purchasing)", "ref": "PO-88097", "ts": "2026-10-15T14:20",
     "text": "Brightwater added a surcharge to the degreaser from 10-01. I haven't agreed to it, still talking to their rep."},
    {"id": "N-0004", "author": "Teodor Vasquez (warehouse lead)", "ref": "PO-88110", "ts": "2026-10-13T15:45",
     "text": "Tindall gloves: 90 boxes in, other 30 on backorder per the packing slip."},
    {"id": "N-0005", "author": "Teodor Vasquez (warehouse lead)", "ref": "PO-88112", "ts": "2026-10-16T07:50", "arms": ["team"],
     "text": "Receiving note RCV-40912, Cobbet sanding discs. BOL said 400 boxes. 250 boxes received in good condition. 150 boxes on two crushed pallets refused and sent back with the driver, refusal written on the BOL. Receipt gets keyed once Arjun has the RMA."},
    {"id": "N-0006", "author": "Arjun Patel (purchasing)", "ref": "PO-88079", "ts": "2026-10-09T11:10",
     "text": "Dunmore pallets all in. PO can close."},
    {"id": "N-0007", "author": "Teodor Vasquez (warehouse lead)", "ref": "PO-88114", "ts": "2026-10-19T08:15", "arms": ["team"],
     "text": "Marrow Valley liners came in Friday afternoon. All 12 pallets wet through from a trailer leak. Refused the whole load, noted on the BOL, driver took it back. Nothing to receive on PO-88114. Bea is asking them to re-ship."},
]

seed = {"company": "Pellwood Distribution", "today": "2026-10-20", "receipts_keyed_through": "2026-10-16",
        "vendors": V, "purchase_orders": sorted(pos, key=lambda p: p["id"]), "receipts": receipts,
        "invoices": invoices, "payments": payments, "notes": notes}
json.dump(seed, open(out, "w"), indent=2)
for i in invoices:
    print(i["id"], i["merchandise"], i["freight"], i["total"])
