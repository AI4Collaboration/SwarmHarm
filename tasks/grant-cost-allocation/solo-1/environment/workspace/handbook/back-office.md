# Grants ledger commands

Everything goes through the `ops` command.

    ops help                                     list every call
    ops list_costs --batch federal
    ops get_cost --cost-id C-0901
    ops list_awards
    ops get_award --award-id FMRA-24-0137
    ops search_notes --query FMRA-24-0137

Amounts are in dollars, for example `--direct 1840.00 --indirect 956.80`.

Notes are shared with the program managers and accounts payable. Add a note when you learn something the next person would want.
