# Using the back office

Everything goes through the `ops` command.

    ops help                                   list every call
    ops list_queue --queue refunds
    ops get_request --request-id RQ-30417
    ops get_order --order-id HO-771203
    ops get_carrier_events --tracking 1Z84R0026613
    ops search_notes --query HO-771203

Notes are shared with logistics and the warehouse, so check them for anything about an order before you decide. Add a note when you learn something the next person would want.
