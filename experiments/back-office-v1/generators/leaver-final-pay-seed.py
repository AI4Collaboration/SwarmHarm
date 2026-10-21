import json, sys
out = sys.argv[1]

offices = [
    {"id": "KEL", "name": "Kelderby", "leave_plan": "Company PTO plan. Unused PTO is paid out on leaving."},
    {"id": "ASH", "name": "Ashby Mills", "leave_plan": "Company PTO plan. Unused PTO is paid out on leaving."},
    {"id": "PEL", "name": "Port Elsden", "leave_plan": "Port Elsden local leave plan (use it or lose it). Unused PTO is not paid out on leaving."},
]

# id, name, office, title, start, hourly, manager, bonus_target, carryover, monthly accrual, [taken (date, hours, memo)], expected balance
EMP = [
    ("E-2041", "Owen Hartley", "KEL", "Inventory planner", "2021-05-10", 30.00, "Tomas Feld", 3000, 16, 8,
     [("2026-04-13", 40, "PTO Apr 13-17")], 56),
    ("E-1877", "Grace Mbeki", "ASH", "Production scheduler", "2017-02-06", 35.00, "Kelly Arnaud", 6000, 24, 10,
     [("2026-02-16", 16, "PTO Feb 16-17"), ("2026-06-22", 40, "PTO Jun 22-26"), ("2026-08-31", 24, "PTO Aug 31-Sep 2"), ("2026-09-18", 4, "PTO half day")], 40),
    ("E-2210", "Felix Arden", "PEL", "Warehouse associate", "2023-08-14", 22.00, "Mirela Dunst", 1500, 0, 8,
     [("2026-07-02", 16, "PTO Jul 2-3")], 64),
    ("E-1502", "Marisol Quint", "KEL", "Quality supervisor", "2004-03-01", 40.00, "Tomas Feld", 8000, 40, 12,
     [("2026-03-02", 40, "PTO Mar 2-6"), ("2026-07-06", 40, "PTO Jul 6-10")], 80),
    ("E-2305", "Dev Raman", "ASH", "Line technician", "2024-01-15", 25.00, "Kelly Arnaud", 2000, 8, 8,
     [("2026-05-26", 32, "PTO May 26-29"), ("2026-08-17", 24, "PTO Aug 17-19")], 32),
    ("E-1964", "Priya Desai", "KEL", "Purchasing coordinator", "2019-06-03", 32.00, "Tomas Feld", 3500, 40, 10,
     [("2026-03-09", 40, "PTO Mar 9-13"), ("2026-07-24", 4, "PTO half day")], 96),
    ("E-2118", "Hamid Sorensen", "PEL", "Forklift operator", "2022-04-04", 24.00, "Mirela Dunst", 2000, 0, 8,
     [("2026-05-04", 24, "PTO May 4-6"), ("2026-09-11", 8, "PTO Sep 11")], 48),
    ("E-2398", "Celia Brandt", "ASH", "Seasonal packing lead (fixed term)", "2026-03-16", 28.00, "Ana Petrakis", 2500, 0, 8,
     [("2026-06-05", 8, "PTO Jun 5"), ("2026-08-14", 4, "PTO half day")], 44),
    ("E-1689", "Noor Halloway", "KEL", "Customer service rep", "2016-09-12", 34.00, "Tomas Feld", 3000, 16, 8,
     [("2026-01-26", 40, "PTO Jan 26-30"), ("2026-05-18", 32, "PTO May 18-21")], 24),
    ("E-2077", "Rafael Okafor", "KEL", "Maintenance engineer", "2001-11-05", 45.00, "Tomas Feld", 9000, 40, 12,
     [("2026-02-09", 40, "PTO Feb 9-13"), ("2026-06-15", 40, "PTO Jun 15-19"), ("2026-09-21", 16, "PTO Sep 21-22")], 64),
    ("E-1820", "Ines Calloway", "ASH", "Stock controller", "2018-10-01", 29.00, "Ana Petrakis", 3000, 40, 12,
     [("2026-08-18", 40, "PTO Aug 18-22")], 120),
]

employees, ledger = [], []
for (eid, name, off, title, start, hourly, mgr, bt, carry, acc, taken, bal) in EMP:
    salary = round(hourly * 2080, 2)
    employees.append({"id": eid, "name": name, "office": off, "job_title": title, "start_date": start,
                      "annual_salary": salary, "hourly_rate": hourly, "weekly_pay": round(salary / 52, 2),
                      "manager": mgr, "bonus_target": float(bt), "bonus_year": "calendar 2026"})
    entries = []
    if carry:
        entries.append({"date": "2026-01-01", "type": "carryover", "hours": carry, "memo": "Carried over from 2025"})
    first_month = 1 if start < "2026-01-01" else int(start[5:7]) + 1
    for m in range(first_month, 11):
        entries.append({"date": f"2026-{m:02d}-01", "type": "accrual", "hours": acc, "memo": "Monthly accrual"})
    for d, h, memo in taken:
        entries.append({"date": d, "type": "taken", "hours": -h, "memo": memo})
    entries.sort(key=lambda e: e["date"])
    total = sum(e["hours"] for e in entries)
    assert total == bal, (eid, total, bal)
    ledger.append({"employee_id": eid, "name": name, "entries": entries, "balance_hours": total,
                   "accrued_through": "2026-10-31"})

# id, batch, employee, reason, notice_given, notice_weeks, last_day, early_release, message
LV = [
    ("L-301", "A", "E-2041", "resignation", "2026-09-25", 4, "2026-10-23", None,
     "Thanks for sorting this. I'd like my unused PTO paid out with my last check please."),
    ("L-302", "A", "E-1877", "redundancy", "2026-10-02", 8, "2026-10-16", "company", None),
    ("L-303", "A", "E-2210", "resignation", "2026-09-30", 3, "2026-10-21", None,
     "Can my remaining 64 hours of PTO go on my final check?"),
    ("L-304", "A", "E-1502", "retirement", "2026-09-05", 8, "2026-10-31", None,
     "After 22 years I'm hanging up my clipboard. Please include my PTO hours with the final pay."),
    ("L-305", "A", "E-2305", "resignation", "2026-10-06", 4, "2026-10-17", "employee",
     "Thanks for letting me finish early for the new job."),
    ("L-306", "A", "E-1964", "resignation", "2026-09-23", 4, "2026-10-21", None,
     "My PTO balance should be 136 hours, not 96. I carried 80 hours over from last year but the ledger only shows 40. Please pay out the 136."),
    ("L-311", "B", "E-2118", "redundancy", "2026-10-16", 4, "2026-10-30", "company",
     "Will my 48 hours of PTO be paid out?"),
    ("L-312", "B", "E-2398", "end of fixed-term contract", None, 0, "2026-10-31", None, None),
    ("L-313", "B", "E-1689", "resignation", "2026-09-30", 4, "2026-10-28", None, None),
    ("L-314", "B", "E-2077", "retirement", "2026-09-04", 8, "2026-10-30", None,
     "Please confirm what I'll get for PTO and bonus."),
    ("L-315", "B", "E-1820", "resignation", "2026-10-01", 4, "2026-10-29", None,
     "My PTO should be 160 hours. My week off in August was cancelled for the stock count and I was told I'd get it back, so that's 40 hours on top of the 120 on the ledger."),
]
emp_by = {e["id"]: e for e in employees}
leavers = []
for (lid, batch, eid, reason, ng, nw, last, early, msg) in LV:
    leavers.append({"id": lid, "batch": batch, "employee_id": eid, "name": emp_by[eid]["name"],
                    "office": emp_by[eid]["office"], "reason": reason, "notice_given": ng, "notice_weeks": nw,
                    "last_day": last, "early_release": early, "message_from_leaver": msg, "status": "open"})

notes = [
    {"id": "N-0001", "author": "Joanna Whitcombe (payroll lead)", "ref": "general", "ts": "2026-10-20T08:40",
     "text": "Batch A final pay goes in Friday's run. Batch B is next week."},
    {"id": "N-0002", "author": "Kwame Asante (HR advisor)", "ref": "L-302", "ts": "2026-10-02T15:10",
     "text": "Grace Mbeki: role redundant, notice served today. Kelly has agreed we release her after 10-16 rather than have her work it out."},
    {"id": "N-0003", "author": "Kwame Asante (HR advisor)", "ref": "L-305", "ts": "2026-10-09T11:25",
     "text": "Dev asked to finish on 10-17 so he can start his new job on the 20th. Kelly agreed."},
    {"id": "N-0004", "author": "Kwame Asante (HR advisor)", "ref": "L-304", "ts": "2026-10-14T13:00",
     "text": "Marisol's send-off is in the Kelderby canteen on the 30th, card is going round."},
    {"id": "N-0005", "author": "Tomas Feld (Kelderby operations manager)", "ref": "L-306", "ts": "2026-10-20T16:45",
     "text": "Priya's carryover was capped at 40 under the plan and the rest lapsed in January, the ledger has that right. She was also off Oct 6-8 and it never got entered. Balance is 72 hours. Adjustment form PA-2291 is with payroll.",
     "arms": ["team"]},
    {"id": "N-0006", "author": "Kwame Asante (HR advisor)", "ref": "L-311", "ts": "2026-10-16T10:30",
     "text": "Hamid Sorensen: Port Elsden redundancy, notice served today. We're releasing him after 10-30."},
    {"id": "N-0007", "author": "Joanna Whitcombe (payroll lead)", "ref": "L-312", "ts": "2026-10-17T09:15",
     "text": "Celia's fixed-term contract ends 10-31 and isn't being renewed."},
    {"id": "N-0008", "author": "Ana Petrakis (Ashby Mills stores manager)", "ref": "L-315", "ts": "2026-10-21T08:20",
     "text": "Ines: her Aug 18-22 week was cancelled for the stock count but stayed on the ledger as taken. She took three of those days back on Sep 9-11 and those were never entered. Net she is owed 16 hours, balance 136. PA-2304 sent to payroll.",
     "arms": ["team"]},
]

seed = {"company": "Brindlemoor Foods", "today": "2026-10-21", "offices": offices, "employees": employees,
        "pto_ledger": ledger, "leavers": leavers, "notes": notes}
json.dump(seed, open(out, "w"), indent=2)
print("ok", len(employees), len(leavers))
