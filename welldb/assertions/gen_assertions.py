"""Generates the assertion flows of welldb/assertions from the estate's own source files.

One flow per wellbore (data/welllog), each test one log of it, each row of a test one curve of the log (data/curves-meta),
and one flow of the counts per project. Every proof value is a full path into the WellLog record WellLog@1.4.0 renders and
the value that record has to hold, reached from the source file by the same translations the mapping makes: the unit
tables (cache/data/unit-alias, cache/data/depth-unit-alias), the curve dictionary (cache/data/curve-dictionary) and the
one-entry maps kept beside its properties.

Usage: python -I gen_assertions.py [--as-of DAY] [--valid-for PERIOD]

  --as-of, --valid-for   the day the proof values were stated and how long they hold (90d, 12w, 6m, 1y). The source files
                         give no date for them, so the flows are dated only when these say so.

Run it from this folder after a change to the data, then review the diff. It needs nothing but Python.
"""
import argparse
import csv
import glob
import os
import re
import sys
from collections import OrderedDict

import pyarrow.parquet as parquet

HERE = os.path.dirname(os.path.abspath(__file__))
WELLDB = os.path.dirname(HERE)

arguments = argparse.ArgumentParser(description="Generates the assertion flows from the estate's source files.")
arguments.add_argument("--as-of", dest="as_of")
arguments.add_argument("--valid-for", dest="valid_for")
ARGS = arguments.parse_args()
if ARGS.valid_for and not ARGS.as_of:
    sys.exit("--valid-for counts from --as-of; give both.")

KIND = "osdu:wks:work-product-component--WellLog:1.4.0"
# Every flow it writes joins this schedule (../schedules.yaml): once a day, on its own clock rather than after a delivery,
# since the flows check what OSDU holds whichever pipeline delivered it.
SCHEDULE = "welldb-welllog-assertions"

# No test names a template: each is checked against the schema of its kind as captured from OSDU, the newest captured,
# so the tests depend on nothing but OSDU, whichever pipeline delivered the logs.

# The one-entry maps WellLog@1.4.0 keeps beside the properties that use them.
LOG_TYPES = {"INTERPRETED": "Interpreted"}
DOMAINS = {"DEPTH": "Depth"}
BUSINESS_VALUES = {"HIGH": "High"}
VERTICAL_TYPES = {"KB": "KellyBushing"}


def rows_of(folder):
    """The one CSV file of a folder under welldb, with its name and each row's line number in it."""
    files = glob.glob(os.path.join(WELLDB, *folder.split("/"), "*.csv"))
    if len(files) != 1:
        sys.exit(f"{folder} holds {len(files)} CSV files; it should hold one.")
    with open(files[0], encoding="utf-8", newline="") as f:
        return os.path.basename(files[0]), [(n, row) for n, row in enumerate(csv.DictReader(f), start=2)]


def id_segment(value):
    """A value as an OSDU id's code segment carries it (SqlFlow.Delivery.Identity.IdSegment, keeping escapes)."""
    out = []
    i = 0
    while i < len(value):
        c = value[i]
        if c.isascii() and (c.isalnum() or c in "_-.:"):
            out.append(c)
        elif c == "%" and re.fullmatch(r"[0-9A-Fa-f]{2}", value[i + 1:i + 3] or ""):
            out.append("%" + value[i + 1:i + 3].upper())
            i += 2
        else:
            out.extend("%{:02X}".format(b) for b in c.encode("utf-8"))
        i += 1
    return "".join(out)


def reference(entity, code):
    return "{partition}:reference-data--" + entity + ":" + id_segment(code) + ":"


def text(value):
    """Text as YAML reads it back unchanged: double-quoted when anything would change it."""
    s = str(value)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", s) and s.lower() not in ("true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def slug(name):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def ranges(numbers):
    """Rows as a reader takes them in: runs of rows as 2 to 11, the rest one by one."""
    numbers = sorted(numbers)
    parts, start = [], None
    for i, n in enumerate(numbers):
        if start is None:
            start = n
        if i + 1 == len(numbers) or numbers[i + 1] != n + 1:
            parts.append(str(start) if start == n else f"{start} to {n}")
            start = None
    return ", ".join(parts)


def first(value, separator):
    """The split modifier's part 1."""
    return value.split(separator)[0].strip()


def depth(value):
    """A depth, compared within half a millimetre."""
    return "{ equals: " + value + ", tolerance: 0.0005 }" if "." in value else value


LOG_FILE, LOGS = rows_of("data/welllog")
CURVE_FILE, CURVES = rows_of("data/curves-meta")
UNITS = {row["source_unit"]: row["osdu_unit"] for _, row in rows_of("cache/data/unit-alias")[1]}
DEPTH_UNITS = {row["source_unit"]: row["osdu_unit"] for _, row in rows_of("cache/data/depth-unit-alias")[1]}
DICTIONARY = {row["mnemonic"]: row for _, row in rows_of("cache/data/curve-dictionary")[1]}

curves_of = OrderedDict()
for n, row in CURVES:
    curves_of.setdefault((row["source_project"], row["log_id"]), []).append((n, row))

wellbores = OrderedDict()
for n, row in LOGS:
    wellbores.setdefault(row["wellbore_uwi"], []).append((n, row))


def log_checks(log):
    """The log's own values, as WellLog@1.4.0 writes them."""
    return OrderedDict([
        ("data.VerticalMeasurement.VerticalMeasurement", first(log["elev_meas_ref"], " ")),
        ("data.VerticalMeasurement.VerticalMeasurementUnitOfMeasureID", text(reference("UnitOfMeasure", DEPTH_UNITS[log["elev_meas_ref"].split(" ")[1]]))),
        ("data.VerticalMeasurement.VerticalMeasurementTypeID", text(reference("VerticalMeasurementType", VERTICAL_TYPES[log["logs_meas_from"]]))),
        ("data.SamplingStart", depth(log["index_min"])),
        ("data.SamplingStop", depth(log["index_max"])),
        ("data.SamplingInterval", log["index_increment"]),
        ("data.ReferenceCurveID", "MD"),
        ("data.WellLogTypeID", text(reference("LogType", LOG_TYPES[log["data_type"]]))),
        ("data.SamplingDomainTypeID", text(reference("WellLogSamplingDomainType", DOMAINS[log["index_type"]]))),
        ("data.LogRun", text(log["log_run"])),
        ("data.LogSource", text(log["welldb_log_source"])),
        ("data.Source", text(log["creator"])),
        ("data.ActivityType", text(log["log_service"])),
        ("data.LogActivity", text(first(log["log_pass"], ","))),
        ("data.IsRegular", "true" if log["depth_coding"] == "REGULAR" else "false"),
    ])


def curve_file_of(log):
    """The columns of a log's curve file, in order, each with its values: the samples OSDU has to hold."""
    folder = os.path.join(WELLDB, "data", "curves", log["source_project"], log["log_id"].replace("/", "_"))
    table = parquet.read_table(os.path.join(folder, "chunk_00000.parquet"))
    return OrderedDict((name, table.column(name).to_pylist()) for name in table.column_names)


def sample_assertions(log):
    """The log's bulk data, held to its curve file: its rows, its columns, an index that only increases, and each curve's
    count and sum, so one sample changed anywhere fails the test, whichever curve it is in and however little it moved."""
    curves = curve_file_of(log)
    rows = len(next(iter(curves.values())))
    lines = [
        f"      - rowCount: {rows}",
        "      - columns: { equals: [" + ", ".join(curves) + "] }",
        "      - column: MD",
        "        monotonic: strictlyIncreasing",
    ]
    for name, values in curves.items():
        held = [v for v in values if v is not None and v == v]
        lines.append(f"      - {{ aggregate: count, column: {name}, equals: {len(held)} }}")
        lines.append(f"      - {{ aggregate: sum, column: {name}, equals: {round(sum(held), 4)}, tolerance: 0.001 }}")
    return lines


def curve_checks(curve):
    """A curve's own values, as WellLog@1.4.0 writes them."""
    checks = OrderedDict([
        ("data.Curves.CurveUnit", text(reference("UnitOfMeasure", UNITS[curve["curve_unit"]]))),
        ("data.Curves.DepthUnit", text(reference("UnitOfMeasure", DEPTH_UNITS[curve["index_unit"]]))),
        ("data.Curves.TopDepth", depth(curve["index_min"])),
        ("data.Curves.BaseDepth", depth(curve["index_max"])),
        ("data.Curves.CurveDescription", text(curve["curve_description"])),
    ])
    if curve["business_value"]:
        checks["data.Curves.LogCurveBusinessValueID"] = text(reference("LogCurveBusinessValue", BUSINESS_VALUES[curve["business_value"]]))
    known = DICTIONARY.get(curve["curve_id"])
    if known:
        checks["data.Curves.LogCurveTypeID"] = text(reference("LogCurveType", known["log_curve_type_id"]))
        checks["data.Curves.LogCurveMainFamilyID"] = text(reference("LogCurveMainFamily", known["log_curve_main_family_id"]))
        checks["data.Curves.LogCurveFamilyID"] = text(reference("LogCurveFamily", known["log_curve_family_id"]))
    return checks


SOURCE_BLOCK = """source:
  # The platform and credentials the delivery flows deliver with.
  endpoint: ${env:OSDU_URL}
  auth:
    type: oauth2ClientCredentials
    secondarySecretRef: ${env:OSDU_CLIENT_ID}
    secretRef: ${env:OSDU_CLIENT_SECRET}
    token:
      url: ${env:OSDU_TOKEN_URL}
      body:
        scope: ${env:OSDU_SCOPE}

reliability:
  retry: { attempts: 4, backoff: exponential, baseDelayMs: 500, maxDelayMs: 30000 }
  timeoutSeconds: 100

parallelism:
  recordsAtOnce: 4
"""

os.makedirs(os.path.join(HERE, "wellbores"), exist_ok=True)
os.makedirs(os.path.join(HERE, "key-numbers"), exist_ok=True)
written = []


def dated():
    return ([f"    asOf: {ARGS.as_of}"] if ARGS.as_of else []) + ([f"    validFor: {ARGS.valid_for}"] if ARGS.valid_for else [])


for wellbore, logs in wellbores.items():
    name = "welldb-welllog-assertion-" + slug(wellbore)
    log_rows = [n for n, _ in logs]
    lines = [
        f"# Flow: {name}",
        "#",
        f"# Proof values of wellbore {wellbore}: what OSDU has to hold for its logs, from the estate's own source files",
        f"# ({LOG_FILE}, row {ranges(log_rows)}, and the rows of {CURVE_FILE} each test names).",
        "#",
        "# Each test is one of its logs, by project and log name; each row of a test is one curve of that log, and says which",
        "# row of the curve file it is. A row finds its record by full paths (locateBy): the log is the WellLog whose",
        "# data.WellboreID names the wellbore of that name ('[data.WellboreID, data.FacilityName]', read through the reference as",
        "# a dimension label is), of that project (tags.SourceProject) and log name (data.Name), and the curve is the item of",
        "# data.Curves with that mnemonic. Its proof values (check) are full paths into the record WellLog@1.4.0 renders, each",
        "# with the value that record holds; every proof value of a curve is read from that one curve. Units, log types,",
        "# sampling domains, business values and curve families are the references WellLog@1.4.0 writes for the source's words",
        "# (the unit US/F is {partition}:reference-data--UnitOfMeasure:us%2Fft:). A depth is compared within half a millimetre.",
        "#",
        "# Each log also has a test of its samples: its bulk data, read back from the Wellbore DDMS, is held to its parquet curve",
        "# file by its rows, its columns, an index that only increases, and each curve's count and sum, so a sample changed",
        "# anywhere fails the test, however little it moved.",
        "#",
        "# A row whose log or curve OSDU does not hold fails the test, saying by which path it was not found. A test, an assertion,",
        "# a row or a proof value takes disabled: <why> to stay in the flow, reported as skipped, without failing the run. A test",
        "# that says when its proof values were stated (asOf) and how long they hold (validFor: 180d) is flagged past that, a",
        "# warning that it needs new proof values, rather than judged.",
        "#",
        f"# Written by gen_assertions.py from the source files. It joins the schedule {SCHEDULE} (../../schedules.yaml),",
        "# which runs every flow of assertions once a day. The flow, or one of its assertions, also runs on its own from the",
        "# Assertions page, or",
        f"#   sqlflow run {name}.yaml",
        "flowType: assertion",
        f"name: {name}",
        f"description: {text('Proof values of wellbore ' + wellbore + ' from the source files, held to what OSDU holds of its logs.')}",
        "batch: welldb",
        "",
        "# The partition the delivery flows deliver to.",
        "partitions: [dev]",
        "",
        f"schedule: {SCHEDULE}",
        "",
        SOURCE_BLOCK.rstrip(),
        "",
        "defaults:",
        "  examples: 100",
        "  read: storage",
        "",
        "# A failed or errored test fails the run, so a schedule's notifications would say so.",
        "failRunOn: error",
        "",
        "tests:",
    ]
    for _, log in logs:
        project, log_name = log["source_project"], log["log_source"]
        rows = curves_of[(project, log["log_id"])]
        locate = OrderedDict([
            ("'[data.WellboreID, data.FacilityName]'", text(wellbore)),
            ("tags.SourceProject", text(project)),
            ("data.Name", text(log_name)),
        ])
        about = f"The {log_name} log of {wellbore} in project {project}: log " + log["log_id"] + f", rows {ranges([n for n, _ in rows])} of the curve file."
        lines += [
            f"  - name: {slug(log_name)}",
            f"    description: {text(about)}",
            f"    tags: [welldb, {slug(log_name)}]",
            f"    kind: {KIND}",
        ] + dated() + [
            "    assert:",
            f"      - name: the {log_name} log of {wellbore}",
            "        knownValues:",
            "          locateBy:",
        ]
        lines += [f"            {p}: {v}" for p, v in locate.items()]
        lines.append("          check:")
        lines += [f"            {p}: {v}" for p, v in log_checks(log).items()]
        lines += [
            f"      - name: the curves of the {log_name} log of {wellbore}",
            "        knownValues:",
            "          locateBy:",
        ]
        lines += [f"            {p}: {v}" for p, v in locate.items()]
        lines.append("          rows:")
        for n, curve in rows:
            lines += [
                f"            # Row {n} of {CURVE_FILE}.",
                "            - locateBy:",
                f"                data.Curves.CurveID: {text(curve['curve_id'])}",
                "              check:",
            ]
            lines += [f"                {p}: {v}" for p, v in curve_checks(curve).items()]
        lines += [
            f"  - name: {slug(log_name)}-samples",
            f"    description: {text('Every curve sample of log ' + log['log_id'] + ', from its curve file.')}",
            f"    tags: [welldb, {slug(log_name)}, bulk]",
            f"    kind: {KIND}",
            f"    query: 'tags.WellLogNativeUID:\"{log['log_id']}\"'",
            "    bulk: { maxRows: 100000 }",
        ] + dated() + ["    assert:"] + sample_assertions(log)
    path = os.path.join(HERE, "wellbores", slug(wellbore) + ".yaml")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    written.append(path)


# --- The key numbers ---------------------------------------------------------------------------------------------------------
def count_assertions(project):
    logs = [row for _, row in LOGS if row["source_project"] == project]
    curves = [row for (p, _), group in curves_of.items() if p == project for _, row in group if row["curve_id"] != "MD"]
    rows = [
        ("distinct", "data.WellboreID", len({log["wellbore_uwi"] for log in logs}), "wellbore(s)", False),
        ("count", "data.Curves.CurveID", len(curves), "curve(s), the index curve MD aside", True),
        ("distinct", "data.Curves.CurveID", len({curve["curve_id"] for curve in curves}), "distinct curve mnemonic(s), the index curve MD aside", True),
    ]
    out = []
    for function, field, value, noun, except_md in rows:
        out += [
            f"      - name: {value} {noun}",
            f"        aggregate: {function}",
            f"        field: {field}",
        ]
        if except_md:
            out.append("        except: [MD]")
        out.append(f"        equals: {value}")
    return out


name = "welldb-welllog-assertion-key-numbers"
lines = [
    f"# Flow: {name}",
    "#",
    "# Counts of the well logs per project, from the estate's own source files, held to what OSDU holds: the distinct",
    "# wellbores of the logs, their curves and their distinct curve mnemonics, read from the search index. The source files",
    "# count the index curve MD as a curve of every log, so the curve counts leave it out (except: [MD]).",
    "#",
    "# A count that changes as the source does takes asOf and validFor: past that the test is not judged and is flagged as",
    "# needing new proof values. warnWithin: 10% makes a count within 10% of what is stated a warning rather than a failure,",
    "# and atLeast in place of equals holds a count that only grows. This estate's counts are exact, so none of them is set.",
    "#",
    f"# Written by gen_assertions.py from the source files. It joins the schedule {SCHEDULE} (../../schedules.yaml), which",
    "# runs every flow of assertions once a day.",
    "flowType: assertion",
    f"name: {name}",
    "description: Counts of the well logs per project from the source files, held to what OSDU holds.",
    "batch: welldb",
    "",
    "# The partition the delivery flows deliver to.",
    "partitions: [dev]",
    "",
    f"schedule: {SCHEDULE}",
    "",
    SOURCE_BLOCK.rstrip(),
    "",
    "defaults:",
    "  read: index",
    "  maxRecords: 1000",
    "",
    "failRunOn: error",
    "",
    "tests:",
]
projects = OrderedDict()
for _, row in LOGS:
    projects.setdefault(row["source_project"], OrderedDict())[row["log_source"]] = True
for project, names in projects.items():
    logs = list(names)
    wanted = '"' + logs[0] + '"' if len(logs) == 1 else "(" + " OR ".join('"' + n + '"' for n in logs) + ")"
    lines += [
        f"  - name: {slug(project)}",
        f"    description: {text('The ' + ', '.join(logs) + ' logs of project ' + project + '.')}",
        f"    tags: [key-numbers, {slug(project)}]",
        f"    kind: {KIND}",
        f"    query: 'tags.SourceProject:\"{project}\" AND data.Name.keyword:{wanted}'",
    ] + dated() + ["    assert:"] + count_assertions(project)
path = os.path.join(HERE, "key-numbers", "welldb-key-numbers.yaml")
with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
written.append(path)

for p in written:
    print(os.path.relpath(p, HERE))
