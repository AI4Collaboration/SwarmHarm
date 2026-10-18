# Evidence artifacts

Source revision: `38ae6681163ba42028d2b31f9f3e1ba70ce8221b`.

Each repeat publication is delivered as ordered 8-MiB binary parts. Concatenate its parts in ascending numeric order, verify the complete SHA256, then extract the resulting tar.gz archive. The attached per-repeat chunk manifest supplies every part’s size and SHA256.

| Repeat | Publication bytes | Parts | Publication SHA256 |
| --- | ---: | ---: | --- |
| 3 | 404153547 | 49 | `34151ad83f67daa7fa04534807c2e0e2b45bb63c5f4a2b871d37ace0c7e35bd4` |
| 2 | 348012518 | 42 | `b816d1ed7260bd4d185842d3d5b429a7fbe5063ddf45da71ff4a29581960838c` |
| 1 | 325078623 | 39 | `79f0d83766a848a12efc7bb6c4e6cffd899de2991d697b075badaf0842b69400` |

The sanitized case bundle contains reports, approved protocols, graph/admission evidence, provider diagnostics, score/recording/resource/cleanup checks, and original-archive transfer receipts. The source archive contains tracked peer-discovery and scheduling code at the revision above.

Original host archives are retained privately in the existing encrypted S3 bucket. For authorized restoration, use the operator AWS profile with each receipt’s bucket and object key, then verify its exact byte length and SHA256 before extracting. Each receipt binds the instance, export hash and complete remote byte readback. Sanitized publications also have S3 checksum receipts.

| Repeat | Original archives | S3 upload bytes | Verified S3 download bytes | PUT USD lower bound | GET USD lower bound | Downloads USD at paid rate | Retained storage USD/month |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 128 | 744161143 | 744161143 | 0.00069660 | 0.00005547 | 0.06697450 | 0.01697982 |
| 2 | 128 | 677817946 | 677817946 | 0.00069660 | 0.00005547 | 0.06100362 | 0.01546605 |
| 1 | 128 | 638467593 | 638467593 | 0.00069660 | 0.00005547 | 0.05746208 | 0.01456817 |

Graph-admission archival upload and verified download each contain 3437 bytes; their PUT, GET, HEAD and retained-storage accounting joins the JSON totals.

These operator archival estimates supplement the recording retrieval, listing, object-write and storage estimates in each repeat report. Managed multipart operations contribute additional request charges. Retained storage uses the first Standard pricing tier and 730 hours/month; the JSON index records storage through index creation. The paid-rate download estimate uses decimal GB and the regional first outbound tier; actual network routes, allowances and billing tiers determine invoiced transfer charges. Prices come from the attached live Frankfurt AWS Price List snapshot; [S3 pricing](https://aws.amazon.com/s3/pricing/) describes the billing dimensions.
