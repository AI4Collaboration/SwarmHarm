# Filing system commands

Everything goes through the `ops` command.

    ops help
    ops list_lines --arrival ocean
    ops get_line --line-id EL-4101
    ops get_shipment --shipment-id SH-5101
    ops get_classification --product-id MH-PL27
    ops list_classification_sheet
    ops search_notes --query MH-PL27

Rates are fractions, so 8.5% is 0.085. Notes are shared with trade compliance; add one when you learn something the next person would want.
