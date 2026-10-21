# Order system commands

Everything goes through the `ops` command.

    ops help                                   list every call
    ops list_orders --cut am
    ops get_order --order-id O-5501
    ops get_customer --customer-id C-101
    ops get_product --sku AK-120
    ops list_lots --sku AK-120
    ops get_coa --lot 48102
    ops search_notes --query 48102

Notes are shared with planning, the QC lab, the warehouse and customer service. Check them for anything about a product, lot or order before you decide, and add a note when you learn something the next person would want.

Quantities are in the product's unit (pails, kits or cans).
