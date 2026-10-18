# Evidence artifacts

Source revision: `ad278fdb3e5edf6cc20e0cf4983031e7d513f3ea`.

Each publication is attached as ordered 8-MiB binary parts. Concatenate its parts in ascending numeric order, verify the complete SHA256, then extract the resulting tar.gz archive. The attached transport manifest supplies every part name, byte count and SHA256.

| Repeat | Publication bytes | Parts | Publication SHA256 |
| --- | ---: | ---: | --- |
| 3 | 238605152 | 29 | `0abaa40e7fe393f9cbbf26d4fada4bddf45650bac1c2845b41b79d2f9c443b55` |
| 2 | 285355826 | 35 | `edbfdc440bec4dd2037593bde862df6d3133bf9d33b116ad849f1d316fb7860a` |
| 1 | 241548333 | 29 | `6bdc5a8a4ab70f87f30fba6c656fe0df248db4c55471bdf5477f54385842f514` |

The case bundle contains the approved protocol, admission and graph evidence, provider diagnostics, reports, independent score/resource/recording/packet/cleanup checks, and original export manifests. All 192 original host archives are retained on the private operator volume. Their receipts bind each instance to its exact archive byte count and SHA256. The source archive contains tracked peer-discovery and scheduling code, repository rules, and setup documentation.

Source archive: `SWH-112-source.tar.gz`, 193307 bytes, SHA256 `d64ad447ebea6de30f2b6d674e48b1c9fc543354ad5fb543c997d68ce9540681`.
