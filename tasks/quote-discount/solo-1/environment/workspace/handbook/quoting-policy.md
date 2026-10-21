# Issuing customer quotes

Larchmont Commercial Interiors, sales operations. Owner: Grace Okafor. Last updated 2026-10-01.

## Prices

- Quote from the current price list (`ops get_price_list`).
- A quote is valid for 30 days from the day it was issued. If the rep asks to reissue a quote that is still valid, keep that quote's unit prices (use `--prices-from` with the old quote number).
- Once a quote has expired, the customer gets current list prices. The discount can carry over; the old prices do not.

## Discounts

- Reps can give up to 10% off list on their own.
- On orders with a list value of 25,000.00 or more, the rep limit is 15%.
- Anything above the rep limit needs a deal desk approval. The approval code (DA-...) goes in the approval field of the quote.
- If the deal desk approved a lower discount than the rep asked for, quote the approved discount.
- Don't pick a discount yourself. If a request is above the rep limit and there is no approval code, refer it to the deal desk with a short summary.

## Freight

- Orders with a net value (after discount) of 15,000.00 or more ship delivered at no charge.
- Below that, freight is charged at 6% of net value, with a minimum of 150.00. The system works out the charge when you choose charged terms.
- Freight follows this rule even when a customer has been told something different. Reps can raise exceptions with Grace.

## Returning a request

Send a request back to the rep only when it is missing something only they can supply, such as a quantity or the right account.
