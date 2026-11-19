"""Build the schema and load every processed CSV + log file into PostgreSQL."""

import csv
import glob
import os
from calendar import month_abbr
from datetime import date
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
LOG_DIR = PROJECT_ROOT / "logs"
SCHEMA_DIR = PROJECT_ROOT / "sql" / "schema"
MAPPING_FILE = PROJECT_ROOT / "data" / "reference" / "airline_mapping.csv"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://airlines:airlines@localhost:5432/airlines")

DROP_ALL = """
DROP TABLE IF EXISTS data_issue, fact_monthly_market_service, fact_monthly_service,
    fact_monthly_load_factor, fact_monthly_passengers, fact_yearly_market_aggregate_coefficients,
    fact_yearly_coefficients, fact_yearly_market_aggregate, fact_yearly_airline,
    airline_mapping, dim_month, dim_airline CASCADE;
"""


def read_csv(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def none_if_blank(v):
    return v if v != "" else None


def run_schema(conn):
    conn.execute(DROP_ALL)
    for path in sorted(SCHEMA_DIR.glob("*.sql")):
        conn.execute(path.read_text(encoding="utf-8"))


def load_dim_airline(conn, mapping_rows):
    airlines = {}
    for r in mapping_rows:
        airlines[r["airline"]] = (r["airline_name"], r["recon_group"])
    with conn.cursor().copy("COPY dim_airline (airline_code, airline_name, recon_group, is_combined_entity) "
                            "FROM STDIN") as copy:
        for code, (name, group) in sorted(airlines.items()):
            copy.write_row((code, name, group, code == "jet_group"))
    return len(airlines)


def load_dim_month(conn):
    months = set()
    for path in ["monthly_airline_passengers.csv", "monthly_airline_load_factor.csv",
                 "monthly_airline_service.csv", "monthly_market_service.csv"]:
        for r in read_csv(PROCESSED / path):
            months.add((int(r["year"]), int(r["month"]), r["fiscal_year"]))
    with conn.cursor().copy("COPY dim_month (year, month, fiscal_year, calendar_date, month_name) FROM STDIN") as copy:
        for year, month, fy in sorted(months):
            copy.write_row((year, month, fy, date(year, month, 1), month_abbr[month]))
    return len(months)


def load_airline_mapping(conn, mapping_rows):
    with conn.cursor().copy("COPY airline_mapping (source, source_key, airline_code, airline_name, recon_group, "
                            "notes) FROM STDIN") as copy:
        for r in mapping_rows:
            copy.write_row((r["source"], r["source_key"], r["airline"], r["airline_name"], r["recon_group"],
                           none_if_blank(r["notes"])))
    return len(mapping_rows)


YEARLY_COLUMNS = ["departures", "hours_flown", "km_flown_thousand", "passengers", "rpk_million", "ask_million",
                  "pax_load_factor_pct", "freight_tonnes", "mail_tonnes", "total_cargo_tonnes",
                  "pax_tonne_km_million", "freight_tonne_km_million", "mail_tonne_km_million", "rtk_million",
                  "atk_million", "weight_load_factor_pct", "source_edition", "source_file"]


def load_yearly(conn, table, key_column, csv_name):
    rows = read_csv(PROCESSED / csv_name)
    db_columns = [key_column, "fiscal_year", *YEARLY_COLUMNS[:6], "pax_load_factor_pct_dgca", *YEARLY_COLUMNS[7:15],
                 "weight_load_factor_pct_dgca", "source_edition", "source_file"]
    with conn.cursor().copy(f"COPY {table} ({', '.join(db_columns)}) FROM STDIN") as copy:
        for r in rows:
            copy.write_row((r["airline"], r["fiscal_year"], *(r[c] for c in YEARLY_COLUMNS)))
    return len(rows)


COEFF_COLUMNS = ["pax_load_factor_pct", "weight_load_factor_pct", "avg_speed_kmh", "avg_stage_distance_km",
                 "avg_pax_per_departure", "avg_distance_per_pax_km000", "source_edition", "source_file"]


def load_coefficients(conn, table, key_column, csv_name):
    rows = read_csv(PROCESSED / csv_name)
    db_columns = [key_column, "fiscal_year", *COEFF_COLUMNS]
    with conn.cursor().copy(f"COPY {table} ({', '.join(db_columns)}) FROM STDIN") as copy:
        for r in rows:
            copy.write_row((r["airline"], r["fiscal_year"], *(r[c] for c in COEFF_COLUMNS)))
    return len(rows)


def load_monthly_passengers(conn):
    rows = read_csv(PROCESSED / "monthly_airline_passengers.csv")
    with conn.cursor().copy("COPY fact_monthly_passengers (airline_code, year, month, fiscal_year, pax_lakh, "
                            "passengers, source_report) FROM STDIN") as copy:
        for r in rows:
            copy.write_row((r["airline"], r["year"], r["month"], r["fiscal_year"], r["pax_lakh"], r["passengers"],
                           r["source_report"]))
    return len(rows)


def load_monthly_load_factor(conn):
    rows = read_csv(PROCESSED / "monthly_airline_load_factor.csv")
    with conn.cursor().copy("COPY fact_monthly_load_factor (airline_code, year, month, fiscal_year, "
                            "pax_load_factor_pct, source_report) FROM STDIN") as copy:
        for r in rows:
            copy.write_row((r["airline"], r["year"], r["month"], r["fiscal_year"], r["pax_load_factor_pct"],
                           r["source_report"]))
    return len(rows)


def load_monthly_service(conn):
    rows = read_csv(PROCESSED / "monthly_airline_service.csv")
    with conn.cursor().copy("COPY fact_monthly_service (airline_code, year, month, fiscal_year, metric, value, "
                            "footnote, otp_airports, source_report) FROM STDIN") as copy:
        for r in rows:
            copy.write_row((r["airline"], r["year"], r["month"], r["fiscal_year"], r["metric"], r["value"],
                           r["footnote"] == "True", none_if_blank(r["otp_airports"]), r["source_report"]))
    return len(rows)


def load_monthly_market_service(conn):
    rows = read_csv(PROCESSED / "monthly_market_service.csv")
    with conn.cursor().copy("COPY fact_monthly_market_service (year, month, fiscal_year, "
                            "overall_cancellation_rate_pct, total_complaints, complaints_per_10k, otp_airports, "
                            "source_report) FROM STDIN") as copy:
        for r in rows:
            copy.write_row((r["year"], r["month"], r["fiscal_year"], none_if_blank(r["overall_cancellation_rate_pct"]),
                           none_if_blank(r["total_complaints"]), none_if_blank(r["complaints_per_10k"]),
                           none_if_blank(r["otp_airports"]), r["source_report"]))
    return len(rows)


def load_data_issues(conn):
    rows = []

    def add(log, category, detail, airline=None, fiscal_year=None, year=None, month=None):
        rows.append((log, category, airline, fiscal_year,
                    int(year) if year else None, int(month) if month else None, detail))

    for r in read_csv(LOG_DIR / "yearly_domestic_history_conflicts.csv"):
        add("yearly_domestic_history_conflicts.csv", "edition_disagreement",
            f"{r['column']}: {r['edition_a']}={r['value_a']} vs {r['edition_b']}={r['value_b']}",
            r["airline"], r["fiscal_year"])
    for r in read_csv(LOG_DIR / "yearly_coefficients_conflicts.csv"):
        add("yearly_coefficients_conflicts.csv", "edition_disagreement",
            f"{r['column']}: {r['edition_a']}={r['value_a']} vs {r['edition_b']}={r['value_b']}",
            r["airline"], r["fiscal_year"])
    for r in read_csv(LOG_DIR / "yearly_validation_mismatches.csv"):
        add("yearly_validation_mismatches.csv", "recomputed_vs_printed",
            f"{r['metric']} ({r['source']}): computed={r['computed']} dgca={r['dgca_printed']} "
            f"diff={r['pct_diff']}%", r["airline"], r["fiscal_year"])
    for r in read_csv(LOG_DIR / "monthly_passengers_revisions.csv"):
        add("monthly_passengers_revisions.csv", "later_report_revised",
            f"{r['report_a']}={r['pax_lakh_a']} lakh -> {r['report_b']}={r['pax_lakh_b']} lakh",
            r["airline_raw"], year=r["year"], month=r["month"])
    for r in read_csv(LOG_DIR / "monthly_load_factor_revisions.csv"):
        add("monthly_load_factor_revisions.csv", "later_report_revised",
            f"{r['report_a']}={r['value_a']}% -> {r['report_b']}={r['value_b']}%",
            r["airline"], year=r["year"], month=r["month"])
    for r in read_csv(LOG_DIR / "monthly_vs_yearly_passengers.csv"):
        if r["within_tolerance"] != "True":
            add("monthly_vs_yearly_passengers.csv", "monthly_vs_yearly_mismatch",
                f"monthly={r['monthly_passengers']} yearly={r['yearly_passengers']} diff={r['pct_diff']}%",
                r["recon_group"], r["fiscal_year"])
    for name in ["monthly_passengers_checks.csv", "monthly_load_factor_checks.csv", "monthly_service_checks.csv"]:
        for r in read_csv(LOG_DIR / name):
            if r["status"] != "ok":
                y, m = r["report"].split("_")[0], r["report"].split("_")[1][:2]
                add(name, "report_check_failed", f"{r['report']}: {r['status']}", year=y, month=m)

    with conn.cursor().copy("COPY data_issue (source_log, category, airline_code, fiscal_year, year, month, detail) "
                            "FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
    return len(rows)


def main():
    mapping_rows = read_csv(MAPPING_FILE)
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        run_schema(conn)
        print(f"dim_airline: {load_dim_airline(conn, mapping_rows)}")
        print(f"dim_month: {load_dim_month(conn)}")
        print(f"airline_mapping: {load_airline_mapping(conn, mapping_rows)}")
        print(f"fact_yearly_airline: {load_yearly(conn, 'fact_yearly_airline', 'airline_code', 'yearly_airline_domestic_history.csv')}")
        print(f"fact_yearly_market_aggregate: {load_yearly(conn, 'fact_yearly_market_aggregate', 'aggregate_group', 'yearly_market_aggregates.csv')}")
        print(f"fact_yearly_coefficients: {load_coefficients(conn, 'fact_yearly_coefficients', 'airline_code', 'yearly_airline_coefficients.csv')}")
        print(f"fact_yearly_market_aggregate_coefficients: {load_coefficients(conn, 'fact_yearly_market_aggregate_coefficients', 'aggregate_group', 'yearly_market_aggregate_coefficients.csv')}")
        print(f"fact_monthly_passengers: {load_monthly_passengers(conn)}")
        print(f"fact_monthly_load_factor: {load_monthly_load_factor(conn)}")
        print(f"fact_monthly_service: {load_monthly_service(conn)}")
        print(f"fact_monthly_market_service: {load_monthly_market_service(conn)}")
        print(f"data_issue: {load_data_issues(conn)}")


if __name__ == "__main__":
    main()
