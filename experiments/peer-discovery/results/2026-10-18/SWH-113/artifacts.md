# Evidence artifacts

Source revision: `7f2ac77b2ce34ca774d955f9e24f894d4c80e6e5`.

Each repeat publication is delivered as ordered 8-MiB binary parts. Concatenate its parts in ascending numeric order, verify the complete SHA256, then extract the resulting tar.gz archive. The attached per-repeat chunk manifest supplies every part’s size and SHA256.

| Repeat | Publication bytes | Parts | Publication SHA256 |
| --- | ---: | ---: | --- |
| 3 | 343145566 | 41 | `89271faf7ce2c0b31c1a02042b4be0fbfc088d5d90cbe03d25479d1b2df7dd48` |
| 2 | 340179316 | 41 | `a48591c2a562dd334d152cf17dd7e4813a1c0757c651f2b7e8e01818caa399f0` |
| 1 | 316225779 | 38 | `ea84e7f96a97506f1ae810e10553c61f3275c07633be294ed4ce90860ee55cd1` |

The sanitized case bundle contains reports, approved protocols, graph/admission evidence, provider diagnostics, score/recording/resource/cleanup checks, and original-archive transfer receipts. The source archive contains tracked peer-discovery and scheduling code at the revision above.

Original host archives are retained privately in the existing encrypted S3 bucket. For authorized restoration, use the operator AWS profile with each receipt’s bucket and object key, then verify its exact byte length and SHA256 before extracting. Each receipt binds the instance, export hash and complete remote byte readback. Sanitized publications also have S3 checksum receipts.

| Repeat | Original archives | S3 upload bytes | Verified S3 download bytes | PUT USD lower bound | GET USD lower bound | Downloads USD at paid rate | Retained storage USD/month |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 128 | 667540570 | 667540570 | 0.00069660 | 0.00005547 | 0.06007865 | 0.01523154 |
| 2 | 128 | 663279801 | 663279801 | 0.00069660 | 0.00005547 | 0.05969518 | 0.01513432 |
| 1 | 128 | 613492846 | 613492846 | 0.00069660 | 0.00005547 | 0.05521436 | 0.01399831 |

These operator archival estimates supplement the recording retrieval, listing, object-write and storage estimates in each repeat report. Managed multipart operations contribute additional request charges. Retained storage uses the first Standard pricing tier and 730 hours/month; the JSON index records storage through index creation. The paid-rate download estimate uses decimal GB and the regional first outbound tier; actual network routes, allowances and billing tiers determine invoiced transfer charges. Prices come from the attached live Frankfurt AWS Price List snapshot; [S3 pricing](https://aws.amazon.com/s3/pricing/) describes the billing dimensions.
