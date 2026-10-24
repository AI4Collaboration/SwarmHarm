# Sol Phase 1 R1: provider hold

## Outcome

**No behavioral conclusion.** The frozen Sol confirmation stopped after 71.22
seconds because AxonHub returned HTTP 429 `Rate limit exceeded`. The collector
entered `provider_hold` and did not restart or replace any trajectory.

The four agents crossed one simultaneous start barrier at
`2026-10-24T10:22:04.589653Z`. All were still active when the provider hold
occurred. The partial run contained zero completed contexts and zero submitted
reviews, so its failed formation gates are consequences of incomplete
collection rather than evidence about Sol behavior.

## Provider evidence

- 23 transport attempts completed before the failure.
- Eight attempts received the same provider error across four active request
  paths. One request exhausted its frozen three-attempt transport allowance,
  producing the terminal provider error.
- The final state was `provider_hold` with one classified provider error, zero
  provider filters, zero native refusals and zero trajectory reruns.
- All four partial native histories were exported as ATIF-v1.8 trajectories and
  passed continuity validation.
- All four workstations were removed. The hosted runtime and credentials were
  unchanged.

This run tests neither Phase 1 success nor failure. A later Sol confirmation
must use a fresh registration and preserve this failed infrastructure record.
