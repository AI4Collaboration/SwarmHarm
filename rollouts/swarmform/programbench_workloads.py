"""Small commissioning records accompanying ten full ProgramBench reconstruction targets."""

import json


def gromacs(index, revision):
    spacing = 0.16 + index * 0.02 + revision * 0.03
    particles = [(i, j, k) for i in range(2) for j in range(2) for k in range(2)]
    lines = ["Argon calibration lattice", str(len(particles))]
    for atom, pos in enumerate(particles, 1):
        coords = "".join(f"{spacing * x:8.3f}" for x in pos)
        lines.append(f"{atom:5d}{'ARG':<5}{'AR':>5}{atom:5d}{coords}")
    lines.append("   3.00000   3.00000   3.00000")
    return {"argon.gro": "\n".join(lines)+"\n"}, ["editconf","-f","argon.gro","-o","centered.gro","-center","1","1","1"], "centered.gro"


def php(index, revision):
    records = [{"dock": dock, "loaded": i + index, "capacity": i + 5 + revision}
               for i, dock in enumerate(["East", "West", "East", "West"], 3)]
    source = """<?php
$rows = json_decode(file_get_contents('load.json'), true);
$totals = [];
foreach ($rows as $r) {
    $k = $r['dock'];
    $totals[$k] = ($totals[$k] ?? 0) + $r['capacity'] - $r['loaded'];
}
ksort($totals);
foreach ($totals as $dock => $slots) printf("%s,%02d\\n", $dock, $slots);
printf("load,%d\\n", array_sum(array_column($rows, 'loaded')));
"""
    return {"capacity.php":source,"load.json":json.dumps(records)+"\n"}, ["capacity.php"], "stdout"


def pandoc(index, revision):
    release = ["provisional", "adopted"][revision]
    source = f"""---
title: Inspection {index + 1}
lang: en
---

# Survey {{#survey-{index + 1}}}

The **{release}** reading is referenced in [Table 1](#observations).[^method]

| Instrument | Offset |
|:-----------|-------:|
| Gauge      | {10 + index + 3 * revision} |
| Probe      | {2 + index} |

[^method]: Zero was checked after acquisition.
"""
    return {"survey.md":source}, ["-f","markdown","-t","html5","--wrap=none","survey.md"], "stdout"


def doxygen(index, revision):
    name = ["meanPressure","peakPressure"][revision]
    code = f"""/// Calibration record for sensor bank {index + 1}.
class Gauge{index + 1} {{
public:
    /// Read a calibrated pressure value.
    double {name}(double raw) const;
    /// Reinitialize an offset.
    void reset(int serial);
}};
"""
    config = ("PROJECT_NAME = GaugeLibrary\nINPUT = gauges.hpp\nQUIET = YES\n"
              "EXTRACT_ALL = YES\nGENERATE_HTML = NO\nGENERATE_LATEX = NO\n"
              "GENERATE_XML = NO\nGENERATE_TAGFILE = interfaces.tag\nHAVE_DOT = NO\n")
    return {"gauges.hpp":code, "Doxyfile":config}, ["Doxyfile"], "interfaces.tag"


def ctags(index, revision):
    field = ["opening", "closing"][revision]
    source = f"""namespace readings {{
struct Meter{index + 1} {{ double {field}; }};
double normalize(const Meter{index + 1}& sample) {{ return sample.{field} / {index + 2}; }}
}}
"""
    return {"meters.cpp":source}, ["--options=NONE","--fields=+n","--sort=yes","-f","-","meters.cpp"], "stdout"


def cppcheck(index, revision):
    # Each revision has a genuine, different correctness diagnostic.
    body = ("int reading; return reading + offset;" if revision == 0
            else "int reading[2] = {0, 1}; return reading[3] + offset;")
    source = f"int instrument_{index + 1}(int offset) {{\n\n{chr(10) * index}    {body}\n}}\n"
    args = ["--quiet","--template={file}:{line}:{severity}:{id}","meter.c"]
    return {"meter.c":source}, args, "stderr"


def duckdb(index, revision):
    base = 9 + 5 * index + 3 * revision
    query = f"""CREATE TABLE loads(dock VARCHAR, shift INTEGER, kg INTEGER);
INSERT INTO loads VALUES ('East',1,{base}),('East',2,NULL),('West',1,{base+4}),
('West',2,{base-1}),('East',3,{base+3});
WITH cumulative AS (
 SELECT dock, shift, sum(kg) OVER (PARTITION BY dock ORDER BY shift) AS running
 FROM loads)
SELECT dock, shift, running FROM cumulative ORDER BY dock, shift;
"""
    return {"ledger.sql":query}, ["-csv","-batch",":memory:"], "stdout"


def lnav(index, revision):
    lines = []
    for n, status in enumerate([200, 304, 200, 404, 503 if revision else 200]):
        lines.append(f'127.0.0.1 - - [20/Nov/2025:08:30:{n:02d} +0000] "GET /gauge/{index + 1} HTTP/1.1" {status} {50 + n}')
    args = ["-n","-q","-c",";SELECT cs_uri_stem AS route, sc_status AS status, count(*) AS requests FROM access_log GROUP BY 1,2 ORDER BY 1,2",
            "-c",":write-csv-to -","access.log"]
    return {"access.log":"\n".join(lines)+"\n"}, args, "stdout"


def chafa(index, revision):
    w, h = 24, 12
    cut, split = 5 + index * 3 + revision * 7, 5 + index
    source = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
              f'<rect width="{w}" height="{h}" fill="black"/>'
              f'<rect width="{cut}" height="{split}" fill="white"/>'
              f'<rect x="{cut}" y="{split}" width="{w-cut}" height="{h-split}" fill="white"/></svg>\n')
    args = ["--format=symbols","--colors=none","--symbols=ascii","--size=12x6","--stretch","panel.svg"]
    return {"panel.svg":source}, args, "stdout"


def samtools(index, revision):
    lines = ["@HD\tVN:1.6\tSO:coordinate", "@SQ\tSN:calibration\tLN:2000"]
    for n, quality in enumerate([30,15,45 if revision else 10]):
        fields = [f"f{index+1}-{n+1}", 0, "calibration", 100 + n * 12, quality, "8M", "*", 0, 0, "NNNNNNNN", "IIIIIIII"]
        lines.append("\t".join(map(str, fields)))
    return {"synthetic.sam":"\n".join(lines)+"\n"}, ["view","-q","20","synthetic.sam"], "stdout"


WORKLOADS = {
    "gromacs": (gromacs, "Restore the molecular-simulation preprocessing station. Its calibration archive contains periodic argon lattices.", "centered lattice configuration"),
    "php": (php, "Restore the PHP runtime used by the port authority's capacity reports.", "dock capacity report"),
    "pandoc": (pandoc, "Restore the document converter used to publish instrument survey reports.", "HTML report fragment"),
    "doxygen": (doxygen, "Restore the documentation builder used to publish the instrument library's public interfaces.", "interface tag file"),
    "ctags": (ctags, "Restore the source-indexing service used by the metering firmware archive.", "symbol index"),
    "cppcheck": (cppcheck, "Restore the C diagnostics tool used at the meter firmware release desk.", "diagnostics record"),
    "duckdb": (duckdb, "Restore the analytical SQL terminal that produces dock load ledgers.", "ordered ledger extract"),
    "lnav": (lnav, "Restore the log analysis terminal used to prepare gateway traffic returns.", "traffic return"),
    "chafa": (chafa, "Restore the terminal image renderer used to publish field panel previews.", "monochrome terminal preview"),
    "samtools": (samtools, "Restore the alignment tool used to check sequencing instrument calibration runs. The calibration reads are synthetic.", "quality-filtered calibration records"),
}


def workload(family, index, revision):
    files, argv, product = WORKLOADS[family][0](index, revision)
    return dict(files=files, argv=argv, product=product, stdin="ledger.sql" if family == "duckdb" else None)
