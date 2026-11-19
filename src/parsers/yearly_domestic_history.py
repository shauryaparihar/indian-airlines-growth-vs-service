"""Parse Table 1.04 (10-year domestic history) from the yearly airline Excel files."""

import openpyxl

from common import AGGREGATES, LOG_DIR, OUT_DIR, RAW_DIR, airline_slug, fiscal_year, reconcile, \
    write_conflicts, write_csv

COLUMNS = [
    "departures", "hours_flown", "km_flown_thousand", "passengers",
    "rpk_million", "ask_million", "pax_load_factor_pct",
    "freight_tonnes", "mail_tonnes", "total_cargo_tonnes",
    "pax_tonne_km_million", "freight_tonne_km_million", "mail_tonne_km_million",
    "rtk_million", "atk_million", "weight_load_factor_pct",
]


def parse_file(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = []
    for row in ws.iter_rows(values_only=True):
        fy = fiscal_year(row[0])
        values = row[1:17]
        if fy and len(values) == 16 and all(isinstance(v, (int, float, type(None))) for v in values):
            values = [v or 0 for v in values]
            if any(values):
                rows.append((fy, values))
    wb.close()
    return rows


def collect(files):
    records = []
    for path in files:
        edition = path.parent.name
        slug = airline_slug(path)
        for fy, values in parse_file(path):
            records.append({**dict(zip(COLUMNS, values)), "airline": slug, "fiscal_year": fy,
                            "source_edition": edition, "source_file": path.relative_to(RAW_DIR).as_posix()})
    return reconcile(records, ["airline", "fiscal_year"], COLUMNS)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW_DIR.glob("*/*__domestic_history.xlsx"))
    best, conflicts = collect(files)

    fields = ["airline", "fiscal_year", *COLUMNS, "source_edition", "source_file"]
    airlines = {k: v for k, v in best.items() if v["airline"] not in AGGREGATES}
    aggregates = {k: v for k, v in best.items() if v["airline"] in AGGREGATES}

    write_csv(OUT_DIR / "yearly_airline_domestic_history.csv",
              sorted(airlines.values(), key=lambda r: (r["airline"], r["fiscal_year"])), fields)
    write_csv(OUT_DIR / "yearly_market_aggregates.csv",
              sorted(aggregates.values(), key=lambda r: (r["airline"], r["fiscal_year"])), fields)
    if conflicts:
        write_conflicts(LOG_DIR / "yearly_domestic_history_conflicts.csv", conflicts, ["airline", "fiscal_year"])

    airline_names = sorted({r["airline"] for r in airlines.values()})
    print(f"Files read: {len(files)}")
    print(f"Airlines: {len(airline_names)} -> {', '.join(airline_names)}")
    print(f"Airline rows: {len(airlines)}  Aggregate rows: {len(aggregates)}")
    print(f"Conflicts between editions: {len(conflicts)}"
          + (f" -> logs/{(LOG_DIR / 'yearly_domestic_history_conflicts.csv').name}" if conflicts else ""))
    for slug in airline_names:
        years = sorted(fy for (a, fy) in airlines if a == slug)
        print(f"  {slug:28s} {years[0]} .. {years[-1]} ({len(years)})")


if __name__ == "__main__":
    main()
