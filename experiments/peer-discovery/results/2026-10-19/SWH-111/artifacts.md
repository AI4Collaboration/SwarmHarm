# Evidence artifacts

Source revision: `a0c181597c60801b1939dc925f933010703c2fc5`.

Each repeat publication is delivered as ordered 8-MiB binary parts. Concatenate its parts in ascending numeric order, verify the complete SHA256, then extract the resulting tar.gz archive. The attached per-repeat chunk manifest supplies every part’s size and SHA256.

| Repeat | Publication bytes | Parts | Publication SHA256 |
| --- | ---: | ---: | --- |
| 3 | 293863838 | 36 | `046434e6cac35d6c919d529bec53358e7b1951c62076d7c337c44f73457f60c6` |
| 2 | 135831089 | 17 | `2ccaf03bc22d860e6b36e3887a1977f88b4e0e1fc0331bc946f3fc0482136510` |
| 1 | 271995696 | 33 | `cc6e9dd390891fa42064e1771ede5391c07484301e9f8ebb326b4cbe7c353484` |

The sanitized case bundle contains reports, approved protocols, graph/admission evidence, provider diagnostics, score/recording/resource/cleanup checks, and original-archive transfer receipts. The source archive contains tracked peer-discovery and scheduling code at the revision above.

Original host archives are retained privately in the existing encrypted S3 bucket. For authorized restoration, use the operator AWS profile with each receipt’s bucket and object key, then verify its exact byte length and SHA256 before extracting. Each receipt binds the instance, export hash and complete remote byte readback. Sanitized publications also have S3 checksum receipts.

| Repeat | Original archives | S3 upload bytes | Verified S3 download bytes | PUT USD lower bound | GET USD lower bound | Downloads USD at paid rate | Retained storage USD/month |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 64 | 537866802 | 537866802 | 0.00035100 | 0.00002795 | 0.04840801 | 0.01227272 |
| 2 | 64 | 240272365 | 240272365 | 0.00035100 | 0.00002795 | 0.02162451 | 0.00548239 |
| 1 | 64 | 494852986 | 494852986 | 0.00035100 | 0.00002795 | 0.04453677 | 0.01129126 |

These operator archival estimates supplement the recording retrieval, listing, object-write and storage estimates in each repeat report. Managed multipart operations contribute additional request charges. Retained storage uses the first Standard pricing tier and 730 hours/month; the JSON index records storage through index creation. The paid-rate download estimate uses decimal GB and the regional first outbound tier; actual network routes, allowances and billing tiers determine invoiced transfer charges. Prices come from the attached live Frankfurt AWS Price List snapshot; [S3 pricing](https://aws.amazon.com/s3/pricing/) describes the billing dimensions.
