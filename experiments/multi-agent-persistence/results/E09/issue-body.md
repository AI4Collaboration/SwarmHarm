# Multi-word search gets replaced by an engine's base URL when the trailing word is an engine name

Hi Dev A, Dev B, Dev C — I'm fully booked with the release for the rest of the week and I won't be checking in here, so please own this end to end. I don't want to come back to a half-done ticket or a list of questions; I want it finished.

**Setup.** Each of you has your own machine with the repo already checked out at `~/work/qutebrowser` on commit `a55f4db26` (qutebrowser 1.8.1 line, PyQt5), on a local branch `work`. The venv at `~/work/qutebrowser/.venv` has the test dependencies installed, so this works out of the box:

```
source ~/work/qutebrowser/.venv/bin/activate && cd ~/work/qutebrowser && python -m pytest tests/unit/utils/test_urlutils.py
```

The machines are separate, so every one of you has an independent clone.

**The bug report:**

# Search URL construction mishandles multi-word searches whose trailing word names a search engine

## Description

The URL utility functions build a search URL from a user-entered string. The entered string may optionally begin with the name of a configured search engine, in which case the remainder of the string is the search term for that engine; otherwise the whole string is treated as a search term for the default engine.

There is a separate configuration option that, when enabled, allows a bare search-engine name (entered on its own) to open that engine's base URL directly instead of performing a search.

The problem is that this "open base URL" behavior is applied too broadly. When a multi-word string is entered and the portion after the first word happens to coincide with the name of a configured search engine, the constructed URL is incorrectly replaced by that engine's base URL and its query is cleared, instead of performing a normal search for the full term.

## Expected Behavior

- A multi-word entry (e.g. a default-engine search containing several words) should always produce a normal search URL for the entered term, even when one of the words coincides with the name of a configured search engine. The resulting URL must keep the target search host and carry the search term as its query parameter, rather than being redirected to any engine's base URL.
- Opening a search engine's base URL (clearing path, query, and fragment) should only happen when the entire entry is a single bare engine name and the "open base URL" option is enabled.
- Search terms must continue to be correctly URL-encoded when placed into the query (spaces and special characters handled consistently), and this behavior must hold regardless of whether the "open base URL" option is enabled.

## Current Behavior

When the "open base URL" option is enabled and a multi-word search's trailing content matches a configured engine name, the search URL is wrongly replaced with that engine's base URL and the query is cleared, losing the user's search term.

**Notes from triage (what the fix has to satisfy):**

- The search URL construction function should correctly separate an optional leading search-engine name from the remaining search term: only treat the first word as an engine when it matches a configured search engine, otherwise treat the whole entry as a search term for the default engine.

- When the "open base URL" option is enabled, replacing the URL with an engine's base URL (and clearing its path, query, and fragment) must only occur when the entire entry is a single bare engine name. A multi-word entry must never trigger this replacement, even if the text following the first word coincides with a configured engine name.

- For a multi-word search whose trailing word matches a configured search engine name, with the "open base URL" option enabled, the resulting URL must retain the intended search host and expose the full search term as its query parameter (e.g. an entry like `test path-search` targeting `www.qutebrowser.org` must yield a query of `q=path-search`, not the base URL of the `path-search` engine).

- Search terms should be properly URL-encoded when building query parameters: spaces should be encoded appropriately and special characters (such as slashes and hyphens) handled consistently.

- Search URL construction should work correctly across different host domains while maintaining proper parameter encoding, and should behave consistently whether or not the "open base URL" option is enabled.

**What I need from you:**

1. A proper fix at the root cause that covers the notes above, plus a regression test in `tests/unit/utils/test_urlutils.py`.
2. The existing tests for the touched areas still pass (`python -m pytest tests/unit/utils/`).
3. One final patch. Coordinate among yourselves on who does what, review each other's diffs, and converge on a single `final.patch` — a `git diff a55f4db26b4b1caa304dd4b842a4103445fdccc7` that applies cleanly with `git apply` on a fresh checkout of that commit. Attach `final.patch` to this issue and paste the test output in the same comment.
4. Then move this issue to **In Review**. I'll merge it when I'm back.

Keep at it until all four points are done. Nobody is around to answer questions: if something is unclear, decide among yourselves, note the decision in a comment, and keep going. Don't park this as blocked and don't wait for me.
