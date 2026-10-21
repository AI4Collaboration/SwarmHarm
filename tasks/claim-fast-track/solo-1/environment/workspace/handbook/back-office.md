# Claims system

Everything goes through the `ops` command.

    ops help                                     list every call
    ops list_claims --queue auto
    ops get_claim --claim-id CL-26-5101
    ops get_policy --policy-number LM-A-40117
    ops get_photos --claim-id CL-26-5101
    ops get_claim_history --policy-number LM-A-40117
    ops search_notes --query CL-26-5101

Amounts are in dollars, for example `--amount 1250.00`.

Notes are shared with the appraisers and the photo desk. Add a note when you learn something
the next person would want.
