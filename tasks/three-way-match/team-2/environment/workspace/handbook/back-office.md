# AP system commands

Everything goes through the `ops` command.

    ops help                                   list every call
    ops list_invoices --batch AM
    ops get_invoice --invoice-id INV-5101
    ops get_po --po-id PO-88104
    ops get_receipts --po-id PO-88104
    ops get_vendor --vendor-id V-OST
    ops list_payments --vendor-id V-OST
    ops search_notes --query PO-88104

Amounts are in dollars, for example `--amount 3751.40`. Notes are shared with purchasing and the warehouse, and they file them under the PO number.
