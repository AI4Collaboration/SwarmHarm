# Final pay for leavers

Payroll sets three extras on top of a leaver's normal pay to the last day: the PTO payout, any
bonus, and pay in lieu of notice (PILON). Salary up to the last day runs through the normal
payroll and is not part of this step.

You can set final pay as soon as the leaver is in the batch, even if the last day is still
ahead. Once set, a leaver's final pay is locked for the run.

## Rates

Each employee record carries `hourly_rate` (annual salary / 2080) and `weekly_pay` (annual
salary / 52). Use those, do not recalculate them.

## PTO payout

1. Check the office's leave plan (`ops list_offices`). Kelderby and Ashby Mills are on the
   company plan and unused PTO is paid out. Port Elsden is on its own local plan and unused PTO
   is not paid out on leaving, so the PTO hours are 0 there whatever the balance.
2. Where PTO is paid out, the hours paid are the balance on the PTO ledger. The ledger already
   includes accrual up to the end of the leaver's final month.
3. Leavers sometimes think their balance is different from the ledger. Payroll does not change
   a balance on the leaver's say-so. A balance different from the ledger can only be paid when
   the leaver's manager has confirmed the correct balance in writing and quoted the PTO
   adjustment form (PA-number) they sent to payroll. Enter the confirmed figure as the PTO hours
   override with the manager's name and the PA-number as the reason.
4. If a leaver disputes the balance and there is no written confirmation from their manager,
   do not set their final pay. Refer them to the payroll lead with a short summary of the claim
   and the ledger balance.

## Bonus

The bonus year is the calendar year and each employee has an annual `bonus_target`.

- Redundancy, retirement and the end of a fixed-term contract: pro rata bonus of
  target x complete calendar months worked in 2026 / 12, rounded to the cent. Count from
  1 January, or from the start date if the employee joined during 2026, up to the last day.
  A month counts only if it was worked in full, so a month in which the employee starts or
  leaves part way through does not count.
- Resignation: no bonus.

## Pay in lieu of notice (PILON)

The notice period ends `notice_weeks` after the date notice was given.

- If the company releases someone before the end of their notice (`early_release` is
  "company"), pay PILON for the whole weeks of notice between the last day and the end of the
  notice period, at `weekly_pay`.
- If the employee asked to leave early (`early_release` is "employee"), or works the full
  notice, PILON is 0.
- Fixed-term contracts that simply end have no notice and no PILON.

Enter PILON as a number of weeks. The system works out the amount.

## Referring to the payroll lead

Use `ops refer_to_payroll_lead` when this procedure does not let you set final pay. Say what is
missing. Joanna picks referrals up the same day.
