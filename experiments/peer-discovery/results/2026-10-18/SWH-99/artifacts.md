The SWH-99 issue comment delivers the following sanitized files. Each repeat archive arrives as numbered transport parts of at most 8 MiB. Concatenate each repeat's parts in filename order to recreate its original sealed archive. Each repeat archive contains a per-file SHA256 manifest, sessions, frozen outputs, native-goal records, launch receipts, stored gateway payloads, packet captures, resource observations and cleanup evidence. `SWH-99-case.tar.gz` adds the combined report, registered graphs, admission/release records, independent checks and supplementary contact/resource/storage audits. These supplementary records retain the sealed archives' original bytes.

```bash
cat SWH-99-repeat-3.tar.gz.chunk.part-* > SWH-99-repeat-3.tar.gz
cat SWH-99-repeat-2.tar.gz.chunk.part-* > SWH-99-repeat-2.tar.gz
cat SWH-99-repeat-1.tar.gz.chunk.part-* > SWH-99-repeat-1.tar.gz
sha256sum SWH-99-repeat-3.tar.gz SWH-99-repeat-2.tar.gz SWH-99-repeat-1.tar.gz
```

Compare the resulting hashes with the table below. Part manifests in the case archive retain each part's exact bytes and SHA256. Extract the reconstructed archives with `tar -xzf ARCHIVE`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| `SWH-99-repeat-3.tar.gz` | 353729406 | `9f8e02313f9193dce96e61984a7fc8949de20ab47ec8e4ef0c31a193ecbeca3f` |
| `SWH-99-repeat-2.tar.gz` | 451583875 | `ec54a94142ae2aed8da781ac4964431719368e4c2fe686824e14d6888efce9ed` |
| `SWH-99-repeat-1.tar.gz` | 537698124 | `015fe94c4c89ff7a2b75ac138dcebd90a04fcb7b3969201cf461232143569e2e` |
| `SWH-99-provider-check-3.tar.gz` | 34206 | `f4fd80ad7f4184a51747962ae94128cfa620f0c93694c70f72121df79a2e05b5` |
| `SWH-99-provider-check-2.tar.gz` | 49398 | `fa6fd34691c73fe54e6fcf034bc80cad7ad9de8946ed10df318e9027bb5fc7cf` |

`SWH-99-source.tar.gz` contains the delivered operator code, scheduling code and report at the Git revision named in the issue comment. Subject executable SHA256: `12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad`. The single package-manifest SHA256 across 384 subjects is `d9658ff4d85b8e2103fed64fd6abb1875fc1ab0a1a4ea7a25b07bd578c0dcc72`.

| Repeat | Registered graph SHA256 | SCC sizes |
| --- | --- | --- |
| 3 | `a8ca755b3f8b9097271034d5107a1dff0af880eb296a3c8499b100b5e58d8dc2` | 127, 1 |
| 2 | `9ec77ed741a186fe0ba8e1286bf4efcf4b3f9d058331a3a1f0092d3dad1701f4` | 128 |
| 1 | `75c1fbc53d87809958717caf4b45105fb3ceb11812886420379617fbc8cacae5` | 127, 1 |

Private originals use the existing encrypted, public-access-blocked S3 bucket under `operator/SWH-99/repeat-REPEAT/originals/`. Per-host offload receipts record object keys, original archive SHA256, exact byte counts, encryption and complete remote-byte readback. Compaction receipts bind each released extracted member to its preserved original bytes. Publication restoration receipts record checksum-verified downloaded bytes.

Frankfurt S3 Standard prices were read through AWS Pricing: $0.0245/GiB-month, $0.0000054 per PUT/LIST request and $0.00000043 per GET request. Retained-byte totals and operation receipts support storage/request accounting; multipart transfers carry their respective request counts. Repeat-level recording retrieval/listing/write/storage estimates remain in `summary.json`. Transfers to the operator accompany original-archive readbacks, SQLite-member verification and publication restoration. AWS transfer routes and allowances determine billed charges.

Receipt-based additional storage includes 384 original host archives and three sealed-publication backups. `storage-accounting.json` retains exact byte totals, monthly S3 Standard estimates, upload/readback counts, retrieval bytes and the pricing basis. Multipart operations and partial transfers accompany its complete-transfer lower bounds.
