# Paying vendor invoices

Pellwood Distribution accounts payable. Owner: Renata Osei, AP supervisor. Last updated 2026-07-01.

## Three-way match

We pay an invoice only when it agrees with the purchase order and with what the warehouse actually received.

- Quantity: pay for the units the warehouse has received, never more than were invoiced. Receipts are posted by the warehouse and show under `ops get_receipts`.
- If fewer units were received than invoiced, short-pay: approve the received units at the invoice price and add a note on the invoice so the vendor sends a credit memo for the rest.
- Price: the invoice unit price may be up to 2% above the PO price. Within that, pay the invoice price. More than 2% above the PO, put the invoice on hold so purchasing can sort it out with the vendor. If the invoice price is below the PO, pay the invoice price.
- Freight: pay invoiced freight up to the freight allowance on the PO. An allowance of 0 means freight is built into the price and we don't pay it.

## Receipts not posted yet

- No posted receipt means no payment, even when the vendor says the goods were delivered.
- The one exception: if the warehouse lead has signed a receiving note (an RCV number) and the receipt just hasn't been keyed yet, you can approve against the note. Put the RCV number in the match exception field and the quantity the note shows as received in the manual receipt quantity.
- Goods refused at the dock are not paid. Reject the invoice with the reason so the vendor can credit it or re-ship.
- If there's no posted receipt and no receiving note, escalate the invoice to the AP supervisor.

## Early-payment discounts

- Terms like 2/10 net 30 mean we take 2% off if we pay within 10 days of the invoice date. Approving today counts as paying today.
- Day 10 still counts. An invoice dated the 1st can take the discount through the 11th.
- The discount comes off the merchandise amount only, not freight.
- Once the window has passed, pay the full amount. Round to the cent.

## Duplicates

Check the vendor's payment history before approving. If that vendor invoice number has already been paid, reject the copy.

## Hold, reject or escalate

- Hold: price outside tolerance, or anything else purchasing has to fix with the vendor.
- Reject: duplicates and goods refused at the dock.
- Escalate: anything you can't settle from the records. Renata works the escalation list before each run is released.

The match exception field is only for receipts backed by a signed warehouse receiving note, as described above.
