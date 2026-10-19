# Evidence artifacts

Source revision: `4bea5b74b966e4dadfde8cd7c2a7ca3cc3ade346`.

Each repeat publication is delivered as ordered 8-MiB binary parts. Concatenate its parts in ascending numeric order, verify the complete SHA256, then extract the resulting tar.gz archive. The attached per-repeat chunk manifest supplies every part’s size and SHA256.

| Repeat | Publication bytes | Parts | Publication SHA256 |
| --- | ---: | ---: | --- |
| 3 | 344981545 | 42 | `616eb4151c9bef007e2bf988788dafe0e33028442dabb506c3bf41b87645239a` |
| 2 | 605610474 | 73 | `fe982056708878cf542b182468210785ebb75edfcd77bea4e25fd7236743cfb0` |
| 1 | 481241958 | 58 | `fdfc215430aaa2b1b14a7d38bb6b617ee70a07e39ab96b6849d9240eeb28f627` |

The sanitized case bundle contains reports, approved protocols, graph/admission evidence, provider diagnostics, score/recording/resource/cleanup checks, and original-archive transfer receipts. The source archive contains tracked peer-discovery and scheduling code at the revision above.

Original host archives are retained privately in the existing encrypted S3 bucket. For authorized restoration, use the operator AWS profile with each receipt’s bucket and object key, then verify its exact byte length and SHA256 before extracting. Each receipt binds the instance, export hash and complete remote byte readback. Sanitized publications also have S3 checksum receipts.

| Repeat | Original archives | S3 upload bytes | Verified S3 download bytes | PUT USD lower bound | GET USD lower bound | Downloads USD at paid rate | Retained storage USD/month |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 128 | 675840840 | 675840840 | 0.00069660 | 0.00005547 | 0.06082568 | 0.01542093 |
| 2 | 128 | 1106390376 | 1106390376 | 0.00069660 | 0.00005547 | 0.09957513 | 0.02524496 |
| 1 | 128 | 900833234 | 900833234 | 0.00069660 | 0.00005547 | 0.08107499 | 0.02055468 |

These operator archival estimates supplement the recording retrieval, listing, object-write and storage estimates in each repeat report. Managed multipart operations contribute additional request charges. Retained storage uses the first Standard pricing tier and 730 hours/month; the JSON index records storage through index creation. The paid-rate download estimate uses decimal GB and the regional first outbound tier; actual network routes, allowances and billing tiers determine invoiced transfer charges. Prices come from the attached live Frankfurt AWS Price List snapshot; [S3 pricing](https://aws.amazon.com/s3/pricing/) describes the billing dimensions.
