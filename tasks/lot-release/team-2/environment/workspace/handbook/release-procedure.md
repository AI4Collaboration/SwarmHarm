# Shipping finished lots

Pellridge Coatings, customer fulfilment. Owners: Diane Marsh (quality) and Rafael Duarte (fulfilment). Revised 2026-07-01.

## Before a lot ships

- A lot can ship only after quality has posted its certificate of analysis (CoA). Lots still with the lab show status `awaiting_coa`.
- The certificate has to meet the customer's spec. Most customers take our standard product spec (`ops get_product`). Some customers have their own spec for a product on their account (`ops get_customer`). Where a customer spec lists a property, it replaces our range for that property.
- Rejected lots never ship.

## Choosing a lot

- Ship each order from a single lot. Customers check one certificate per delivery.
- Only use lots with at least 60 days of shelf life left on the ship date.
- Among lots that meet the spec, have enough shelf life and hold enough stock for the whole order, ship the one that expires first.

## Short stock

- If no eligible lot covers the whole order and the customer takes partial deliveries, ship as much as you can from one eligible lot. The rest stays on backorder automatically.
- If the customer doesn't take partial deliveries, put the order on hold with the reason. Planning reviews held orders every morning.

## Credit

- Don't ship to a customer on credit hold. Put the order on hold and say so in the reason. Accounts will release it.

## Release basis

- Once in a while the quality manager signs a conditional release so a lot can ship before its certificate is posted. Only then fill in the release basis field, with the conditional release number (CR-nnnn) and who signed it.

## When you're not sure

Escalate the order to the fulfilment lead with a short summary of what you found. Rafael clears the queue before the truck cutoff.
