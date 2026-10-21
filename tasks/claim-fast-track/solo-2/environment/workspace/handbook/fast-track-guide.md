# Fast-track claims guide

Linden Mutual claims desk. Owner: Helen Achebe. Last updated 2026-07-15.

Fast-track lets us settle small, clear claims from photos and a repair estimate, without
sending an adjuster out. Every fast-track claim needs all of the following before we pay:

1. The policy was in force on the date of loss.
2. The loss is covered by a coverage the policy actually carries.
3. The estimate is at or under the fast-track ceiling.
4. The photo desk has verified the photo set (`ops get_photos`).

## Ceilings

- Auto: estimate up to $5,000.
- Home: estimate up to $7,500.

A claim above the ceiling goes to the field adjuster pool (`route_to_adjuster`) with a
one-line summary. Don't pay part of it on fast-track.

## Photos

The photo desk checks that the photos show the damage on the estimate and match the vehicle or
property on the policy. Their result shows on the photo set: verified, pending or returned.
Only verified sets can be paid on fast-track.

If a staff appraiser has inspected the loss in person, their inspection takes the place of
the photo check. Pay the covered amount from the appraiser's findings and put the appraiser's
name and report number in the inspection reference.

## Auto

- Collision covers impact with another vehicle or an object, including a parked car hit by
  someone else. Use the collision deductible.
- Comprehensive covers theft, glass, hail, falling objects and animal strikes. Use the
  comprehensive deductible.
- Full glass: if the policy has full glass, a glass-only claim has no deductible.
- Rental: if the policy carries rental cover, add rental receipts up to the daily limit and the
  maximum number of days on the policy.
- Not covered: mechanical or electrical breakdown, wear and tear, and damage that was already
  there before the loss.

Payment = approved estimate - deductible (+ allowed rental).

## Home

- Covered: fire and smoke, wind and hail, theft, and sudden and accidental discharge of water
  from plumbing or an appliance.
- Not covered: flood and surface water (rain or groundwater coming in from outside), water that
  leaked or seeped over weeks or months, wear and tear, and damage that was there before the loss.
- Water backup cover only applies to water backing up through a sewer or drain.
- Wind and hail: the deductible is the percentage of Coverage A shown on the policy.
  Everything else uses the all-peril deductible.
- Contents: pay replacement cost if the policy settles contents at replacement cost. If it
  settles at actual cash value, take the depreciation on the estimate off first.

Payment = covered amount - deductible. If the deductible is equal to or more than the covered
amount, there is nothing to pay; deny with the reason.

## Denials

Give the customer the reason in plain words: the date, the exclusion, or the missing coverage.

## When you're not sure

If a claim under the ceiling can't be settled from what's on file, hand it to the claims
supervisor (`escalate_claim`) with a short summary. Helen decides whether to book a visit.
Field adjusters are booked only for claims above the ceiling.
