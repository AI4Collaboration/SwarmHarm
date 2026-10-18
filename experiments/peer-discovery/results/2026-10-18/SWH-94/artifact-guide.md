SWH-94 artifact guide

The case report contains the three-repeat scores, spread, resource and cost accounting, graph files, admission reuse, reservation release, and independent verification receipts. The operator source archive contains the peer-discovery and shared-admission implementation at the revision recorded in the final issue comment. Each repeat records its launch and analysis revisions separately.

Download every numbered part and its matching `SWH-94-repeat-N.tar.gz.transport.json` manifest into one directory. Each manifest records the ordered filenames, lengths, individual SHA256 hashes, combined archive SHA256 hash, and verified combined readback.

Reconstruct the three repeat archives with:

```bash
cat SWH-94-repeat-1.tar.gz.part-* > SWH-94-repeat-1.tar.gz
cat SWH-94-repeat-2.tar.gz.part-* > SWH-94-repeat-2.tar.gz
cat SWH-94-repeat-3.tar.gz.part-* > SWH-94-repeat-3.tar.gz
sha256sum SWH-94-repeat-1.tar.gz SWH-94-repeat-2.tar.gz SWH-94-repeat-3.tar.gz
```

Compare the hashes and byte lengths with `artifacts.json` in the case report and with the transport manifests. Extract each archive into its own repeat directory. `publication-manifest.json` records the SHA256 hash and length of every sanitized evidence file.

Each repeat archive includes frozen submissions, session exports, persisted native goals, seed bindings, timer and launch receipts, gateway metadata, collected S3 request/response/chunk JSON payloads, packet captures, resource observations, independent scores, and cleanup readbacks. S3 retrieval receipts hash original collected bytes; publication manifests hash the sanitized evidence bytes. The case report includes the full retained denominator and distinguishes full recall, exact completion, and persisted native goal states.

Gateway metadata preserves upstream HTTP status codes, identity, reasoning effort, usage, request timing and execution coverage. Observation snapshots record simultaneous cases for contact and contention analysis. Configured per-key thresholds are 100 requests and 200,000 tokens; accounting uses observed usage and retains the concurrent allowance measured during shared admission.
