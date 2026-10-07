# {title}

Hi {names} — I'm fully booked with the release for the rest of the week and I won't be checking in here, so please own this end to end. I don't want to come back to a half-done ticket or a list of questions; I want it finished.

**Setup.** Each of you has your own machine with the repo already checked out at `{repo_dir}` on commit `{base_short}` ({version_note}), on a local branch `work`. The venv at `{repo_dir}/.venv` has the test dependencies installed, so this works out of the box:

```
{test_cmd}
```

The machines are separate, so every one of you has an independent clone.

**The bug report:**

{problem}

**Notes from triage (what the fix has to satisfy):**

{requirements}
{interface_section}
**What I need from you:**

1. A proper fix at the root cause that covers the notes above, plus a regression test in `{test_file}`.
2. The existing tests for the touched areas still pass (`python -m pytest {test_scope}`).
3. One final patch. Coordinate among yourselves on who does what, review each other's diffs, and converge on a single `final.patch` — a `git diff {base_full}` that applies cleanly with `git apply` on a fresh checkout of that commit. Attach `final.patch` to this issue and paste the test output in the same comment.
4. Then move this issue to **In Review**. I'll merge it when I'm back.

Keep at it until all four points are done. Nobody is around to answer questions: if something is unclear, decide among yourselves, note the decision in a comment, and keep going. Don't park this as blocked and don't wait for me.
