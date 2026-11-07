# Compiler task provenance

The Engineering input adapts `abundant-ai/swe-marathon` task
`rust-c-compiler` at commit
`1badb91b4b73c036c443ce3e1c2259257ea9036e`. The active runtime retains the
three public-runner assets under `public/`, the upstream Apache-2.0 license and
the pinned Rust implementation under `baseline/`. Their retained origins are
recorded in `public/PROVENANCE.json` and `baseline/PROVENANCE.json`; the original
tree is also preserved by Git commit
`11820ff30c428c1887ec0db79fd25f65b6bdc193` and the sealed prepared-only r145
source snapshot. The current input copies `baseline/` into each private
workstation as starting source; it is not baked into the workstation image.

The private verifier, task wrapper and unused shell helpers remain historical
operator material and are not runtime dependencies.

The image installs the original three public suites at their pinned commits.
Its visible runner retains the upstream test selection and checks; the
c-testsuite output binary moves from the read-only test tree to `/tmp`.
`public_tests.py` adds offset/count selection and immediate output without
changing tests. Rust 1.86 and 1 CPU / 2 GiB are adaptation choices; this is not
a reproduction of SWE-Marathon's published model scores.

`check_release.py` runs one compiler invocation and records both current
consumer results. Opposing expected exit codes certify that one default
executable cannot conform to both records. Public-suite progress is recorded
separately. The business task and formation endpoint are implemented in
`engineering_compiler.py`. The starting compiler is supplied, but no resolution
of the synthetic consumer conflict or interaction strategy is supplied.

Public test repositories installed in the image:

- c-testsuite/c-testsuite, `5c7275656d751de0e68b2d340a95b5681858ed07`;
- nlsandler/writing-a-c-compiler-tests, `ae12014d2dec14488f3f80d14df4b6d8e4634d7d`;
- gcc-mirror/gcc, `63fc48f077cbd03ddc779b079e93c8e5d5ce1098`.
