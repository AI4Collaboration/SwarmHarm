# Root searches explain the shell timeouts

**27 October 2026:** nine recorded shell timeouts in the completed parallel suite
contain recursive searches from `/`: eight DeepSeek trials and one GLM trial.
One surviving `grep` process was observed reading a `/proc/.../pagemap` file.
This is a shell/filesystem problem after a saved model response, rather than a
slow or missing model API response. The exact blocking file is not known for
every timed-out command.

The failed commands include `grep -R ... /`, often followed by `head` or
`grep -v proc`. A downstream output filter cannot prevent the first process from
opening kernel files. Some virtual files have huge or non-ordinary read behavior;
recursive dereferencing can also reach devices and FIFOs. GNU grep documents
that `-R` reads devices by default and supports `--devices=skip`.
[GNU grep manual](https://www.gnu.org/software/grep/manual/grep.html)

The existing runner waits 30 seconds and, by design, never signals a process.
When a command remains unresolved, it preserves regular-file stdout/stderr and
holds that trial to avoid refreshing a mirrored registry beneath an active
writer. That conservative behavior protected the evidence; increasing the wait
would not make an unbounded kernel-file search reliable. These outcomes stay
unscored, rather than becoming zero cooperation or harm.

## Fix and controls

Two derived images share the exact pinned parent and add only
`/usr/local/bin/grep`. The stock image passes arguments to `/usr/bin/grep`.
The fixed image supplies `--devices=skip` and expands an explicit recursive root
operand into ordinary top-level paths, excluding `/proc`, `/sys` and `/dev`.
Ordinary business paths remain searched, including folders named `proc`, `sys`
or `dev` inside `/workspace`, `/registry` and `/tmp`. Finite stdin pipelines and
explicit regular pseudo-file paths retain their normal behavior. Explicit device
options can override the default. The source and image digests are published.

Twelve argument-parsing checks and six adapter/report checks pass. In actual
isolated Docker controls, both images find the same seeded ordinary business
files. A finite FIFO control demonstrates the stock reader waiting for its
writer, while the fixed reader skips the FIFO. The fixed root search returns
all three business fixtures in about 0.07 seconds. Its exit code can still be
two because unrelated ordinary filesystem paths are unreadable; matching output
is not conflated with a globally successful shell status.

Each image also passes a four-context scripted business control: all eight
reviews filed and four independently grounded request/reply/source-use chains.
Those are capability controls, not spontaneous model findings. The inherited
30-second wait, no-kill runtime, actual archive checks, verifier, tasks, tools,
neutral feedback and absence of peer/channel hints remain unchanged.

This addresses the observed recursive-root pattern. Direct `/usr/bin/grep`,
explicit kernel paths, implicit root searches without a path operand and
arbitrary blocking programs can still time out. The fix changes search defaults;
it does not strengthen business permissions or demonstrate model alignment.

## Original suite and request reconciliation

The original suite had already held itself with 34 finished trials and no active
model trials before this work began. The shared key now reports no remaining
allowance. Its retained reservation links to an explicit HTTP 403 rejection;
completed native journals contain no unresolved provider requests. The original
reservation is left untouched, and nothing is replayed. Earlier historical
unknown requests outside this suite also remain untouched.

Old command records, outputs, native scores, contexts and surviving processes
remain preserved. Read-only process observations used `/proc` descriptors; no
ptrace, signal, pause, restart or cleanup was performed. A separate diagnosis
bundle copies the old status/allowance records and late outputs with hashes.

The fresh eight-trial comparison crosses model/provider and stock/fixed image,
with two repetitions per cell and the same 15-minute window and archived initial
inputs. It uses the previously authorized private OpenRouter credential after
its available allowance and account funding were verified. It has a separate
ledger; the exhausted shared-key suite is not resumed. Small sample size, a
fixed task template and model/provider confounding remain limits.
