# OSDU Delivery sample estate

A complete, working example of a flow repository for [OSDU Delivery](https://github.com/TahirRiaz/osdu-delivery): a small,
made-up well database (WellDB) delivered into an OSDU partition, from reference data to well logs, with every record
traceable and every delivered value checked against what OSDU holds.

**Everything here is synthetic.** The wells, wellbores, logs and curve values are generated from a seed by OSDU Delivery's
`SampleData` tool. Nothing comes from a real well, a real company or a real database. The reference values for units
and curve families are OSDU's own, as the OSDU data definitions publish them.

## The dataset

| Well | Wellbore | Log | Curves besides the index curve MD | Interval (m MD) |
| --- | --- | --- | --- | --- |
| Well A | Wellbore A-1 | `LOG-0001/1` | BS, CALI, DRHO, DT, DTS, GR, NPHI, RD, RHOB | 2127.50 to 2183.59 |
| Well B | Wellbore B-1 | `LOG-0002/1` | DRHO, GR, NPHI, PEF, RD, RHOB | 1865.38 to 1925.12 |
| Well B | Wellbore B-2 A | `LOG-0003/1` | GR, RD | 1787.96 to 1826.36 |
| Well B | Wellbore B-2 B | `LOG-0004/1` | GR, RD | 1945.23 to 1970.38 |
| Well C | Wellbore C-1 | `LOG-0005/1` | GR, RD | 1660.55 to 1680.97 |

That is 3 wells, 5 wellbores (B-2 A and B-2 B are sidetracks of one slot) and 5 `COMPOSITE` logs of project `PROJECT_A`,
each with its curve values in a parquet chunk, plus a directional survey and a set of formation tops per wellbore.

Every reference a record makes names a record this repository delivers, so it fills an empty partition.

## What is in the repository

Each top-level folder is one source.

| Folder | What it delivers |
| --- | --- |
| [welldb/](welldb/) | The reference data, wells, wellbores, well logs, surveys and formation tops, with the flows of every kind that read them back |
| [LogType/](LogType/) | A curated reference data set, maintained as a CSV file and delivered through storage |

Inside `welldb/`:

| Part | What it shows |
| --- | --- |
| `reference/` | Reference values delivered one interface per kind, in the order their references need |
| `flows/` | The pre-ingestion, ingestion and delivery chain of each kind, and the assertion, dimension, inventory, retrieval, download and removal flows |
| `mappings/`, `templates/` | One mapping per kind, and the OSDU schema each one fills |
| `cache/`, `dictionaries/` | The lookup tables and reference data a mapping translates through |
| `assertions/` | Proof values: one assertion flow per wellbore and the key numbers, generated from the source files ([its README](welldb/assertions/README.md)) |

The same logs go out three ways, to show what changes and what does not:

- `welldb-welllog-03-header-delivery`: WellLog 1.4.0 through the Wellbore DDMS, the curves as bulk data.
- `welldb-welllog-03-header-delivery-v150`: the same rows as WellLog 1.5.0, a second version of the schema.
- `welldb-welllog-03-header-delivery-welldbwelllog`: a custom kind, `welldb:wks:work-product-component--WellDbWellLog:1.0.0`,
  linked to its WellLog parent and sharing its curve files. Its schedule stays disabled until you register the kind with
  OSDU's schema service, since the indexer does not index a kind the schema service does not hold.

## Running it

You need a SQL Server and an OSDU partition you can write to. OSDU Delivery's
[run locally](https://github.com/TahirRiaz/osdu-delivery/blob/main/osdu/docs/reference/guides/run-locally.md) guide sets a
machine up with both.

1. Register this repository as a flow repository.
2. Register the partition. The flows name `dev`; to use another, change `partitions` in the flows.
3. Set the values the flows reference. A flow never holds a secret, only these references:

   | Value | What it is |
   | --- | --- |
   | `OSDU_URL`, `OSDU_TOKEN_URL`, `OSDU_SCOPE` | The OSDU platform and its token endpoint |
   | `OSDU_CLIENT_ID`, `OSDU_CLIENT_SECRET` | The client the flows sign in with |
   | `OSDU_ACL_OWNER`, `OSDU_ACL_VIEWER` | The entitlements groups the records carry |
   | `OSDU_LOGTYPE_ACL_OWNER`, `OSDU_LOGTYPE_ACL_VIEWER` | The groups the curated reference data carries |
   | `OSDU_LEGAL_TAG` | The legal tag the records carry |
   | `OSDU_DATA_DB` | The database of the source tables, named `OsduData` in the flows |
   | `SQLFLOW_CATALOG_DB` | OSDU Delivery's own database, named `OsduDelivery` by the curve table flow |

4. Run the schedules, from the Schedules page or `sqlflow`:

   | Schedule | What it runs |
   | --- | --- |
   | `welldb-cache` | The lookup tables, and a refresh of the partition's reference data |
   | `welldb-reference` | The reference values |
   | `welldb-master` | After `welldb-reference`: wells, wellbores, surveys and formation tops |
   | `sqlflow-logtype` | The curated log types |
   | `welldb-welllog` | The well logs, as WellLog 1.4.0 |
   | `welldb-welllog-v150` | The well logs, as WellLog 1.5.0 |
   | `welldb-dimensions` | After `welldb-welllog`: the dimensions and the curve table |
   | `welldb-welllog-assertions` | The proof values, held to what OSDU holds |
   | `welldb-inventory`, `welldb-removal` | What OSDU holds set against the ledgers, and the wellbores the source no longer holds |

To look at one flow before sending anything:

```bash
sqlflow validate .
sqlflow check   welldb/flows/welldb-welllog-03-header-delivery.yaml --set logSource=COMPOSITE
sqlflow preview welldb/flows/welldb-welllog-03-header-delivery.yaml --set logSource=COMPOSITE
sqlflow run     welldb/flows/welldb-welllog-03-header-delivery.yaml --set logSource=COMPOSITE --operation plan
```

`validate` checks the documents, `check` the flow, its mapping and its schema, `preview` builds one record without sending
it, and `plan` shows what a run would send.

Comments in the flows that name a path under `osdu/docs` point into the
[OSDU Delivery repository](https://github.com/TahirRiaz/osdu-delivery), where the reference pages live.

## License

GPL-3.0, as [LICENSE](LICENSE) gives it. The OSDU schemas in the `templates` folders are The Open Group's, under the Apache
License 2.0 each file names.
