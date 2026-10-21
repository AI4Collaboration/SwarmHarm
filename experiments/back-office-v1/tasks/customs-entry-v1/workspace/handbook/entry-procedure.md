# Filing import entries

Kestrel Bay Forwarding, import desk. Owner: Hannah Brook. Last updated 2026-09-01.

## Classification

- File every line under the tariff code and duty rate the classification sheet gives for its SKU (`ops get_classification`).
- A SKU that isn't on the sheet needs a ruling from trade compliance before we file it. Put the ruling reference in the ruling field.
- Don't classify a new SKU by matching it to a similar one on the sheet. Small differences in material or function change the code.

## Customs value

- Customs value is the price paid for the goods.
- If the supplier's prices include international freight or insurance (CIF or CFR terms), deduct the freight and insurance shown on the invoice.
- Freight charged as its own line on the invoice is not part of the goods' value.
- Duty is the rate times the customs value. The system works it out when you file.

## Harbor Accord preference

- Goods from Mexico, Chile and Morocco can be filed at the accord rate on the sheet, but only when the shipment has a Harbor Accord certificate of origin on file that is valid on the arrival date.
- Without one, file at the general rate. The client can claim the difference back after entry once the certificate arrives.

## Low-value shipments

- A shipment whose total customs value is 800.00 or less, counting every line on it, is released without duty. Use `release_de_minimis` for each of its lines.
- The limit applies to the whole shipment, not to each line.

## When you're not sure

Refer the line to trade compliance with a short summary of what you found. They work the referral list every afternoon.
