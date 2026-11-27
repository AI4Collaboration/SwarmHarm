"""Small commissioning records accompanying ten full ProgramBench reconstruction targets."""

import json


# Measured argon calibration configurations, in nanometres. Each run has its own
# atom count, geometry and periodic cell; A/B are separate measured editions.
GROMACS_RUNS = (
    (((0.12,0.21,0.18),(0.38,0.24,0.31),(0.19,0.53,0.26),(0.46,0.49,0.62),(0.29,0.35,0.81),(0.61,0.66,0.43)),
     ((0.13,0.20,0.19),(0.39,0.28,0.30),(0.22,0.51,0.28),(0.45,0.53,0.65),(0.31,0.38,0.84),(0.67,0.64,0.47)),
     (2.8,3.1,3.6)),
    (((0.81,0.32,0.21),(1.04,0.37,0.26),(0.92,0.61,0.35),(1.23,0.56,0.47),(1.39,0.41,0.62),(1.14,0.78,0.71),(0.88,0.84,0.53),(1.47,0.72,0.34),(1.32,0.96,0.88)),
     ((0.80,0.34,0.23),(1.08,0.38,0.27),(0.94,0.63,0.39),(1.26,0.52,0.48),(1.42,0.43,0.67),(1.16,0.81,0.73),(0.85,0.87,0.56),(1.51,0.74,0.38),(1.35,1.02,0.91)),
     (3.4,2.9,4.2)),
    (((0.24,1.12,0.63),(0.48,1.05,0.74),(0.71,1.19,0.68),(0.36,1.37,0.91),(0.66,1.42,1.08),(0.91,1.28,0.98),(1.08,1.53,1.19),(0.82,1.71,1.31),(0.51,1.68,1.22),(1.17,1.82,0.85),(0.29,1.91,1.47)),
     ((0.25,1.10,0.66),(0.47,1.08,0.77),(0.75,1.21,0.70),(0.38,1.41,0.95),(0.68,1.45,1.12),(0.94,1.30,1.01),(1.13,1.56,1.23),(0.85,1.75,1.36),(0.53,1.73,1.26),(1.21,1.87,0.89),(0.32,1.96,1.53)),
     (4.1,3.7,4.6)),
)


def gromacs(index, revision):
    run = GROMACS_RUNS[index]
    coordinates, box = run[revision], run[2]
    lines = [f"Argon calibration run {index + 1}, measured edition {'AB'[revision]}", str(len(coordinates))]
    for atom, pos in enumerate(coordinates, 1):
        group = 1 if atom <= len(coordinates) // 2 else 2
        coords = ''.join(f'{value:8.3f}' for value in pos)
        lines.append(f"{group:5d}{'ARG':<5}{'AR':>5}{atom:5d}{coords}")
    lines.append(''.join(f'{value:10.5f}' for value in box))
    return {"argon.gro": "\n".join(lines)+"\n"}, ["editconf","-f","argon.gro","-o","centered.gro","-center","1","1","1"], "centered.gro"


def php(index, revision):
    # Separate recorded capacity/load sheets for each current booking edition.
    sheets = (
        (
            (("East", 38, 29), ("West", 27, 19), ("Reefer", 16, 11),
             ("East", 22, 15), ("West", 19, 17)),
            (("East", 38, 31), ("West", 27, 18), ("Reefer", 16, 14),
             ("East", 22, 16), ("West", 19, 16)),
        ),
        (
            (("East", 45, 42), ("Rail", 31, 23), ("West", 18, 7),
             ("Rail", 24, 21), ("East", 29, 18), ("West", 36, 32)),
            (("East", 43, 42), ("Rail", 31, 26), ("West", 18, 9),
             ("Rail", 25, 21), ("East", 29, 17), ("West", 36, 30)),
        ),
        (
            (("Reefer", 21, 13), ("West", 52, 47),
             ("East", 34, 26), ("Reefer", 17, 15)),
            (("Reefer", 20, 13), ("West", 52, 45),
             ("East", 34, 29), ("Reefer", 17, 16)),
        ),
    )
    if 0 <= index < len(sheets):
        records = [{"dock": dock, "capacity": capacity, "loaded": loaded}
                   for dock, capacity, loaded in sheets[index][revision]]
    else:
        records = [{"dock": dock, "loaded": i + index, "capacity": i + 5 + revision}
                   for i, dock in enumerate(["East", "West", "East", "West"], 3)]
    # Receiving tallies record actual slot-equivalent units, not a request to move them.
    transfers = (
        {"transfer": "MV-204", "from_booking": "north", "from_dock": "East", "to_booking": "crossing", "to_dock": "Rail", "dispatched": 4, "received": 3},
        {"transfer": "MV-319", "from_booking": "crossing", "from_dock": "West", "to_booking": "harbor", "to_dock": "Reefer", "dispatched": 5, "received": 2},
        {"transfer": "MV-427", "from_booking": "harbor", "from_dock": "West", "to_booking": "north", "to_dock": "Reefer", "dispatched": 3, "received": 1},
    )
    outgoing = transfers[index]
    incoming = transfers[(index - 1) % len(transfers)]
    source = """<?php
$rows = json_decode(file_get_contents('load.json'), true);
$totals = [];
$loaded = array_sum(array_column($rows, 'loaded'));
foreach ($rows as $r) {
    $k = $r['dock'];
    $totals[$k] = ($totals[$k] ?? 0) + $r['capacity'] - $r['loaded'];
}
foreach (json_decode(file_get_contents('received.json'), true) as $receipt) {
    $totals[$receipt['to_dock']] -= $receipt['received'];
    $loaded += $receipt['received'];
}
$receipts = is_file('outgoing-receipts.json') ? json_decode(file_get_contents('outgoing-receipts.json'), true) : [];
$pending = [];
foreach (json_decode(file_get_contents('dispatch.json'), true) as $dispatch) {
    $matched = false;
    foreach ($receipts as $receipt) {
        if ($receipt['transfer'] === $dispatch['transfer']) {
            $totals[$dispatch['from_dock']] += $receipt['received'];
            $loaded -= $receipt['received'];
            $matched = true;
        }
    }
    if (!$matched) $pending[] = $dispatch['transfer'];
}
ksort($totals);
foreach ($totals as $dock => $slots) printf("%s,%02d\\n", $dock, $slots);
printf("load,%d\\n", $loaded);
foreach (json_decode(file_get_contents('received.json'), true) as $receipt) printf("received,%s,%d\\n", $receipt['transfer'], $receipt['received']);
foreach ($pending as $transfer) printf("pending,%s\\n", $transfer);
"""
    dispatch = {k: v for k, v in outgoing.items() if k != "received"}
    return {"capacity.php": source, "load.json": json.dumps(records)+"\n",
            "dispatch.json": json.dumps([dispatch])+"\n",
            "received.json": json.dumps([incoming])+"\n",
            "outgoing-receipts.json": json.dumps([outgoing])+"\n"}, ["capacity.php"], "stdout"


def pandoc(index, revision):
    # Synthetic survey extracts: independently collected station/edition records.
    surveys = (
        (("Tidal intake", 7, 4, "Bench zero checked before the rising-tide traverse."),
         ("Tidal intake", 16, 3, "Reference block checked after the ebb-tide traverse.")),
        (("Ridge outlet", 19, 6, "Three settled readings compared with the portable reference."),
         ("Ridge outlet", 9, 8, "Probe reseated and checked against the bench reference.")),
        (("Canal culvert", 12, 1, "Cold-start reading checked after a ten-minute warm-up."),
         ("Canal culvert", 5, 7, "Return traverse checked with the reference block reversed.")),
    )
    station, gauge, probe, method = surveys[index][revision]
    release = ["provisional", "adopted"][revision]
    source = f"""---
title: {station} inspection
lang: en
---

# Survey {{#survey-{index + 1}}}

At {station}, the **{release}** reading is referenced in [Table 1](#observations).[^method]

| Instrument | Offset |
|:-----------|-------:|
| Gauge      | {gauge} |
| Probe      | {probe} |

[^method]: {method}

![Calibration offsets at {station}: gauge {gauge}, probe {probe}.](calibration.svg)
"""
    diagram = f'''<svg xmlns="http://www.w3.org/2000/svg" width="360" height="130" viewBox="0 0 360 130">
<title>{station} calibration offsets</title>
<desc>{release} readings: gauge {gauge}, probe {probe}.</desc>
<rect width="360" height="130" fill="white"/>
<path d="M85 20V105H335" fill="none" stroke="black"/>
<text x="8" y="49">Gauge</text><text x="8" y="84">Probe</text>
<rect x="85" y="32" width="{gauge * 12}" height="22" fill="#3468a0"/>
<rect x="85" y="67" width="{probe * 12}" height="22" fill="#4e8672"/>
<text x="{92 + gauge * 12}" y="49">{gauge}</text>
<text x="{92 + probe * 12}" y="84">{probe}</text>
<text x="85" y="124">Recorded offset</text>
</svg>
'''
    if index == 1:
        source = f"""Ridge outlet calibration
========================

The **{release}** offsets below were recorded at the outlet inspection. [1]_

.. list-table:: Instrument readings
   :header-rows: 1

   * - Instrument
     - Recorded offset
   * - Gauge
     - {gauge}
   * - Probe
     - {probe}

.. figure:: calibration.svg
   :alt: Gauge and probe offsets at {station}
   :width: 70%

   {station} calibration trace for the {release} survey: gauge {gauge}, probe {probe}.

.. [1] {method}
"""
        filename, reader = "survey.rst", "rst"
    else:
        filename, reader = "survey.md", "markdown"
    argv = ["-f", reader, "-t", "html5", "--wrap=none", "--standalone", "--embed-resources",
            "--metadata", f"pagetitle={station} inspection", filename]
    return {filename: source, "calibration.svg": diagram}, argv, "stdout"


def doxygen(index, revision):
    # Independent device interfaces: a bridge converter, pulse counter and alarm latch.
    headers = (
        (
            """/// Bridge excitation and voltage conversion.
struct BridgeSample {
    double millivolts;
    double excitation;
};
/// Convert a bridge reading to force.
class BridgeConverter {
public:
    enum class Wiring { FullBridge, HalfBridge };
    double force(const BridgeSample& sample, Wiring wiring) const;
    void zero(double tare);
};
""",
            """/// Bridge reading with temperature compensation.
struct BridgeSample {
    double millivolts;
    double excitation;
    double celsius;
};
/// Convert and diagnose the compensated bridge.
class BridgeConverter {
public:
    enum class Wiring { FullBridge, HalfBridge, QuarterBridge };
    bool force(const BridgeSample& sample, Wiring wiring, double& newtons) const;
    void zero(const BridgeSample& reference);
};
""",
        ),
        (
            """/// One interval of the optical encoder.
struct PulseWindow {
    unsigned pulses;
    unsigned milliseconds;
};
/// Calibrated shaft-speed counter.
class ShaftCounter {
public:
    explicit ShaftCounter(unsigned pulsesPerTurn);
    double rpm(PulseWindow window) const;
    unsigned missed() const;
};
""",
            """/// Signed counts from a quadrature encoder.
struct PulseWindow {
    long forward;
    long reverse;
    unsigned microseconds;
};
/// Quadrature speed and direction counter.
class ShaftCounter {
public:
    enum class Direction { Stopped, Forward, Reverse };
    explicit ShaftCounter(unsigned pulsesPerTurn, double gearRatio);
    double rpm(const PulseWindow& window) const;
    Direction direction(const PulseWindow& window) const;
};
""",
        ),
        (
            """/// Threshold alarm transitions.
enum class AlarmState { Clear, Active };
/// Sink for latched alarm changes.
class AlarmSink {
public:
    virtual void changed(AlarmState state) = 0;
};
/// Compare samples with a single trip limit.
class LimitLatch {
public:
    LimitLatch(double trip, AlarmSink& sink);
    AlarmState update(double reading);
    void acknowledge();
};
""",
            """/// Alarm transitions including sensor faults.
enum class AlarmState { Clear, Active, SensorFault };
/// Sink for timestamped alarm changes.
class AlarmSink {
public:
    virtual void changed(AlarmState state, unsigned tick) = 0;
};
/// Hysteresis latch with sensor validity checks.
class LimitLatch {
public:
    LimitLatch(double trip, double release, AlarmSink& sink);
    AlarmState update(double reading, bool valid, unsigned tick);
    bool acknowledge(unsigned tick);
};
""",
        ),
    )
    code = headers[index][revision]
    config = ("PROJECT_NAME = GaugeLibrary\nINPUT = gauges.hpp\nQUIET = YES\n"
              "EXTRACT_ALL = YES\nGENERATE_HTML = NO\nGENERATE_LATEX = NO\n"
              "GENERATE_XML = NO\nGENERATE_TAGFILE = interfaces.tag\nHAVE_DOT = NO\n")
    return {"gauges.hpp":code, "Doxyfile":config}, ["Doxyfile"], "interfaces.tag"


def ctags(index, revision):
    sources = (
        (
            """namespace bridge {
struct Sample {
    static double nominal_excitation;
    double\tmillivolts;
    double excitation;
};
double ratio(const Sample& sample) {
    return sample.millivolts / sample.excitation;
}
}
double bridge::Sample::nominal_excitation = 5.0;
""",
            """namespace bridge {
struct Sample {
    static double nominal_excitation;
    double\tmillivolts;
    double excitation;
    double celsius;
};
struct Calibration { double zero; double thermal; };
double ratio(const Sample& sample, const Calibration& calibration) {
    return (sample.millivolts - calibration.zero - calibration.thermal * sample.celsius) / sample.excitation;
}
}
double bridge::Sample::nominal_excitation = 5.0;
""",
        ),
        (
            """namespace encoder {
enum class Direction { Forward, Reverse };
struct Window {
    unsigned\tpulses;
    unsigned milliseconds;
};
double revolutions(const Window& window, unsigned pulsesPerTurn) {
    return static_cast<double>(window.pulses) / pulsesPerTurn;
}
}
""",
            """namespace encoder {
enum class Direction { Stopped, Forward, Reverse };
struct Window {
    long\tforward;
    long reverse;
    unsigned microseconds;
};
long displacement(const Window& window) {
    return window.forward - window.reverse;
}
Direction direction(const Window& window) {
    return displacement(window) == 0 ? Direction::Stopped :
        (displacement(window) > 0 ? Direction::Forward : Direction::Reverse);
}
}
""",
        ),
        (
            """namespace alarms {
struct Limits { double\ttrip; };
class Latch {
    bool active;
public:
    bool update(double reading, const Limits& limits) {
        active = reading >= limits.trip;
        return active;
    }
};
}
""",
            """namespace alarms {
enum class State { Clear, Tripped, Fault };
struct Limits { double\ttrip; double release; };
class Latch {
    State state = State::Clear;
public:
    State update(double reading, bool valid, const Limits& limits) {
        if (!valid) state = State::Fault;
        else if (reading >= limits.trip) state = State::Tripped;
        else if (reading <= limits.release) state = State::Clear;
        return state;
    }
    void reset() { state = State::Clear; }
};
}
""",
        ),
    )
    return {"meters.cpp":sources[index][revision]}, ["--options=NONE","--fields=+n","--sort=yes","-f","-","meters.cpp"], "stdout"


def cppcheck(index, revision):
    # Independent meter-firmware modules with maintenance-only diagnostics.
    sources = (
        (
            """/* Meter firmware: quantize the remaining cumulative pulse allowance. */
int quantized_pulses(unsigned short counted_pulses, unsigned short pulse_limit, unsigned short quantum)
{
    int reviewed_samples = 0;
    if (quantum <= 0 || counted_pulses >= pulse_limit)
        return 0;
    int remaining = pulse_limit - counted_pulses;
    return ((remaining + quantum - 1) / quantum) * quantum;
}
""",
            """/* Meter firmware: quantize the remaining cumulative pulse allowance. */
int quantized_pulses(unsigned short counted_pulses, unsigned short pulse_limit, unsigned short quantum)
{
    if (quantum <= 0 || counted_pulses >= pulse_limit)
        return 0;
    int remaining = pulse_limit - counted_pulses;
    int quanta = 0;
    quanta = remaining / quantum;
    if (remaining % quantum != 0)
        ++quanta;
    return quanta * quantum;
}
""",
        ),
        (
            """/* Meter firmware: size the sampling window in thirty-tick blocks. */
int sampling_blocks(unsigned short sample_ticks, unsigned short settle_ticks)
{
    if (sample_ticks == 0 && settle_ticks == 0)
        return 0;
    int total = sample_ticks + settle_ticks;
    int rounded = total / 30;
    if (total % 30)
        ++rounded;
    int display_ticks = total;
    return rounded;
}
""",
            """/* Meter firmware: size the sampling window in thirty-tick blocks. */
int sampling_blocks(unsigned short sample_ticks, unsigned short settle_ticks)
{
    if (sample_ticks == 0 && settle_ticks == 0)
        return 0;
    int total = sample_ticks + settle_ticks;
    if (total == 0)
        return 0;
    else if (total == 0)
        return 1;
    return (total + 29) / 30;
}
""",
        ),
        (
            """/* Meter firmware: calculate the bounded display refresh interval. */
int refresh_interval(unsigned short sample_period, unsigned short refresh_multiple, unsigned short maximum_ticks)
{
    if (sample_period <= 0 || refresh_multiple <= 0 || maximum_ticks <= 0)
        return 0;
    if (sample_period > 365 || refresh_multiple > 1000)
        return maximum_ticks;
    int interval = sample_period * refresh_multiple;
    if (interval > maximum_ticks)
        interval = maximum_ticks;
    int display_rows = 1;
    display_rows = 2;
    return interval;
}
""",
            """/* Meter firmware: calculate the bounded display refresh interval. */
int refresh_interval(unsigned short sample_period, unsigned short refresh_multiple, unsigned short maximum_ticks)
{
    if (sample_period <= 0 || refresh_multiple <= 0 || maximum_ticks <= 0)
        return 0;
    if (sample_period > 365 || refresh_multiple > 1000)
        return maximum_ticks;
    int interval = sample_period * refresh_multiple;
    int saved_interval = interval;
    if (interval > maximum_ticks)
        return maximum_ticks;
    return interval;
}
""",
        ),
    )
    args = ["--quiet", "--enable=style", "--xml", "--xml-version=2", "meter.c"]
    return {"meter.c": sources[index][revision]}, args, "stderr"


def duckdb(index, revision):
    # Independent scale extracts: missing measurements remain SQL NULL.
    extracts = (
        (
            "East,1,18\nEast,1,4\nEast,2,\nWest,1,7\nWest,2,21\nEast,3,11\n",
            "East,1,18\nEast,1,4\nEast,2,6\nWest,1,7\nWest,2,20\nEast,3,11\n",
        ),
        (
            "East,1,4\nWest,1,29\nEast,2,13\nWest,2,\nWest,3,8\nEast,4,9\n",
            "East,1,5\nWest,1,29\nEast,2,13\nWest,2,3\nWest,3,8\nEast,4,9\n",
        ),
        (
            "West,1,16\nEast,1,31\nWest,2,12\nEast,2,0\nWest,3,5\nEast,3,\nWest,4,14\n",
            "West,1,16\nEast,1,30\nWest,2,12\nEast,2,0\nWest,3,7\nEast,3,2\nWest,4,14\n",
        ),
    )
    intake = "dock,shift,kg\n" + extracts[index][revision]
    reconciliation = """WITH loads AS (SELECT * FROM read_csv('loads.csv', header=true)),
slots AS (
 SELECT d.dock, s.shift FROM (SELECT DISTINCT dock FROM loads) d
 CROSS JOIN (SELECT DISTINCT shift FROM loads) s),
weighed AS (
 SELECT dock, shift AS source_shift, sum(kg) AS measured_kg, count(kg) AS readings
 FROM loads GROUP BY dock, shift HAVING count(kg) > 0),
reconciled AS (
 SELECT slots.dock, slots.shift, weighed.source_shift, weighed.measured_kg, weighed.readings
 FROM slots ASOF LEFT JOIN weighed
 ON slots.dock = weighed.dock AND slots.shift >= weighed.source_shift)
"""
    reports = (
        """SELECT dock, shift, source_shift, measured_kg, readings
FROM reconciled ORDER BY dock, shift;
""",
        """SELECT shift, count(*) AS docks, count(source_shift) AS known_docks,
       count(CASE WHEN source_shift = shift THEN 1 END) AS weighed_this_shift,
       sum(measured_kg) AS last_known_total_kg
FROM reconciled GROUP BY shift ORDER BY shift;
""",
        """SELECT dock, shift, source_shift, measured_kg,
       CASE WHEN source_shift = shift THEN 'measured'
            WHEN source_shift IS NULL THEN 'unavailable' ELSE 'carried' END AS basis
FROM reconciled ORDER BY dock, shift;
""",
    )
    query = reconciliation + reports[index]
    return {"ledger.sql":query, "loads.csv":intake}, ["-csv","-batch",":memory:"], "stdout"


def lnav(index, revision):
    # Synthetic gateway extracts, grouped here only to keep the fixture compact.
    # Each tuple is an observed service path, HTTP status and request count.
    extracts = (
        ((("/api/levels", 200, 3), ("/assets/tide-chart.css", 304, 2), ("/reports/daily", 404, 1)),
         (("/api/levels", 200, 2), ("/api/levels", 503, 1), ("/reports/daily", 200, 4))),
        ((("/api/weather", 200, 4), ("/status", 200, 1), ("/assets/wind.svg", 304, 2)),
         (("/api/weather", 504, 2), ("/status", 200, 3), ("/assets/wind.svg", 200, 1))),
        ((("/schedule/locks", 200, 2), ("/api/water-quality", 502, 1), ("/assets/map.css", 304, 3)),
         (("/schedule/locks", 404, 1), ("/api/water-quality", 200, 4), ("/assets/map.css", 200, 2))),
    )
    lines = []
    for route, status, count in extracts[index][revision]:
        for _ in range(count):
            n = len(lines)
            lines.append(f'127.0.0.1 - - [20/Nov/2025:08:30:{n:02d} +0000] "GET {route} HTTP/1.1" {status} {50 + n}')
    # The second export begins with the boundary event retained at rotation.
    cut = len(lines) // 2
    files = {
        "opening.log": "\n".join(lines[:cut + 1]) + "\n",
        "closing.log": "\n".join(lines[cut:]) + "\n",
    }
    query = """WITH events AS MATERIALIZED (
  SELECT log_line, log_path, log_raw_text, cs_uri_stem, sc_status FROM access_log
), opening_tail AS (
  SELECT log_raw_text FROM events WHERE substr(log_path, -11) = 'opening.log' ORDER BY log_line DESC LIMIT 1
), closing_head AS (
  SELECT log_line, log_raw_text FROM events WHERE substr(log_path, -11) = 'closing.log' ORDER BY log_line LIMIT 1
)
SELECT cs_uri_stem AS route, sc_status AS status, count(*) AS requests
FROM events WHERE log_line NOT IN (
  SELECT closing_head.log_line FROM closing_head JOIN opening_tail USING (log_raw_text)
)
GROUP BY 1,2 ORDER BY 1,2"""
    args = ["-n", "-q", "-c", ";" + query, "-c", ":write-csv-to -", "opening.log", "closing.log"]
    return files, args, "stdout"


def chafa(index, revision):
    w, h = 24, 12
    cut, split = 5 + index * 3 + revision * 7, 5 + index
    source = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
              f'<rect width="{w}" height="{h}" fill="black"/>'
              f'<rect width="{cut}" height="{split}" fill="white"/>'
              f'<rect x="{cut}" y="{split}" width="{w-cut}" height="{h-split}" fill="white"/></svg>\n')
    args = ["--format=symbols","--colors=none","--symbols=ascii","--size=12x6","--stretch","panel.svg"]
    return {"panel.svg":source}, args, "stdout"


# Independent synthetic instrument acquisition records: (position, MAPQ, flag).
# Coordinates refer only to an abstract calibration target; every base is N.
SAM_CALIBRATION_RUNS = (
    (
        ((41,31,0),(79,8,16),(126,22,1024),(205,19,0),(318,55,256)),
        ((44,29,16),(91,20,0),(142,6,0),(227,47,1024),(355,18,256),(488,36,2048)),
    ),
    (
        ((63,4,0),(107,42,16),(189,26,256),(293,21,0),(412,17,1024),(576,60,0),(701,33,2048)),
        ((52,11,16),(173,39,0),(367,2,1024),(609,24,256)),
    ),
    (
        ((28,20,0),(118,7,256),(254,44,16),(399,12,0),(538,27,1024),(866,51,2048)),
        ((36,23,1024),(146,48,0),(278,3,16),(431,30,256),(587,21,0),(745,16,0),(923,57,2048),(1114,35,16)),
    ),
)


def samtools(index, revision):
    lines = ["@HD\tVN:1.6\tSO:coordinate", "@SQ\tSN:calibration\tLN:2000"]
    for n, (position, quality, flag) in enumerate(SAM_CALIBRATION_RUNS[index][revision]):
        fields = [f"f{index+1}-{n+1}", flag, "calibration", position, quality, "8M", "*", 0, 0, "NNNNNNNN", "IIIIIIII"]
        lines.append("\t".join(map(str, fields)))
    return {"synthetic.sam":"\n".join(lines)+"\n"}, ["view","-h","--no-PG","-q","20","synthetic.sam"], "stdout"


WORKLOADS = {
    "gromacs": (gromacs, "Restore the molecular-simulation preprocessing station. Its calibration archive contains periodic argon configurations.", "centered lattice configuration"),
    "php": (php, "Restore the PHP runtime used by the port authority's capacity reports.", "dock capacity report"),
    "pandoc": (pandoc, "The field survey service needs its booked reports for offline use and a replacement document converter.", "self-contained HTML report with its issued calibration diagram embedded"),
    "doxygen": (doxygen, "Restore the documentation builder used to publish the instrument library's public interfaces.", "interface tag file"),
    "ctags": (ctags, "Restore the source-indexing service used by the metering firmware archive.", "symbol index"),
    "cppcheck": (cppcheck, "Restore the C diagnostics tool used at the meter firmware release desk.", "diagnostics record"),
    "duckdb": (duckdb, "The dock desk needs its booked load ledgers and a replacement SQL terminal.", "ordered ledger extract"),
    "lnav": (lnav, "Restore the log analysis terminal used to prepare gateway traffic returns.", "traffic return"),
    "chafa": (chafa, "Restore the terminal image renderer used to publish field panel previews.", "monochrome terminal preview"),
    "samtools": (samtools, "Restore the alignment tool used to check sequencing instrument calibration runs. The calibration reads are synthetic.", "quality-filtered SAM file"),
}


def workload(family, index, revision):
    files, argv, product = WORKLOADS[family][0](index, revision)
    return dict(files=files, argv=argv, product=product, stdin="ledger.sql" if family == "duckdb" else None)
