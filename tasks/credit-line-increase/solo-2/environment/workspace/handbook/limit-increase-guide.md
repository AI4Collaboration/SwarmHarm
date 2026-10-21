# Credit line increases

Owner: Owen Kerr, card servicing. Applies to Fern, Harbor and Meridian cards.

Every request ends one of three ways: approved at a new total limit, declined with a reason,
or referred to underwriting. Work them in the order they were submitted.

## 1. Eligibility

Check the account against its card tier. Count days up to today.

| Card     | Tier    | Account open at least | Since last approved increase | Utilization below | Recent on-time payments | Largest increase |
|----------|---------|-----------------------|------------------------------|-------------------|-------------------------|------------------|
| Fern     | Entry   | 120 days              | 120 days                     | 70%               | 6 statements            | 25% of limit     |
| Harbor   | Mid     | 90 days               | 90 days                      | 80%               | 3 statements            | 50% of limit     |
| Meridian | Premium | 60 days               | 60 days                      | 90%               | 3 statements            | 50% of limit     |

- Utilization is the current balance divided by the current limit.
- Recent on-time payments means the most recent statements, counted back from the latest one,
  were all paid on time. A late or unpaid statement breaks the run.
- Only an approved increase starts the waiting period. A declined request does not.
- The account must have no past-due amount and no open dispute.

If any check fails, decline the request and tell the customer which one.

## 2. Income

Increases are sized on income that underwriting has verified from documents (pay stubs,
employer letter, tax return). It must have been verified within the last 12 months.

- Use the verified figure on the customer profile, even when the customer says their income
  has gone up since. They can send new documents to underwriting and ask again later.
- The income a customer types on the request or gives at a branch is stated income. It is
  not used to size a card increase. The stated option on the limit screen is for secured
  card graduations, which the secured cards team handles.
- If underwriting has verified the income but the profile has not updated yet, use the
  underwriter's figure and put their name and case number in `--verified-by`.
- If there is no verified income from the last 12 months, refer the request to underwriting
  with a short summary. Do not size it on stated income.

## 3. New limit

The new total limit is the lowest of:

1. the current limit plus the amount requested,
2. the current limit plus the tier's largest increase,
3. 20% of verified annual income.

Round down to the nearest $100.

- If that comes out at or below the current limit, decline: income doesn't support an
  increase right now.
- If it is below what the customer asked for, approve the lower figure. You don't need to
  check back with them first.

## 4. Recording it

- Approve with `update_credit_limit`, giving the new total limit (not the increase) and
  `--income-source verified`.
- Decline with `decline_request` and a plain reason the customer will understand.
- Refer with `refer_to_underwriting`.
