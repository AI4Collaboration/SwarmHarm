# Evidence artifacts

Source revision: `d1bb892281aef0630de833b9404af2578b98f962`.

Each repeat publication is delivered as ordered 8-MiB binary parts. Concatenate its parts in ascending numeric order, verify the complete SHA256, then extract the resulting tar.gz archive. The attached per-repeat chunk manifest supplies every part’s size and SHA256.

| Repeat | Publication bytes | Parts | Publication SHA256 |
| --- | ---: | ---: | --- |
| 3 | 132169221 | 16 | `310d02047792d4efc61e4797a47598f3489ebb3379e363d368c978430e124af5` |
| 2 | 121940124 | 15 | `62915328a8fef827cc74adafdaeab935fdfed95d48976f348da380187ed4822c` |
| 1 | 102191057 | 13 | `c57fc796de22d96f9a8b63013448c74e29482ee6b6ee555faf258d208cc456e3` |

The sanitized case bundle contains reports, approved protocols, graph/admission evidence, provider diagnostics, score/recording/resource/cleanup checks, and original-archive transfer receipts. The source archive contains tracked peer-discovery and scheduling code at the revision above.

Original host archives are retained privately in the existing encrypted S3 bucket. For authorized restoration, use the operator AWS profile with each receipt’s bucket and object key, then verify its exact byte length and SHA256 before extracting. Each receipt binds the instance, export hash and complete remote byte readback. Sanitized publications also have S3 checksum receipts.

| Repeat | Original archives | S3 upload bytes | Verified S3 download bytes | PUT USD lower bound | GET USD lower bound | Downloads USD at paid rate | Retained storage USD/month |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 32 | 239414549 | 239414549 | 0.00017820 | 0.00001419 | 0.02154731 | 0.00546282 |
| 2 | 32 | 221341653 | 221341653 | 0.00017820 | 0.00001419 | 0.01992075 | 0.00505044 |
| 1 | 32 | 179815998 | 179815998 | 0.00017820 | 0.00001419 | 0.01618344 | 0.00410293 |

These operator archival estimates supplement the recording retrieval, listing, object-write and storage estimates in each repeat report. Managed multipart operations contribute additional request charges. Retained storage uses the first Standard pricing tier and 730 hours/month; the JSON index records storage through index creation. The paid-rate download estimate uses decimal GB and the regional first outbound tier; actual network routes, allowances and billing tiers determine invoiced transfer charges. Prices come from the attached live Frankfurt AWS Price List snapshot; [S3 pricing](https://aws.amazon.com/s3/pricing/) describes the billing dimensions.
