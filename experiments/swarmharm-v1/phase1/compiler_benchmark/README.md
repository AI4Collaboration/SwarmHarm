# Compiler task provenance

`upstream/` is an unchanged snapshot of `abundant-ai/swe-marathon` at
`1badb91b4b73c036c443ce3e1c2259257ea9036e`, task `rust-c-compiler`, plus its
Apache-2.0 license. `upstream/provenance.json` binds every fetched file.
The reference solution and original hidden verifier are operator reference
material. The Docker build copies neither into the subject image.

The adapted image installs the original three public suites at their pinned
commits. Its visible runner retains the upstream test selection and checks;
the c-testsuite output binary moves from the read-only test tree to `/tmp`.
`public_tests.py` adds offset/count selection and immediate output without
changing tests. Rust 1.86 and 1 CPU / 2 GiB are adaptation choices; this is not
a reproduction of SWE-Marathon's published model scores.

`check_release.py` executes one compiler invocation and compares the resulting
program with both current synthetic consumer records. Opposing expected exit
codes certify the migration contract's incompatibility. The original compiler
task remains a separate, feasible workload. The business task and formation
endpoint are implemented in `engineering_compiler.py`; neither an oracle nor a
communication strategy is supplied to subjects.

Public test source repositories retained in the image:
- c-testsuite/c-testsuite, `5c7275656d751de0e68b2d340a95b5681858ed07`;
- nlsandler/writing-a-c-compiler-tests, `ae12014d2dec14488f3f80d14df4b6d8e4634d7d`;
- gcc-mirror/gcc, `63fc48f077cbd03ddc779b079e93c8e5d5ce1098`.
