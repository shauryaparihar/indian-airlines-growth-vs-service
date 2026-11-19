# Local PySpark analysis: market share and concentration (HHI)

A small PySpark DataFrame analysis of the project's **already-processed** CSVs. It recomputes
airline-family market shares and the Herfindahl-Hirschman Index (HHI) and checks yearly totals
against an independent published aggregate.

**Scope, stated plainly:** this is Spark running in `local` mode on about 200 rows. It shows
DataFrame skills, correctness checks and tests. It is **not** distributed processing, not a
performance result, and not AWS or cluster work. It does not touch Power BI, PostgreSQL results
or the raw PDFs.

## Inputs (read-only, committed in this repo)

| File | Used for |
|---|---|
| `data/processed/yearly_airline_domestic_history.csv` | passengers per airline per fiscal year |
| `data/processed/yearly_market_aggregates.csv` | the `all_scheduled_indian_airlines` series, used only for validation |
| `data/reference/airline_mapping.csv` | airline to `recon_group` (family) mapping, `source = yearly` rows |

If a required CSV is missing the script stops with a clear message. It never regenerates data.

## Method

Same as `sql/analysis/01_airline_year.sql` and `02_market_concentration.sql`:

1. Group canonical airlines into `recon_group` families first (for example Air India, Air India Express,
   Alliance Air, Vistara and AIX Connect become `air_india_family`).
2. Sum passengers per `(fiscal_year, recon_group)`.
3. `share_pct = 100 * group_passengers / sum of included groups' passengers that year`.
4. `HHI = SUM(share_pct ^ 2)`, on a 0-10,000 scale. Groups with zero passengers are excluded.
5. Reconcile each year's total with `all_scheduled_indian_airlines` using a **full outer join**, so a year
   missing on either side stays visible. `diff_pct = (spark - published) / published * 100` (signed).
   Default tolerance is +/-1%.

Bad input fails loudly instead of being coerced to zero: null, negative or non-numeric passengers,
malformed fiscal years, duplicate airline-years, airlines with no mapping, and conflicting mappings.
A year whose total is zero is excluded and reported, never divided.

A second table shows HHI **without** family grouping. It is a labelled comparison only and is not
the README's methodology.

## Setup (isolated, no global installs)

Verified on macOS (Apple Silicon) with Python 3.11, Java 17 and PySpark 4.0.5. PySpark 4 needs
Java 17 or newer. Python 3.14 was avoided because PySpark has not been verified on it here.

```bash
brew install openjdk@17                  # macOS; any Java 17+ works
python3.11 -m venv .venv
.venv/bin/pip install -r spark/requirements.txt
```

The script finds Java itself (it asks Homebrew for the `openjdk@17` prefix if `java` is not on your
PATH) and points Spark's workers at the same Python as the driver. If it cannot find Java it says so.

## Run

From the repository root:

```bash
.venv/bin/python spark/airlines_spark.py
```

Options: `--data-dir PATH`, `--years 2013-14 2024-25`, `--tolerance-pct 1.0`, and
`--output-dir spark/output` to write the summary CSVs (that folder is git-ignored).

## Tests

```bash
.venv/bin/python -m pytest spark/tests -q
```

41 tests: synthetic unit tests (HHI arithmetic, grouping, year isolation, validation failures,
reconciliation, determinism) and real-data tests. The real-data tests compare Spark with
(a) an independent pure-Python calculation that shares no code with the module, (b) the figures cited in the
main README, and (c) a saved snapshot of `v_market_concentration` taken from PostgreSQL 17
(`spark/tests/reference/`). Re-creating that snapshot needs Docker and the project's SQL pipeline.

## Observed results (committed data)

| Fiscal year | Total passengers | Active families | Top family (share) | Top 3 share | HHI |
|---|---|---|---|---|---|
| 2013-14 | 60,668,409 | 6 | IndiGo (29.80%) | 72.96% | 2,241.6 |
| 2019-20 | 141,199,505 | 9 | IndiGo (48.20%) | 88.44% | 3,291.8 |
| 2024-25 | 165,541,692 | 8 | IndiGo (62.97%) | 96.25% | 4,817.9 |

These match the main README (about 2,242 and 4,818) and the PostgreSQL view to floating-point precision.
Without family grouping the HHI would be 1,995.6 (2013-14) and 4,260.3 (2024-25).

### How to read the reconciliation

| Years | Result | What it means |
|---|---|---|
| FY 2013-14 to 2017-18 | exact match (0.0%) | airline rows add up to the published market total |
| FY 2007-08 to 2012-13 | Spark is 30.5% to 2.1% below | the airline file is missing some **private** carriers. The public-sector carriers (Air India, Air India Express, Alliance Air) match the published `scheduled_national_airlines` figure exactly every year. The data does not say which private carriers are missing. |
| FY 2018-19 to 2024-25 | `missing_in_aggregate` | the `all_scheduled_indian_airlines` series has no rows after FY 2017-18 |

So shares and HHI **before FY 2013-14 are computed over an incomplete market** and should not be compared
with later years. The SQL views have the same limitation.

## Limitations

- Local Spark on a small dataset. It demonstrates correctness and Spark DataFrame usage, not scale.
- The cause of the early-year coverage gap beyond "private carriers are missing" is not established by the data.
- The CI workflow in `.github/workflows/spark-tests.yml` runs the same tests on GitHub. Its result is
  only known after a run on GitHub, and local success does not guarantee it.
