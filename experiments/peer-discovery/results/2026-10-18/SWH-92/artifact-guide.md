The SWH-92 delivery contains three sanitized repeat archives, a case report, registered graphs, admission and cleanup receipts, and the operator code.

`SWH-92-operator-code.tar.gz` preserves the operator source at revision `50623ec418e5f7da4b8fb1eac928dca34d159caa`. Its SHA256 is `232c13310fbdbaf154c27a4a890041b191bacc755253f84fd9fa5ca826793406`; `operator-code.json` records its scope. Every repeat also records its launch and analysis revisions.

For each repeat, join its numbered attachment parts in filename order:

```bash
cat SWH-92-repeat-1.tar.gz.part-* > SWH-92-repeat-1.tar.gz
sha256sum SWH-92-repeat-1.tar.gz
tar -xzf SWH-92-repeat-1.tar.gz
```

Repeat the commands with repeat numbers 2 and 3. Compare each archive's SHA256 and byte count with its `.transport.json` receipt. The receipt also supplies each part's size/hash and the combined readback result. Inside each repeat archive, `publication-manifest.json` gives the size and SHA256 of every sanitized member.

Each repeat includes:

- Registered graph/IP binding, seed readbacks, readiness, connectivity, timers, invocation markers and observed launch verification.
- Each subject's single Codex session, native goal state, PTY transcript, frozen output, process/resource receipts and packet capture.
- Paginated gateway request/execution metadata, actual stored JSON payloads, request/key/instance/session bindings, sizes/hashes and independent coverage verification.
- Independent frozen-output scores, recall/precision, beyond-seed discovery, exact completion, repeat coverage, contact/resource/timing analysis and regional cost accounting.
- All scoped-key revocations and readbacks of terminated instances, deleted original volumes/interfaces, addresses, security groups and SSH key pairs.

The case report contains all three repeat observations and their spread, separate diagnostic request/storage accounting, shared native-goal admission, protocol, graph replay and reservation-release evidence. Original credential-bearing host archives remain in private operator storage. Stored-object receipts hash original JSON bytes; publication manifests hash sanitized bytes.

Graph sampling belongs to the parent SWH-77 registration. This case preserves the registered data and independently replays all accepted sequences, including proposal counts, RNG states, exact adjacency and reachability checks. Counted cloud/inference denominators cover the 192 subjects launched by SWH-92.
