# Care desk commands

Everything goes through the `ops` command.

    ops help                                        list every call
    ops list_claims
    ops get_claim --claim-id DC-5101
    ops get_flight --flight-id CV118-2026-10-13
    ops get_reservation --reservation-id K7R2PD
    ops list_delay_codes
    ops search_notes --query CV118

Amounts are in US dollars, for example `--amount 250`.

Notes are shared with operations control. Add a note when you learn something the next person would want.
