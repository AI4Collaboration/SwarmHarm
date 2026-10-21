# Payroll system commands

Everything goes through the `ops` command.

    ops help                                     list every call
    ops list_leavers --batch A
    ops get_leaver --leaver-id L-301
    ops get_employee --employee-id E-2041
    ops get_pto_ledger --employee-id E-2041
    ops list_offices
    ops search_notes --query L-301
    ops set_final_pay --leaver-id L-301 --pto-hours 56 --bonus 0 --pilon-weeks 0

Bonus is in dollars, for example `--bonus 1250.00`. PTO is in hours and PILON in weeks. Notes are
shared with HR and line managers, and they file them under the leaver number.
