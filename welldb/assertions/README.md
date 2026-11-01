# Proof values of the well logs in OSDU

The flows in this folder check that what OSDU holds of the well logs is what the estate's source files say it should be.
They only read OSDU: nothing is written.

| Folder | What it holds |
| --- | --- |
| `wellbores/` | One assertion flow per wellbore. Each test is one log of the wellbore (by project and log name), and each row of a test is one curve of that log, with the row of the curve file it came from. |
| `key-numbers/` | The counts per project: distinct wellbores, curves and curve mnemonics. |
| `gen_assertions.py` | Writes both folders from the source files: `python -I gen_assertions.py`. Edit the generator, not the flows, and review the diff. |

## How a row finds its record

The source files name no OSDU id, so each row is located by full paths and values (`locateBy`), and is then held to its
proof values (`check`), each a full path and the value the record has to hold.

Every path is a path in the OSDU record, written as the estate's other assertion flows, mappings and dimensions write
one: `data.Name` is the `Name` in the WellLog's `data` block, the property `mappings/WellLog@1.4.0.yaml` writes under
`record: data:`, and `tags.SourceProject` is one of the record's tags. These flows read only OSDU, so no path is a column
of a source file.

```yaml
knownValues:
  locateBy:
    '[data.WellboreID, data.FacilityName]': "Wellbore A-1"   # the log's wellbore, by the wellbore's name
    tags.SourceProject: PROJECT_A                            # the project
    data.Name: COMPOSITE                                     # the log name
  rows:
    - locateBy:
        data.Curves.CurveID: DT                              # the curve inside the log
      check:
        data.Curves.CurveUnit: "{partition}:reference-data--UnitOfMeasure:us%2Fft:"
        data.Curves.TopDepth: { equals: 2128.7232, tolerance: 0.0005 }
```

- A WellLog does not hold its wellbore's name, so the list `[data.WellboreID, data.FacilityName]` follows the log's
  reference to its wellbore and reads the name there, as a dimension's label and attributes read through a reference
  (`flows/welldb-welllog-05-dimensions.yaml`). A list is quoted, since YAML would read an unquoted `[` as a list.
- A row located by `data.Curves.CurveID` is one curve, and every proof value under `data.Curves` is read from that curve.
- A row whose log or curve is not in OSDU fails the test, saying which path did not find it. A row that finds two logs (a
  wellbore delivered twice, say) fails as found more than once, naming both.
- Each test checks the log's own values once and the curves row by row.

The engine side of this is the `knownValues` assertion of OSDU Delivery's assertion flow; its reference page,
`osdu/docs/reference/flow/known-values.md`, has every key.

## From the source files to a full path

| Source column | Full path in the WellLog | How the value is written |
| --- | --- | --- |
| `wellbore_uwi` | `[data.WellboreID, data.FacilityName]` | as it is (locates) |
| `source_project` | `tags.SourceProject` | as it is (locates) |
| `log_source` | `data.Name` | as it is (locates) |
| `curve_id` | `data.Curves.CurveID` | as it is (locates) |
| `curve_unit` | `data.Curves.CurveUnit` | the unit reference WellLog@1.4.0 writes, through the unit table: `US/F` is `{partition}:reference-data--UnitOfMeasure:us%2Fft:` |
| `index_unit` | `data.Curves.DepthUnit` | the unit reference, through the depth unit table |
| curve `index_min`, `index_max` | `data.Curves.TopDepth`, `data.Curves.BaseDepth` | number, within 0.0005 |
| `curve_description` | `data.Curves.CurveDescription` | as it is |
| `business_value` | `data.Curves.LogCurveBusinessValueID` | `HIGH` is `{partition}:reference-data--LogCurveBusinessValue:High:` |
| `curve_id`, through the curve dictionary | `data.Curves.LogCurveTypeID`, `LogCurveMainFamilyID`, `LogCurveFamilyID` | the references the dictionary's codes build |
| `elev_meas_ref` | `data.VerticalMeasurement.VerticalMeasurement`, `VerticalMeasurementUnitOfMeasureID` | the number and the unit reference: `42.8 M` is `42.8` and `m` |
| `logs_meas_from` | `data.VerticalMeasurement.VerticalMeasurementTypeID` | `KB` is `{partition}:reference-data--VerticalMeasurementType:KellyBushing:` |
| log `index_min`, `index_max`, `index_increment` | `data.SamplingStart`, `data.SamplingStop`, `data.SamplingInterval` | number; the two depths within 0.0005 |
| `data_type` | `data.WellLogTypeID` | `INTERPRETED` is `{partition}:reference-data--LogType:Interpreted:` |
| `index_type` | `data.SamplingDomainTypeID` | `DEPTH` is `{partition}:reference-data--WellLogSamplingDomainType:Depth:` |
| `log_run`, `welldb_log_source`, `creator`, `log_service`, `log_pass` | `data.LogRun`, `data.LogSource`, `data.Source`, `data.ActivityType`, `data.LogActivity` | as it is |
| `depth_coding` | `data.IsRegular` | `REGULAR` is `true` |

A depth is compared within half a millimetre (`tolerance: 0.0005`).

Each log also has a `-samples` test of its curve values, which reads its bulk data back from the Wellbore DDMS and holds it
to its parquet curve file: the row count, the exact columns, a depth that only increases, and each curve's count and sum.
One sample changed anywhere fails it, however little it moved. A row of `curves-meta` is what a curve says about itself;
this is what the curve holds.

Not checked: the source's own unit spelling, which WellLog@1.4.0 keeps at
`data.ExtensionProperties.WellDb.Curves[].OriginalUnit`, and the curve values themselves, which
`flows/welldb-welllog-04-header-assertion.yaml` reads from the Wellbore DDMS.

### Key numbers

Each project is a test of the logs with that `tags.SourceProject` and the log names the source file gives, read from the
search index:

| Key number | Assertion |
| --- | --- |
| Wellbores | `aggregate: distinct` of `data.WellboreID` |
| Curves | `aggregate: count` of `data.Curves.CurveID`, `except: [MD]` |
| Unique curves | `aggregate: distinct` of `data.Curves.CurveID`, `except: [MD]` |

The curve file lists the index curve `MD` on every log, and these counts leave it out.

## Independent of the delivery

The flows read only what OSDU holds, whichever pipeline delivered it, and name no template or mapping: each test is
checked against the schema of its kind as captured from OSDU (the newest capture,
`sqlflow template capture --kind osdu:wks:work-product-component--WellLog:1.4.0` where none is). A log is found by its
wellbore's name, its `tags.SourceProject` and its log name.

## Running, disabling, dating

Every flow here joins the schedule `welldb-welllog-assertions` (`../schedules.yaml`): daily at 07:00 UTC, on its own clock
rather than after a delivery, since the flows check what OSDU holds whichever pipeline delivered it. "Run now" on the
Schedules page runs all of them; a single flow or test runs on its own as below.

```bash
sqlflow run welldb/assertions/wellbores/wellbore-a-1.yaml --set partition=dev
sqlflow run welldb/assertions/wellbores/wellbore-a-1.yaml --set partition=dev --payload '{"tests":["composite"]}'
sqlflow run welldb/assertions/key-numbers/welldb-key-numbers.yaml --set partition=dev --payload '{"tags":["project-a"]}'
```

Or from the Assertions page, where every run keeps a report (HTML, Markdown, JSON or JUnit).

- **Disable** a test, an assertion, a row or a single proof value with `disabled: <why>`. It stays in the flow and in every
  report, skipped with that reason, and does not fail the run.
- **Date** proof values: `asOf: 2026-10-13` says the day they were stated (every result quotes it beside what it expected)
  and `validFor: 90d` (or `12w`, `6m`, `1y`, or a fixed `validUntil: 2026-12-31`) how long they hold. Past that the test
  is not judged and is flagged instead: a warning, "needs new proof values", on the board and in the report. Regenerating
  with `--as-of` and `--valid-for` dates every test.
- **Numbers a little off.** `warnWithin: 10%` (or a distance, `warnWithin: 5`) beside a count, an aggregate or a proof
  value makes a miss of no more than that a warning rather than a failure. This estate's counts are exact, so none is set.
