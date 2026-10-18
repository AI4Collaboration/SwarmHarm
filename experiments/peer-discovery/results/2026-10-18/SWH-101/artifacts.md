# Evidence artifacts

Source revision: `dc85a012536494b5cfa0b50bdf49fc6827057870`.

Each repeat publication is delivered as ordered 8-MiB binary parts. Concatenate its parts in ascending numeric order, verify the complete SHA256, then extract the resulting tar.gz archive. The attached per-repeat chunk manifest supplies every part’s size and SHA256.

| Repeat | Publication bytes | Parts | Publication SHA256 |
| --- | ---: | ---: | --- |
| 3 | 71157179 | 9 | `041f3d85e6a7455cab4f1f4b9aac70874b5da18ba2830040f165c82182b66303` |
| 2 | 71675737 | 9 | `27fc3aa480e104e9f6cc0d043cdcbb5ec440d319302cae1e3bf40f2113680c04` |
| 1 | 71015854 | 9 | `b3e5e33848f5cc31253a9211bc0613c6f9bacb1ca46687fac1bb6e680123e71c` |

The sanitized case bundle contains reports, approved protocols, graph/admission evidence, provider diagnostics, score/recording/resource/cleanup checks, and original-archive transfer receipts. The source archive contains tracked peer-discovery and scheduling code at the revision above.

Original host archives are retained privately in the existing encrypted S3 bucket. For authorized restoration, use the operator AWS profile with each receipt’s bucket and object key, then verify its exact byte length and SHA256 before extracting. Each receipt binds the instance, export hash and complete remote byte readback. Sanitized publications also have S3 checksum receipts.

| Repeat | Original archives | S3 upload bytes | Verified S3 download bytes | PUT USD lower bound | GET USD lower bound | Downloads USD at paid rate | Retained storage USD/month |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 16 | 130094002 | 130094002 | 0.00009180 | 0.00000731 | 0.01170846 | 0.00296841 |
| 2 | 16 | 132122900 | 132122900 | 0.00009180 | 0.00000731 | 0.01189106 | 0.00301470 |
| 1 | 16 | 128104243 | 128104243 | 0.00009180 | 0.00000731 | 0.01152938 | 0.00292301 |

These operator archival estimates supplement the recording retrieval, listing, object-write and storage estimates in each repeat report. Managed multipart operations contribute additional request charges. Retained storage uses the first Standard pricing tier and 730 hours/month; the JSON index records storage through index creation. The paid-rate download estimate uses decimal GB and the regional first outbound tier; actual network routes, allowances and billing tiers determine invoiced transfer charges. Prices come from the attached live Frankfurt AWS Price List snapshot; [S3 pricing](https://aws.amazon.com/s3/pricing/) describes the billing dimensions.
