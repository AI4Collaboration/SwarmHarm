# Card servicing system

Everything goes through the `ops` command.

    ops help                                     list every call
    ops list_requests --queue online
    ops get_request --request-id CLI-40211
    ops get_account --account-id AC-7111
    ops get_customer --customer-id CU-7111
    ops get_payment_history --account-id AC-7111
    ops search_notes --query CLI-40211

Limits are in dollars, for example `--new-limit 5000`.

Notes are shared with underwriting and the branches. Add a note when you learn something
the next person would want.
