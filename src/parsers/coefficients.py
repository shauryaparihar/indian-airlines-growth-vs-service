"""Parse Table 1.07 (yearly traffic coefficients), domestic block only."""

import openpyxl

from common import AGGREGATES, LOG_DIR, OUT_DIR, RAW_DIR, airline_slug, fiscal_year, norm, reconcile, \
    write_conflicts, write_csv

METRICS = {
    "PASSENGER LOAD FACTOR": "pax_load_factor_pct",
    "WEIGHT LOAD FACTOR": "weight_load_factor_pct",
    "AVERAGE SPEED OF AIRCRAFT": "avg_speed_kmh",
    "AVERAGE STAGE DISTANCE": "avg_stage_distance_km",
    "AVERAGE NUMBER OF PASSENGERS": "avg_pax_per_departure",
    "AVERAGE DISTANCE FLOWN PER": "avg_distance_per_pax_km000",
}
COLUMNS = list(METRICS.values())


def metric_for(label):
    label = norm(label)
    return next((v for k, v in METRICS.items() if label.startswith(k)), None)


def parse_sheet(ws):
    year_cols = {}
    in_domestic = False
    by_year = {}
    for row in ws.iter_rows(values_only=True):
        label = row[0]
        if not isinstance(label, str):
            continue
        block = norm(label)
        if block.startswith(("INTERNATIONAL", "DOMESTIC", "TOTAL")):
            in_domestic = block.startswith("DOMESTIC")
            continue
        if not year_cols:
            years = [fiscal_year(c) for c in row]
            if any(years):
                year_cols = {i: fy for i, fy in enumerate(years) if fy}
            continue
        if not in_domestic:
            continue
        metric = metric_for(label)
        if not metric:
            continue
        for i, fy in year_cols.items():
            v = row[i] if i < len(row) else None
            if isinstance(v, (int, float)):
                by_year.setdefault(fy, {})[metric] = v
    return by_year


def parse_file(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    name = airline_slug(path).replace("_", " ")
    sheet = next((s for s in wb.worksheets if norm(s.title).replace("_", " ") == name.upper()), wb.worksheets[-1])
    by_year = parse_sheet(sheet)
    wb.close()
    return by_year


def collect(files):
    records = []
    for path in files:
        edition = path.parent.name
        slug = airline_slug(path)
        for fy, metrics in parse_file(path).items():
            if len(metrics) == len(COLUMNS):
                records.append({**metrics, "airline": slug, "fiscal_year": fy,
                                "source_edition": edition, "source_file": path.relative_to(RAW_DIR).as_posix()})
    return reconcile(records, ["airline", "fiscal_year"], COLUMNS)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW_DIR.glob("*/*__coefficients.xlsx"))
    best, conflicts = collect(files)

    fields = ["airline", "fiscal_year", *COLUMNS, "source_edition", "source_file"]
    airlines = {k: v for k, v in best.items() if v["airline"] not in AGGREGATES}
    aggregates = {k: v for k, v in best.items() if v["airline"] in AGGREGATES}

    write_csv(OUT_DIR / "yearly_airline_coefficients.csv",
              sorted(airlines.values(), key=lambda r: (r["airline"], r["fiscal_year"])), fields)
    write_csv(OUT_DIR / "yearly_market_aggregate_coefficients.csv",
              sorted(aggregates.values(), key=lambda r: (r["airline"], r["fiscal_year"])), fields)
    if conflicts:
        write_conflicts(LOG_DIR / "yearly_coefficients_conflicts.csv", conflicts, ["airline", "fiscal_year"])

    airline_names = sorted({r["airline"] for r in airlines.values()})
    print(f"Files read: {len(files)}")
    print(f"Airlines: {len(airline_names)}")
    print(f"Airline rows: {len(airlines)}  Aggregate rows: {len(aggregates)}")
    print(f"Conflicts between editions: {len(conflicts)}"
          + (f" -> logs/{(LOG_DIR / 'yearly_coefficients_conflicts.csv').name}" if conflicts else ""))


if __name__ == "__main__":
    main()
