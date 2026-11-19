"""Local PySpark analysis of Indian airline market concentration.

Reproduces the repository's SQL methodology (sql/analysis/01_airline_year.sql and
02_market_concentration.sql) with Spark DataFrames:

1. Group canonical airlines into ``recon_group`` families (data/reference/airline_mapping.csv).
2. Sum passengers per (fiscal_year, recon_group).
3. share_pct = 100 * group_passengers / sum of included groups' passengers that year.
4. HHI = SUM(share_pct ** 2), on a 0-10,000 scale.
5. Compare the summed airline passengers with the published aggregate
   ``all_scheduled_indian_airlines`` using a FULL OUTER join, so unmatched years stay visible.

This is local Spark on a few hundred rows. It shows DataFrame fluency, not distributed scale.

Run from the repository root:  .venv/bin/python spark/airlines_spark.py
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data"

HISTORY_FILE = "processed/yearly_airline_domestic_history.csv"
AGGREGATE_FILE = "processed/yearly_market_aggregates.csv"
MAPPING_FILE = "reference/airline_mapping.csv"

MARKET_AGGREGATE_NAME = "all_scheduled_indian_airlines"
FISCAL_YEAR_PATTERN = r"^\d{4}-\d{2}$"
DEFAULT_TOLERANCE_PCT = 1.0  # README: monthly vs yearly totals are checked within 1%.


class DataValidationError(ValueError):
    """Raised when the input data cannot be analysed without guessing."""


# --------------------------------------------------------------------------- #
# Environment helpers
# --------------------------------------------------------------------------- #
def _java_works() -> bool:
    try:
        result = subprocess.run(["java", "-version"], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def ensure_java() -> None:
    """Find a Java runtime; resolve the Homebrew prefix instead of hard-coding it."""
    if _java_works():
        return
    if not os.environ.get("JAVA_HOME") and shutil.which("brew"):
        out = subprocess.run(
            ["brew", "--prefix", "openjdk@17"], capture_output=True, text=True
        )
        home = Path(out.stdout.strip()) / "libexec/openjdk.jdk/Contents/Home"
        if out.returncode == 0 and (home / "bin/java").exists():
            os.environ["JAVA_HOME"] = str(home)
            os.environ["PATH"] = f"{home / 'bin'}{os.pathsep}{os.environ['PATH']}"
            return
    raise RuntimeError(
        "No working Java found. Spark 4 needs Java 17+. Install one "
        "(macOS: `brew install openjdk@17`) and set JAVA_HOME."
    )


def create_spark(app_name: str = "airlines-spark") -> SparkSession:
    ensure_java()
    # Workers must use the same interpreter as the driver, otherwise Spark raises
    # PYTHON_VERSION_MISMATCH when the system python3 differs from the venv.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    spark = (
        SparkSession.builder.appName(app_name)
        .master("local[2]")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def _read_csv(spark: SparkSession, path: Path, required: list[str]) -> DataFrame:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required input missing: {path}. Not regenerating the pipeline; "
            "restore the committed processed CSV and retry."
        )
    df = spark.read.option("header", True).option("inferSchema", False).csv(str(path))
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataValidationError(f"{path.name} is missing columns: {missing}")
    return df.select(*required)


def read_inputs(spark: SparkSession, data_dir: Path) -> tuple[DataFrame, DataFrame, DataFrame]:
    history = _read_csv(spark, data_dir / HISTORY_FILE, ["airline", "fiscal_year", "passengers"])
    aggregates = _read_csv(spark, data_dir / AGGREGATE_FILE, ["airline", "fiscal_year", "passengers"])
    mapping = _read_csv(
        spark, data_dir / MAPPING_FILE, ["source", "source_key", "airline", "recon_group"]
    )
    return history, aggregates, mapping


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _examples(df: DataFrame, cols: list[str], n: int = 5) -> str:
    return "; ".join(", ".join(str(v) for v in row) for row in df.select(*cols).limit(n).collect())


def validate_passengers(df: DataFrame, label: str, allow_null: bool = False) -> DataFrame:
    """Trim identifiers, cast passengers to double and fail loudly on bad values.

    Zero passengers are legal (an airline that did not fly). Null, non-numeric,
    NaN, infinite or negative values are never silently turned into zero.
    """
    raw = F.trim(F.col("passengers").cast("string"))
    # try_cast: Spark 4 runs in ANSI mode, where a plain cast of "abc" raises a raw Spark error
    # instead of returning null, which would bypass our clear validation message.
    value = raw.try_cast("double")
    missing = raw.isNull() | (raw == "")
    unparsable = ~missing & (value.isNull() | F.isnan(value) | value.isin(float("inf"), float("-inf")))
    negative = value < 0

    out = df.select(
        F.trim(F.col("airline")).alias("airline"),
        F.trim(F.col("fiscal_year")).alias("fiscal_year"),
        raw.alias("_raw"),
        value.alias("passengers"),
        missing.alias("_missing"),
        unparsable.alias("_unparsable"),
        negative.alias("_negative"),
    )

    bad_year = out.filter(
        F.col("fiscal_year").isNull() | ~F.col("fiscal_year").rlike(FISCAL_YEAR_PATTERN)
    )
    if bad_year.limit(1).count():
        raise DataValidationError(
            f"{label}: null or malformed fiscal_year (expected like 2024-25). "
            f"Examples (airline, fiscal_year): {_examples(bad_year, ['airline', 'fiscal_year'])}"
        )
    bad_airline = out.filter(F.col("airline").isNull() | (F.col("airline") == ""))
    if bad_airline.limit(1).count():
        raise DataValidationError(f"{label}: null or blank airline name found.")

    bad = out.filter(F.col("_unparsable") | F.col("_negative") | (F.col("_missing") & F.lit(not allow_null)))
    if bad.limit(1).count():
        raise DataValidationError(
            f"{label}: null, negative or invalid passenger counts. "
            f"Examples (airline, fiscal_year, raw): {_examples(bad, ['airline', 'fiscal_year', '_raw'])}"
        )

    dupes = out.groupBy("airline", "fiscal_year").count().filter(F.col("count") > 1)
    if dupes.limit(1).count():
        raise DataValidationError(
            f"{label}: duplicate (airline, fiscal_year) rows. "
            f"Examples: {_examples(dupes, ['airline', 'fiscal_year', 'count'])}"
        )
    return out.select("airline", "fiscal_year", "passengers")


def build_mapping_lookup(mapping: DataFrame) -> DataFrame:
    """One row per canonical airline -> recon_group, from the 'yearly' mapping rows.

    Several source_keys can point to one canonical airline (air_asia and aix_connect
    both mean aix_connect), so we deduplicate on (airline, recon_group) and then
    insist that each airline has exactly one group. A plain join to the raw mapping
    would multiply rows.
    """
    yearly = mapping.filter(F.trim(F.col("source")) == "yearly").select(
        F.trim(F.col("airline")).alias("airline"),
        F.trim(F.col("recon_group")).alias("recon_group"),
    )
    blank = yearly.filter(
        F.col("airline").isNull() | (F.col("airline") == "")
        | F.col("recon_group").isNull() | (F.col("recon_group") == "")
    )
    if blank.limit(1).count():
        raise DataValidationError("airline_mapping.csv: yearly row with blank airline or recon_group.")

    lookup = yearly.distinct()
    conflicts = lookup.groupBy("airline").agg(F.countDistinct("recon_group").alias("groups")).filter(
        F.col("groups") > 1
    )
    if conflicts.limit(1).count():
        raise DataValidationError(
            f"airline_mapping.csv: airline mapped to more than one recon_group: "
            f"{_examples(conflicts, ['airline', 'groups'])}"
        )
    return lookup


# --------------------------------------------------------------------------- #
# Transformations (pure DataFrame in -> DataFrame out; no Spark session created)
# --------------------------------------------------------------------------- #
def build_group_year(history_clean: DataFrame, lookup: DataFrame) -> DataFrame:
    """Sum passengers per (fiscal_year, recon_group), failing on unmapped airlines."""
    joined = history_clean.join(lookup, on="airline", how="left")
    unmapped = joined.filter(F.col("recon_group").isNull()).select("airline").distinct()
    if unmapped.limit(1).count():
        names = sorted(r["airline"] for r in unmapped.collect())
        raise DataValidationError(f"Airlines in the history with no yearly mapping: {names}")
    return joined.groupBy("fiscal_year", "recon_group").agg(F.sum("passengers").alias("passengers"))


def zero_total_years(df: DataFrame) -> DataFrame:
    """Years whose included passengers sum to zero; share and HHI are undefined there."""
    return (
        df.groupBy("fiscal_year").agg(F.sum("passengers").alias("total"))
        .filter(F.col("total") == 0)
        .select("fiscal_year")
    )


def compute_shares(df: DataFrame, key: str = "recon_group") -> DataFrame:
    """Market share per (fiscal_year, key). Zero-passenger members are excluded, as in SQL.

    Years with a zero (or empty) denominator produce no rows instead of dividing by zero.
    """
    active = df.filter(F.col("passengers") > 0)
    by_year = Window.partitionBy("fiscal_year")
    ranked = Window.partitionBy("fiscal_year").orderBy(F.desc("passengers"), F.asc(key))
    return (
        active.withColumn("year_total", F.sum("passengers").over(by_year))
        .withColumn("share_pct", F.lit(100.0) * F.col("passengers") / F.col("year_total"))
        .withColumn("rank", F.row_number().over(ranked))
        .select("fiscal_year", key, "passengers", "year_total", "share_pct", "rank")
    )


def compute_concentration(shares: DataFrame, key: str = "recon_group") -> DataFrame:
    """Per-year total, active members, top member and share, top-3 share and HHI."""
    return (
        shares.groupBy("fiscal_year")
        .agg(
            F.sum("passengers").alias("total_passengers"),
            F.count(F.lit(1)).alias("active_groups"),
            F.max(F.when(F.col("rank") == 1, F.col(key))).alias("top_group"),
            F.max(F.when(F.col("rank") == 1, F.col("share_pct"))).alias("top_share_pct"),
            F.sum(F.when(F.col("rank") <= 3, F.col("share_pct"))).alias("top3_share_pct"),
            F.sum(F.col("share_pct") * F.col("share_pct")).alias("hhi"),
        )
        .orderBy("fiscal_year")
    )


def reconcile_with_aggregate(
    totals: DataFrame,
    aggregates_clean: DataFrame,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    aggregate_name: str = MARKET_AGGREGATE_NAME,
) -> DataFrame:
    """FULL OUTER year-level comparison against the published aggregate.

    ``totals`` has (fiscal_year, spark_passengers). Difference is signed:
    (spark - published) / published * 100, so negative means our airline rows
    cover less than the published total. Years present on only one side stay visible.
    """
    published = aggregates_clean.filter(F.col("airline") == aggregate_name).select(
        "fiscal_year", F.col("passengers").alias("aggregate_passengers")
    )
    diff = F.col("spark_passengers") - F.col("aggregate_passengers")
    return (
        totals.join(published, on="fiscal_year", how="full_outer")
        .withColumn("diff_passengers", diff)
        .withColumn(
            "diff_pct",
            F.when(F.col("aggregate_passengers") > 0, diff / F.col("aggregate_passengers") * 100),
        )
        .withColumn(
            "status",
            F.when(F.col("spark_passengers").isNull(), "missing_in_airline_data")
            .when(F.col("aggregate_passengers").isNull(), "missing_in_aggregate")
            .when(F.col("aggregate_passengers") <= 0, "zero_aggregate")
            .when(F.abs(F.col("diff_pct")) <= tolerance_pct, "within_tolerance")
            .otherwise("outside_tolerance"),
        )
        .orderBy("fiscal_year")
    )


def run_analysis(
    history: DataFrame,
    aggregates: DataFrame,
    mapping: DataFrame,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> dict[str, DataFrame]:
    """Wire the steps together; returns small DataFrames for display or testing."""
    history_clean = validate_passengers(history, "yearly_airline_domestic_history")
    aggregates_clean = validate_passengers(aggregates, "yearly_market_aggregates", allow_null=True)
    lookup = build_mapping_lookup(mapping)

    group_year = build_group_year(history_clean, lookup)
    shares = compute_shares(group_year, "recon_group")
    concentration = compute_concentration(shares, "recon_group")

    # Separate, clearly named comparison: HHI with NO family grouping.
    airline_year = history_clean.join(lookup.select("airline"), on="airline", how="inner")
    ungrouped = compute_concentration(compute_shares(airline_year, "airline"), "airline").select(
        "fiscal_year", F.col("active_groups").alias("active_airlines"),
        F.col("hhi").alias("ungrouped_airline_hhi"),
    )

    totals = concentration.select("fiscal_year", F.col("total_passengers").alias("spark_passengers"))
    reconciliation = reconcile_with_aggregate(totals, aggregates_clean, tolerance_pct)
    return {
        "shares": shares,
        "concentration": concentration,
        "ungrouped": ungrouped,
        "reconciliation": reconciliation,
        "zero_total_years": zero_total_years(group_year),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _write_csv(df: DataFrame, path: Path) -> None:
    rows = df.collect()  # small summary tables only
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(df.columns)
        writer.writerows([list(r) for r in rows])


def main(argv: list[str] | None = None, spark: SparkSession | None = None) -> int:
    """Run the CLI. A session passed in by the caller (e.g. tests) is left running."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="Directory holding processed/ and reference/ (default: <repo>/data)")
    parser.add_argument("--tolerance-pct", type=float, default=DEFAULT_TOLERANCE_PCT)
    parser.add_argument("--years", nargs="*", default=["2013-14", "2024-25"],
                        help="Fiscal years whose per-group shares are printed")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Optional: write summary CSVs here (use spark/output/, which is git-ignored)")
    args = parser.parse_args(argv)

    owns_session = spark is None
    try:
        if owns_session:
            spark = create_spark()
        history, aggregates, mapping = read_inputs(spark, args.data_dir)
        result = run_analysis(history, aggregates, mapping, args.tolerance_pct)

        print("\n== Concentration by fiscal year (airline families, HHI on 0-10,000 scale) ==")
        result["concentration"].select(
            "fiscal_year", "total_passengers", "active_groups", "top_group",
            F.round("top_share_pct", 2).alias("top_share_pct"),
            F.round("top3_share_pct", 2).alias("top3_share_pct"),
            F.round("hhi", 1).alias("hhi"),
        ).show(50, truncate=False)

        print("== Comparison only: HHI WITHOUT family grouping (not the README methodology) ==")
        result["ungrouped"].select(
            "fiscal_year", "active_airlines", F.round("ungrouped_airline_hhi", 1).alias("ungrouped_airline_hhi")
        ).orderBy("fiscal_year").show(50, truncate=False)

        for year in args.years:
            print(f"== Group shares, FY {year} ==")
            result["shares"].filter(F.col("fiscal_year") == year).orderBy("rank").select(
                "fiscal_year", "recon_group", "passengers", F.round("share_pct", 2).alias("share_pct")
            ).show(10, truncate=False)

        print(f"== Reconciliation vs {MARKET_AGGREGATE_NAME} "
              f"(diff_pct = (spark - published)/published*100; tolerance +/-{args.tolerance_pct}%) ==")
        result["reconciliation"].select(
            "fiscal_year", "spark_passengers", "aggregate_passengers", "diff_passengers",
            F.round("diff_pct", 3).alias("diff_pct"), "status",
        ).show(50, truncate=False)

        zeros = [r["fiscal_year"] for r in result["zero_total_years"].collect()]
        if zeros:
            print(f"Excluded (zero passenger total, share undefined): {zeros}")

        if args.output_dir:
            for name in ("concentration", "ungrouped", "reconciliation"):
                _write_csv(result[name], args.output_dir / f"{name}.csv")
            print(f"Wrote summary CSVs to {args.output_dir}")
        return 0
    except (DataValidationError, FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if owns_session and spark is not None:
            spark.stop()


if __name__ == "__main__":
    sys.exit(main())
